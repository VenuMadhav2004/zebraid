"""Unit tests for MegaDescriptor-L-384 v1 CPU recognition adapter & service guards."""
from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.integrations.recognition import (
    CHECKPOINT_SHA256,
    MODEL_ID,
    MODEL_REVISION,
    get_recognition_status,
)
from app.schemas import IdentificationSubmitRequest
from app.services import identifications as id_service


def test_recognition_status_unavailable_when_path_unset(monkeypatch):
    monkeypatch.delenv("STRIPECODE_MODEL_PATH", raising=False)
    cfg = Settings(_env_file=None, recognition_model_path="")
    st = get_recognition_status(cfg)
    assert st["available"] is False
    assert st["model_name"] == MODEL_ID
    assert st["model_revision"] == MODEL_REVISION
    assert st["checkpoint_sha256"] == CHECKPOINT_SHA256
    assert "RECOGNITION_MODEL_PATH" in (st["reason"] or "")


def test_recognition_status_unavailable_when_file_missing(tmp_path: Path):
    cfg = Settings(_env_file=None, recognition_model_path=str(tmp_path / "missing.bin"))
    st = get_recognition_status(cfg)
    assert st["available"] is False
    assert "not found" in (st["reason"] or "").lower()


def test_recognition_status_rejects_invalid_preprocessing():
    cfg = Settings(_env_file=None, recognition_model_path="/tmp/x.bin", recognition_preprocessing="invalid")
    st = get_recognition_status(cfg)
    assert st["available"] is False
    assert "RECOGNITION_PREPROCESSING" in (st["reason"] or "")


def test_identification_submit_request_validation():
    req = IdentificationSubmitRequest(query_image_id=uuid.uuid4(), top_k=5, requested_by="researcher")
    assert req.top_k == 5

    with pytest.raises(ValidationError):
        IdentificationSubmitRequest(query_image_id=uuid.uuid4(), top_k=0)
    with pytest.raises(ValidationError):
        IdentificationSubmitRequest(query_image_id=uuid.uuid4(), top_k=21)
    with pytest.raises(ValidationError):
        IdentificationSubmitRequest(query_image_id=uuid.uuid4(), extra_field=1)


def test_submit_identification_run_refuses_when_unavailable(monkeypatch):
    monkeypatch.delenv("STRIPECODE_MODEL_PATH", raising=False)
    cfg = Settings(_env_file=None, recognition_model_path="")
    with pytest.raises(ServiceUnavailableError) as exc:
        id_service.submit_identification_run(
            db=SimpleNamespace(),  # type: ignore[arg-type]
            storage=SimpleNamespace(),  # type: ignore[arg-type]
            settings=cfg,
            body=IdentificationSubmitRequest(query_image_id=uuid.uuid4()),
        )
    assert exc.value.code == "recognition_unavailable"
