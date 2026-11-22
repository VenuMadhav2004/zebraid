"""Integration tests for the grounded Gemini scientific assistant endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
from google.genai import errors as genai_errors

from app.core.config import Settings
from app.models.enums import AnalysisKind, RoiMode, RunStatus
from app.repositories import stripe_analyses as analysis_repo
from app.services import assistant as assistant_service
from tests.conftest import image_bytes, unique_color, upload


class _FakeGenAIClient:
    def __init__(self, handler):
        self._handler = handler
        self.calls = []
        self.models = SimpleNamespace(generate_content=self._generate_content)

    def _generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._handler(kwargs)

    def close(self):
        pass


def _ok_response(text: str):
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text=text)]))],
    )


def test_assistant_reports_unavailable_when_key_empty(api, monkeypatch):
    monkeypatch.setattr(assistant_service, "get_settings", lambda: Settings(_env_file=None, gemini_api_key=""))
    st = api.get("/api/v1/assistant/status")
    assert st.status_code == 200
    assert st.json()["available"] is False
    assert "GEMINI_API_KEY" in st.json()["reason"]

    ask = api.post("/api/v1/assistant/ask", json={"question": "Summarize the latest stripe measurements."})
    assert ask.status_code == 503
    assert ask.json()["error"]["code"] == "assistant_unavailable"


def test_assistant_status_available_when_configured_without_leaking_key(api, monkeypatch):
    fake_secret = "never-expose-this-key-12345"
    monkeypatch.setattr(
        assistant_service,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key=fake_secret, gemini_model="gemini-2.5-flash"),
    )
    st = api.get("/api/v1/assistant/status")
    assert st.status_code == 200
    assert st.json() == {"available": True, "model": "gemini-2.5-flash", "reason": None}
    assert fake_secret not in st.text


def test_assistant_validates_empty_and_oversized_messages(api, monkeypatch):
    monkeypatch.setattr(
        assistant_service,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key="test-fake-key", gemini_model="gemini-2.5-flash"),
    )

    for bad_payload in (
        {"question": ""},
        {"question": "   "},
        {"question": "a"},
        {"question": "x" * 2001},
    ):
        resp = api.post("/api/v1/assistant/ask", json=bad_payload)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"


def test_assistant_missing_record_returns_404(api, monkeypatch):
    monkeypatch.setattr(
        assistant_service,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key="test-fake-key", gemini_model="gemini-2.5-flash"),
    )
    resp = api.post(
        "/api/v1/assistant/ask",
        json={"question": "Explain this zebra.", "zebra_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_assistant_missing_context_uses_database_summary_only(api, monkeypatch):
    cfg = Settings(_env_file=None, gemini_api_key="test-fake-key", gemini_model="gemini-2.5-flash")
    fake_client = _FakeGenAIClient(
        lambda kw: _ok_response(
            "**Observed Measurements & Recorded Data**\nDatabase summary only.\n\n"
            "**Interpretation & Hypotheses**\nSelect an image or completed analysis to inspect stripe measurements."
        )
    )
    monkeypatch.setattr(assistant_service, "get_settings", lambda: cfg)
    monkeypatch.setattr(assistant_service, "_create_genai_client", lambda key, timeout: fake_client)

    resp = api.post("/api/v1/assistant/ask", json={"question": "What stripe width was measured?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "gemini-2.5-flash"
    assert body["grounded_context"]["included_records"] == []
    assert body["grounded_context"]["analysis_count"] == 0
    assert "Observed Measurements" in body["answer"]


def test_assistant_grounds_prompt_in_real_db_records_and_analyses_and_history(api, db, fake_storage, monkeypatch):
    z = api.post("/api/v1/zebras", json={"code": "GEM-01", "name": "Nuru", "species": "Equus quagga"}).json()
    img = upload(api, image_bytes(size=(120, 90), color=unique_color())).json()

    analysis_id = None
    if analysis_repo.table_exists(db):
        job = analysis_repo.create_analysis(
            db,
            image_asset_id=uuid.UUID(img["id"]),
            kind=AnalysisKind.STRIPE_MORPHOLOGY,
            roi={"x": 0, "y": 0, "width": 120, "height": 90},
            roi_mode=RoiMode.AUTO,
            parameters={},
            provider={"name": "member1", "version": "1.0.0"},
        )
        job.status = RunStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.result = {
            "stripe_width_px": {"mean": 11.75, "std": 1.2},
            "quality_metrics": {"confidence_score": 0.84},
        }
        db.flush()
        analysis_id = str(job.id)

    cfg = Settings(_env_file=None, gemini_api_key="test-fake-key", gemini_model="gemini-2.5-flash")
    fake_client = _FakeGenAIClient(
        lambda kw: _ok_response(
            "**Observed Measurements & Recorded Data**\n"
            "Image is 120x90 px; zebra GEM-01 (Nuru); mean stripe width 11.75 px.\n\n"
            "**Interpretation & Hypotheses**\n"
            "quality_metrics.confidence_score (0.84) is a segmentation quality heuristic, not an identity probability."
        )
    )
    monkeypatch.setattr(assistant_service, "get_settings", lambda: cfg)
    monkeypatch.setattr(assistant_service, "_create_genai_client", lambda key, timeout: fake_client)

    payload = {
        "question": "Explain the recorded data for this zebra and image.",
        "zebra_id": z["id"],
        "image_id": img["id"],
        "history": [
            {"role": "user", "text": "Earlier question about GEM-01"},
            {"role": "model", "text": "Earlier grounded explanation"},
        ],
    }
    if analysis_id:
        payload["analysis_ids"] = [analysis_id]

    resp = api.post("/api/v1/assistant/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    sent_contents = fake_client.calls[0]["contents"]
    assert len(sent_contents) == 3
    final_prompt = sent_contents[-1].parts[0].text
    assert "GEM-01" in final_prompt
    assert "120" in final_prompt
    if analysis_id:
        assert "11.75" in final_prompt
        assert data["grounded_context"]["analysis_count"] == 1
    assert data["model"] == "gemini-2.5-flash"
    assert "zebra" in data["grounded_context"]["included_records"]
    assert "image" in data["grounded_context"]["included_records"]
    assert data["grounded_context"]["history_turns"] == 2
    assert "Observed Measurements" in data["answer"]


def test_assistant_http_maps_provider_errors_cleanly(api, monkeypatch):
    secret = "super-secret-invalid-key"
    cfg = Settings(_env_file=None, gemini_api_key=secret, gemini_model="gemini-2.5-flash")
    monkeypatch.setattr(assistant_service, "get_settings", lambda: cfg)

    cases = [
        (
            genai_errors.ClientError(400, {"error": {"status": "INVALID_ARGUMENT", "message": "API key not valid."}}),
            503,
            "assistant_invalid_api_key",
        ),
        (
            genai_errors.ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}}),
            429,
            "assistant_rate_limited",
        ),
        (
            httpx.ReadTimeout("timeout"),
            504,
            "assistant_timeout",
        ),
        (
            httpx.ConnectError("network down"),
            502,
            "assistant_network_error",
        ),
    ]

    for exc, expected_status, expected_code in cases:
        def _raise(_kw, _exc=exc):
            raise _exc

        monkeypatch.setattr(assistant_service, "_create_genai_client", lambda key, timeout, fn=_raise: _FakeGenAIClient(fn))
        resp = api.post("/api/v1/assistant/ask", json={"question": "Explain stripe orientation coherence."})
        assert resp.status_code == expected_status
        assert resp.json()["error"]["code"] == expected_code
        assert secret not in resp.text
