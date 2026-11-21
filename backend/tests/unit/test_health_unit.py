"""/health/db must not leak connection details (DB mocked, no network)."""
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api import health
from app.main import app

SECRET_HOST = "aws-0-region.pooler.supabase.com"
SECRET_USER = "postgres.projectref"


def test_db_health_failure_hides_details(monkeypatch):
    def broken_engine():
        raise OperationalError(
            "connect", {}, Exception(f'connection to server at "{SECRET_HOST}" failed: FATAL: password authentication failed for user "{SECRET_USER}"')
        )

    monkeypatch.setattr(health, "get_engine", broken_engine)
    resp = TestClient(app).get("/health/db")
    assert resp.status_code == 503
    body = resp.text
    assert SECRET_HOST not in body and SECRET_USER not in body and "password" not in body
    assert resp.json()["status"] == "error"


def test_liveness_needs_no_db(monkeypatch):
    monkeypatch.setattr(health, "get_engine", lambda: (_ for _ in ()).throw(RuntimeError("no db")))
    assert TestClient(app).get("/health").json()["status"] == "ok"
