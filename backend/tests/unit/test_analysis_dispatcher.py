"""Dispatcher must never leave a claimed job in 'running' when execution crashes (no DB, no network)."""
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

from app.core.config import Settings
from app.models import RunStatus
from app.services import stripe_analyses as svc


def _patch_common(monkeypatch, job, calls):
    @contextmanager
    def fake_scope():
        yield SimpleNamespace(name="session")

    monkeypatch.setattr(svc, "session_scope", fake_scope)
    monkeypatch.setattr(svc.analysis_repo, "table_exists", lambda db: True)
    monkeypatch.setattr(svc.analysis_repo, "claim_next_pending", lambda db: job)
    monkeypatch.setattr(svc.analysis_repo, "get_analysis", lambda db, jid: job)

    def fake_fail(db, jid, *, error_code, error_message):
        calls.append((jid, error_code, error_message))
        job.status = RunStatus.FAILED
        return job

    monkeypatch.setattr(svc.analysis_repo, "fail_analysis", fake_fail)


def test_crash_outside_worker_marks_job_failed(monkeypatch):
    job = SimpleNamespace(id=uuid.uuid4(), status=RunStatus.RUNNING)
    calls = []
    _patch_common(monkeypatch, job, calls)

    def boom(*a, **k):
        raise RuntimeError("source image row vanished")

    monkeypatch.setattr(svc, "execute_analysis_job", boom)
    dispatcher = svc.AnalysisDispatcher(Settings(_env_file=None), storage_factory=lambda: object())
    assert dispatcher._process_next_job() is True
    assert calls == [(job.id, "worker_error", "The analysis worker exited unexpectedly.")]
    assert job.status == RunStatus.FAILED


def test_successful_execution_does_not_fail_job(monkeypatch):
    job = SimpleNamespace(id=uuid.uuid4(), status=RunStatus.RUNNING)
    calls = []
    _patch_common(monkeypatch, job, calls)
    monkeypatch.setattr(svc, "execute_analysis_job", lambda *a, **k: None)
    dispatcher = svc.AnalysisDispatcher(Settings(_env_file=None), storage_factory=lambda: object())
    assert dispatcher._process_next_job() is True
    assert calls == []
