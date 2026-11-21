"""Phase 3.1 foundation: routing, versioning, error envelope, CORS, request ids,
DB session dependency and settings. No network: DB and Storage are mocked."""
import uuid

import pytest
from fastapi import Query
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError

from app.api import deps, health
from app.core.config import API_V1_PREFIX, Settings
from app.core.errors import AppError
from app.database import session as db_session
from app.database.session import DatabaseNotConfiguredError
from app.integrations.supabase_storage import ImageValidationError, StorageError, StorageNotFoundError
from app.main import create_app
from app.repositories.base import DomainRuleError, NotFoundError

ORIGIN = "http://localhost:5173"
SECRET = "postgres.secretref@db.internal"


def _settings(**kw) -> Settings:
    base = dict(_env_file=None, database_url="", supabase_url="", supabase_service_role_key="", cors_origins=ORIGIN)
    base.update(kw)
    return Settings(**base)


class Item(BaseModel):
    name: str
    count: int


def _raiser(exc: Exception):
    def handler():
        raise exc

    return handler


@pytest.fixture
def app():
    app = create_app(_settings())
    routes = {
        "/_t/app-error": AppError("custom failure", status_code=418, code="teapot", details={"hint": "x"}),
        "/_t/not-found": NotFoundError("Zebra 123 not found"),
        "/_t/domain": DomainRuleError("cannot complete a pending run"),
        "/_t/integrity": IntegrityError("INSERT ...", {}, Exception(f'duplicate key "uq_zebras_code" {SECRET}')),
        "/_t/operational": OperationalError("connect", {}, Exception(f"could not connect to {SECRET}")),
        "/_t/no-db": DatabaseNotConfiguredError("DATABASE_URL is not configured"),
        "/_t/bad-image": ImageValidationError("unsupported content type image/gif"),
        "/_t/storage": StorageError(f"bucket error {SECRET}", 500),
        "/_t/storage-404": StorageNotFoundError("Object not found", 404),
        "/_t/crash": RuntimeError(f"boom {SECRET}"),
    }
    for path, exc in routes.items():
        app.add_api_route(path, _raiser(exc), methods=["GET"])

    def validated(limit: int = Query(..., ge=1, le=100)):
        return {"limit": limit}

    def create_item(item: Item):
        return item

    app.add_api_route("/_t/validated", validated, methods=["GET"])
    app.add_api_route("/_t/items", create_item, methods=["POST"])
    return app


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _error(resp, status: int, code: str) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()["error"]
    assert body["code"] == code
    assert body["request_id"] == resp.headers["X-Request-ID"]
    return body


# -- routing / docs -----------------------------------------------------------
def test_health_endpoints_unversioned_and_preserved(client, monkeypatch):
    assert client.get("/health").json()["status"] == "ok"
    monkeypatch.setattr(health, "get_engine", _raiser(DatabaseNotConfiguredError("x")))
    resp = client.get("/health/db")
    # /health/db keeps its own body shape (the frontend status panel reads it).
    assert resp.status_code == 503
    body = resp.json()
    assert set(body) == {"status", "error", "detail"}
    assert body["status"] == "error" and body["error"] == "DatabaseNotConfiguredError"


def test_api_v1_prefix(client):
    resp = client.get(f"{API_V1_PREFIX}/")
    assert resp.status_code == 200
    assert resp.json()["api_version"] == "v1"


