"""Foundation checks against the real Supabase PostgreSQL (skipped without DATABASE_URL)."""
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import DbSession
from app.main import create_app


def test_health_db_live(engine):
    with TestClient(create_app()) as c:
        resp = c.get("/health/db")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok" and body["server_version"].startswith("PostgreSQL")


def test_db_session_dependency_live(engine):
    app = create_app()

    def handler(db: DbSession):
        revision = db.execute(text("select version_num from alembic_version")).scalar_one()
        return {"revision": revision}

    app.add_api_route("/_t/revision", handler, methods=["GET"])
    with TestClient(app) as c:
        resp = c.get("/_t/revision")
    assert resp.status_code == 200
    assert resp.json() == {"revision": "4fa9f00adf31"}
