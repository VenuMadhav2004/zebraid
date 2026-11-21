"""Background preload of the MegaDescriptor checkpoint and its reported state (fake loader, no weights)."""
import sys
import types

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.integrations.recognition import megadescriptor as md
from app.main import create_app
from app.services import identifications as id_service


@pytest.fixture
def fake_engine(monkeypatch, tmp_path):
    ckpt = tmp_path / "megadescriptor.bin"
    ckpt.write_bytes(b"not-real-weights")
    settings = Settings(_env_file=None, recognition_model_path=str(ckpt), recognition_preload=True)
    monkeypatch.setattr(md, "get_recognition_status", lambda s: {"available": True})
    monkeypatch.setattr(md, "_ensure_vendor_on_path", lambda d: None)
    calls = {"n": 0, "fail": False}

    def load(path, device="cpu", preprocessing="model_card"):
        calls["n"] += 1
        if calls["fail"]:
            raise ValueError("checkpoint SHA-256 mismatch")
        return types.SimpleNamespace(model_id="fake@rev:card")

    pkg = types.ModuleType("member1_dhanushya")
    rec = types.ModuleType("member1_dhanushya.recognition")
    rec.load_recognition_model = load
    monkeypatch.setitem(sys.modules, "member1_dhanushya", pkg)
    monkeypatch.setitem(sys.modules, "member1_dhanushya.recognition", rec)
    md.clear_recognition_cache()
    yield settings, calls
    md.clear_recognition_cache()


def test_preload_loads_once_and_reports_loaded(fake_engine):
    settings, calls = fake_engine
    assert md.model_load_state()["state"] == "idle"
    md.preload_model_in_background(settings).join(10)
    assert md.model_load_state()["state"] == "loaded"
    assert md.preload_model_in_background(settings) is None  # already loaded: no second thread
    md._load_or_get_model(settings)
    assert calls["n"] == 1  # cached in process


def test_failed_load_is_reported(fake_engine):
    settings, calls = fake_engine
    calls["fail"] = True
    md.preload_model_in_background(settings).join(10)
    state = md.model_load_state()
    assert state["state"] == "failed" and state["error"] == "ValueError"


def test_capabilities_expose_model_state(fake_engine, monkeypatch):
    settings, _ = fake_engine
    monkeypatch.setattr(
        id_service,
        "get_recognition_status",
        lambda s: {"available": True, "model_name": "m", "model_revision": "r", "checkpoint_sha256": "x",
                   "preprocessing": "model_card", "gallery_cache_enabled": True},
    )
    client = TestClient(create_app(Settings(_env_file=None)))
    assert client.get("/api/v1/identifications/capabilities").json()["model_state"] == "idle"
    md.preload_model_in_background(settings).join(10)
    body = client.get("/api/v1/identifications/capabilities").json()
    assert body["model_state"] == "loaded" and body["model_load_seconds"] is not None


def test_preload_skipped_when_unavailable(monkeypatch):
    monkeypatch.setattr(md, "get_recognition_status", lambda s: {"available": False})
    assert md.preload_model_in_background(Settings(_env_file=None)) is None
