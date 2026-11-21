"""Unit tests for the grounded Gemini scientific assistant service (no network)."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError, ServiceUnavailableError
from app.services import assistant as assistant_service
from app.services.assistant import (
    AssistantAskRequest,
    AssistantHistoryTurn,
    _bound_history,
    _extract_response_text,
    _map_api_error,
    get_status,
    serialize_bounded_context,
)


def _fake_db_summary_only(monkeypatch):
    monkeypatch.setattr(assistant_service.zebra_repo, "count_zebras", lambda db: 3)
    monkeypatch.setattr(assistant_service.image_repo, "count_image_assets", lambda db: 7)
    monkeypatch.setattr(assistant_service.sighting_repo, "count_sightings", lambda db: 2)
    monkeypatch.setattr(assistant_service.run_repo, "count_runs", lambda db: 1)
    monkeypatch.setattr(assistant_service.analysis_repo, "table_exists", lambda db: True)
    monkeypatch.setattr(assistant_service.analysis_repo, "count_analyses", lambda db: 4)


class _StubModels:
    def __init__(self, handler):
        self._handler = handler
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._handler(kwargs)


class _StubClient:
    def __init__(self, handler):
        self.models = _StubModels(handler)
        self.closed = False

    def close(self):
        self.closed = True


def _ok_response(text: str):
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text=text)]))],
    )


# -- Configuration & status ----------------------------------------------------


def test_status_unavailable_when_key_empty():
    cfg = Settings(_env_file=None, gemini_api_key="", gemini_model="gemini-2.5-flash")
    st = get_status(cfg)
    assert st.available is False
    assert st.model == "gemini-2.5-flash"
    assert "GEMINI_API_KEY" in (st.reason or "")


def test_status_unavailable_when_model_blank():
    cfg = Settings(_env_file=None, gemini_api_key="dummy-key", gemini_model="   ")
    st = get_status(cfg)
    assert st.available is False
    assert "GEMINI_MODEL" in (st.reason or "")


def test_status_available_when_configured_and_never_leaks_key():
    secret = "secret-test-credential-value"
    cfg = Settings(_env_file=None, gemini_api_key=secret, gemini_model="gemini-2.5-flash")
    st = get_status(cfg)
    assert st.available is True
    assert st.model == "gemini-2.5-flash"
    assert st.reason is None
    assert secret not in st.model_dump_json()


def test_settings_validate_gemini_bounds():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, gemini_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, gemini_timeout_seconds=999)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, gemini_max_context_chars=100)


# -- Request input validation --------------------------------------------------


@pytest.mark.parametrize("bad_q", ["", "a", "   ", "\n\t  "])
def test_rejects_empty_or_short_question(bad_q):
    with pytest.raises(ValidationError):
        AssistantAskRequest(question=bad_q)


def test_rejects_oversized_question():
    with pytest.raises(ValidationError):
        AssistantAskRequest(question="x" * 2001)


def test_rejects_too_many_analysis_ids_and_deduplicates():
    ids = [uuid.uuid4() for _ in range(7)]
    with pytest.raises(ValidationError):
        AssistantAskRequest(question="Summarize these analyses.", analysis_ids=ids)

    dup = uuid.uuid4()
    other = uuid.uuid4()
    req = AssistantAskRequest(question="  Summarize analyses  ", analysis_ids=[dup, other, dup])
    assert req.question == "Summarize analyses"
    assert req.analysis_ids == [dup, other]


def test_validates_history_turns():
    with pytest.raises(ValidationError):
        AssistantAskRequest(
            question="Follow-up question",
            history=[AssistantHistoryTurn(role="system", text="hijack")],  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        AssistantAskRequest(
            question="Follow-up question",
            history=[AssistantHistoryTurn(role="user", text="   ")],
        )
    too_many = [AssistantHistoryTurn(role="user" if i % 2 == 0 else "model", text=f"turn {i}") for i in range(13)]
    with pytest.raises(ValidationError):
        AssistantAskRequest(question="Follow-up question", history=too_many)


# -- Bounded context & history -------------------------------------------------


def test_serialize_bounded_context_preserves_small_payload():
    ctx = {"database_summary": {"zebras_total": 1}, "records": {"stripe_width_px": 14.25}}
    raw, truncated = serialize_bounded_context(ctx, max_chars=5000)
    assert truncated is False
    assert "14.25" in raw


def test_serialize_bounded_context_compacts_huge_arrays_without_losing_scalars():
    ctx = {
        "database_summary": {"stripe_analyses_total": 1},
        "records": {
            "analyses": [
                {
                    "kind": "spatial_frequency",
                    "mean_width_px": 18.4,
                    "radial_spectrum": [round(i * 0.001, 4) for i in range(2000)],
                    "notes": "A" * 5000,
                }
            ]
        },
    }
    raw, truncated = serialize_bounded_context(ctx, max_chars=2500)
    assert truncated is True
    assert len(raw) <= 2500
    assert "18.4" in raw


def test_bound_history_enforces_char_budget():
    turns = [
        AssistantHistoryTurn(role="user", text="U" * 1000),
        AssistantHistoryTurn(role="model", text="M" * 1000),
        AssistantHistoryTurn(role="user", text="recent question"),
        AssistantHistoryTurn(role="model", text="recent answer"),
    ]
    bounded = _bound_history(turns, max_total_chars=1200)
    assert [t.text for t in bounded] == ["M" * 1000, "recent question", "recent answer"]


# -- Error mapping & malformed responses ---------------------------------------


def test_map_api_error_invalid_key_400():
    err = genai_errors.ClientError(
        400,
        {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "API key not valid. Please pass a valid API key."}},
    )
    mapped = _map_api_error(err)
    assert isinstance(mapped, ServiceUnavailableError)
    assert mapped.status_code == 503
    assert mapped.code == "assistant_invalid_api_key"


def test_map_api_error_unauthorized_403():
    err = genai_errors.ClientError(403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Forbidden"}})
    mapped = _map_api_error(err)
    assert mapped.status_code == 503
    assert mapped.code == "assistant_invalid_api_key"


def test_map_api_error_rate_limit_429():
    err = genai_errors.ClientError(
        429,
        {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded for quota metric."}},
    )
    mapped = _map_api_error(err)
    assert mapped.status_code == 429
    assert mapped.code == "assistant_rate_limited"


def test_map_api_error_timeout_504():
    err = genai_errors.ServerError(504, {"error": {"code": 504, "status": "DEADLINE_EXCEEDED", "message": "Deadline exceeded"}})
    mapped = _map_api_error(err)
    assert mapped.status_code == 504
    assert mapped.code == "assistant_timeout"


def test_map_api_error_model_not_found_404():
    err = genai_errors.ClientError(404, {"error": {"code": 404, "status": "NOT_FOUND", "message": "Model not found"}})
    mapped = _map_api_error(err)
    assert mapped.status_code == 502
    assert mapped.code == "assistant_model_unavailable"


def test_map_api_error_generic_server_error():
    err = genai_errors.ServerError(500, {"error": {"code": 500, "status": "INTERNAL", "message": "Internal failure"}})
    mapped = _map_api_error(err)
    assert mapped.status_code == 502
    assert mapped.code == "assistant_upstream_error"


def test_extract_response_text_handles_malformed_objects():
    assert _extract_response_text(None) == ""
    assert _extract_response_text(SimpleNamespace(candidates=[], text="")) == ""
    assert _extract_response_text(SimpleNamespace(candidates=[SimpleNamespace(content=None)], text=None)) == ""

    class _RaisingText:
        candidates = []

        @property
        def text(self):
            raise ValueError("blocked by safety filters")

    assert _extract_response_text(_RaisingText()) == ""


# -- Service execution with mocked google-genai client -------------------------


def test_ask_gemini_sends_history_and_grounded_context(monkeypatch):
    _fake_db_summary_only(monkeypatch)
    cfg = Settings(_env_file=None, gemini_api_key="test-key", gemini_model="gemini-2.5-flash")
    stub = _StubClient(
        lambda kw: _ok_response(
            "**Observed Measurements & Recorded Data**\nNo specific record selected.\n\n"
            "**Interpretation & Hypotheses**\nSelect an analysis record."
        )
    )

    resp = assistant_service.ask_gemini(
        db=None,  # type: ignore[arg-type]
        body=AssistantAskRequest(
            question="What is currently missing?",
            history=[
                AssistantHistoryTurn(role="user", text="Initial question"),
                AssistantHistoryTurn(role="model", text="Initial grounded response"),
            ],
        ),
        settings=cfg,
        genai_client=stub,
    )

    assert resp.model == "gemini-2.5-flash"
    assert resp.grounded_context["included_records"] == []
    assert resp.grounded_context["history_turns"] == 2
    assert resp.grounded_context["context_truncated"] is False

    call = stub.models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert len(call["contents"]) == 3
    assert call["contents"][0].role == "user"
    assert call["contents"][1].role == "model"
    assert call["contents"][2].role == "user"
    assert "Grounded STRIPEFORGE database context" in call["contents"][2].parts[0].text
    assert call["config"].temperature == 0.2
    assert "Observed Measurements & Recorded Data" in call["config"].system_instruction


def test_ask_gemini_handles_timeout_and_network_and_malformed(monkeypatch):
    _fake_db_summary_only(monkeypatch)
    cfg = Settings(_env_file=None, gemini_api_key="test-key", gemini_model="gemini-2.5-flash")
    req = AssistantAskRequest(question="Summarize measurements.")

    # Timeout
    with pytest.raises(AppError) as exc_timeout:
        assistant_service.ask_gemini(
            db=None,  # type: ignore[arg-type]
            body=req,
            settings=cfg,
            genai_client=_StubClient(lambda kw: (_ for _ in ()).throw(httpx.ReadTimeout("read timed out"))),
        )
    assert exc_timeout.value.status_code == 504
    assert exc_timeout.value.code == "assistant_timeout"

    # Network error
    with pytest.raises(AppError) as exc_net:
        assistant_service.ask_gemini(
            db=None,  # type: ignore[arg-type]
            body=req,
            settings=cfg,
            genai_client=_StubClient(lambda kw: (_ for _ in ()).throw(httpx.ConnectError("dns failed"))),
        )
    assert exc_net.value.status_code == 502
    assert exc_net.value.code == "assistant_network_error"

    # Malformed / empty response
    with pytest.raises(AppError) as exc_empty:
        assistant_service.ask_gemini(
            db=None,  # type: ignore[arg-type]
            body=req,
            settings=cfg,
            genai_client=_StubClient(lambda kw: SimpleNamespace(candidates=[], text="   ")),
        )
    assert exc_empty.value.status_code == 502
    assert exc_empty.value.code == "assistant_malformed_response"