def test_docs_and_openapi_available(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/health/db", "/api/v1/"} <= set(paths)


def test_root(client):
    assert client.get("/").json()["api"] == "/api/v1"


# -- error envelope -----------------------------------------------------------
def test_unknown_route_404_envelope(client):
    _error(client.get("/api/v1/does-not-exist"), 404, "not_found")


def test_method_not_allowed_envelope(client):
    _error(client.post("/health"), 405, "method_not_allowed")


def test_query_validation_envelope(client):
    body = _error(client.get("/_t/validated?limit=0"), 422, "validation_error")
    assert body["details"][0]["loc"] == ["query", "limit"]


def test_body_validation_does_not_echo_input(client):
    resp = client.post("/_t/items", json={"name": "ok", "count": "not-a-number-" + SECRET})
    body = _error(resp, 422, "validation_error")
    assert body["details"][0]["loc"] == ["body", "count"]
    assert SECRET not in resp.text


def test_malformed_json_body(client):
    resp = client.post("/_t/items", content=b"{bad json", headers={"Content-Type": "application/json"})
    _error(resp, 422, "validation_error")


@pytest.mark.parametrize(
    "path,status,code",
    [
        ("/_t/app-error", 418, "teapot"),
        ("/_t/not-found", 404, "not_found"),
        ("/_t/domain", 422, "domain_rule_violation"),
        ("/_t/integrity", 409, "integrity_conflict"),
        ("/_t/operational", 503, "database_unavailable"),
        ("/_t/no-db", 503, "database_unavailable"),
        ("/_t/bad-image", 422, "invalid_image"),
        ("/_t/storage", 502, "storage_error"),
        ("/_t/storage-404", 404, "storage_object_not_found"),
        ("/_t/crash", 500, "internal_error"),
    ],
)
def test_exception_mapping(client, path, status, code):
    resp = client.get(path)
    _error(resp, status, code)
    assert SECRET not in resp.text


def test_app_error_details_and_safe_messages(client):
    assert client.get("/_t/app-error").json()["error"]["details"] == {"hint": "x"}
    assert client.get("/_t/domain").json()["error"]["message"] == "cannot complete a pending run"
    assert client.get("/_t/crash").json()["error"]["message"] == "Internal server error"


# -- request id -----------------------------------------------------------------
def test_request_id_generated(client):
    rid = client.get("/health").headers["X-Request-ID"]
    assert uuid.UUID(hex=rid)


def test_request_id_propagated(client):
    assert client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"] == "abc-123"


def test_request_id_rejects_unsafe_value(client):
    rid = client.get("/health", headers={"X-Request-ID": "x" * 65}).headers["X-Request-ID"]
    assert rid != "x" * 65 and uuid.UUID(hex=rid)


# -- CORS -------------------------------------------------------------------------
def test_cors_preflight_allowed_origin(client):
    resp = client.options(
        "/api/v1/", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST",
                             "Access-Control-Request-Headers": "content-type"}
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == ORIGIN
    assert resp.headers["access-control-allow-credentials"] == "true"


def test_cors_disallowed_origin(client):
    resp = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers


def test_cors_headers_on_500(client):
    resp = client.get("/_t/crash", headers={"Origin": ORIGIN})
    assert resp.status_code == 500
    assert resp.headers["access-control-allow-origin"] == ORIGIN
    assert "x-request-id" in resp.headers["access-control-expose-headers"].lower()


# -- DB session dependency ------------------------------------------------------
class FakeSession:
    def __init__(self):
        self.rolled_back = self.closed = False

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture
def fake_session(monkeypatch):
    s = FakeSession()
    monkeypatch.setattr(db_session, "get_session_factory", lambda: (lambda: s))
    return s


def test_db_dependency_closes_on_success(app, fake_session):
    def handler(db: deps.DbSession):
        assert db is fake_session
        return {"ok": True}

    app.add_api_route("/_t/db-ok", handler, methods=["GET"])
    with TestClient(app) as c:
        assert c.get("/_t/db-ok").json() == {"ok": True}
    assert fake_session.closed and not fake_session.rolled_back


def test_db_dependency_rolls_back_on_error(app, fake_session):
    def handler(db: deps.DbSession):
        raise DomainRuleError("nope")

    app.add_api_route("/_t/db-err", handler, methods=["GET"])
    with TestClient(app) as c:
        assert c.get("/_t/db-err").status_code == 422
    assert fake_session.rolled_back and fake_session.closed


def test_db_dependency_without_database_url(app, monkeypatch):
    monkeypatch.setattr(db_session, "_engine", None)
    monkeypatch.setattr(db_session, "get_settings", lambda: _settings())

    def handler(db: deps.DbSession):
        return {}

    app.add_api_route("/_t/db-none", handler, methods=["GET"])
    with TestClient(app) as c:
        _error(c.get("/_t/db-none"), 503, "database_unavailable")


def test_storage_dependency_unconfigured(app, monkeypatch):
    monkeypatch.setattr(deps, "_storage", None)
    monkeypatch.setattr(deps, "get_settings", lambda: _settings())

    def handler(storage: deps.Storage):
        return {}

    app.add_api_route("/_t/storage-dep", handler, methods=["GET"])
    with TestClient(app) as c:
        _error(c.get("/_t/storage-dep"), 503, "storage_not_configured")


# -- settings -------------------------------------------------------------------------
def test_cors_wildcard_rejected():
    with pytest.raises(ValidationError):
        _settings(cors_origins="*")


def test_cors_origin_list_parsing():
    assert _settings(cors_origins=" http://a.test , ,http://b.test").cors_origin_list == ["http://a.test", "http://b.test"]


def test_log_level_validation():
    assert _settings(log_level="debug").log_level == "DEBUG"
    with pytest.raises(ValidationError):
        _settings(log_level="loud")


@pytest.mark.parametrize(
    "url,expected",
    [
        ("postgres://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql+psycopg://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
    ],
)
def test_sqlalchemy_url_normalised(url, expected):
    assert _settings(database_url=url).sqlalchemy_url == expected


def test_legacy_config_import_path():
    import app.config as legacy
    import app.core.config as core

    assert legacy.get_settings is core.get_settings and legacy.Settings is core.Settings
