# Backend architecture (Phase 3.1, updated 3.2)

FastAPI + SQLAlchemy 2.0 (sync, psycopg 3) + Alembic, on Supabase PostgreSQL and a private Supabase Storage bucket.
Alembic head: `4fa9f00adf31`. Phase 3.1 added no migrations.

## Layout

```
backend/app/
  main.py                  create_app() factory + module-level `app` (uvicorn app.main:app)
  config.py                compatibility re-export of app.core.config (old import path)
  core/
    config.py              Settings (pydantic-settings, reads backend/.env), API_V1_PREFIX
    logging.py             configure_logging(); request id injected into every log record
    errors.py              AppError, error envelope, exception -> HTTP mapping
    middleware.py          RequestContextMiddleware: X-Request-ID, access log, last-resort 500
  api/
    health.py              GET /health, GET /health/db (unversioned)
    deps.py                DbSession, Storage, Paging dependencies
    v1/
      router.py            api_router (prefix /api/v1); includes every endpoints module
      endpoints/           zebras, images, gallery, sightings, identifications
  database/
    base.py                Declarative Base, naming convention, UUID/timestamp mixins
    session.py             lazy engine, session factory, get_db, session_scope, dispose_engine
  models/                  ORM models (Phase 2)
  schemas/                 Pydantic request/response schemas (Phase 2)
  repositories/            data access; flush, never commit (Phase 2)
  services/                business workflows: zebras, images, gallery, sightings,
                           identifications, image_storage (upload/delete compensation)
  integrations/            external systems (Supabase Storage now; ML later)
```

`app/database/` is kept where it was (Alembic, tests and repositories import it). It is not duplicated under `core/`.

## Layer rules

| Layer | May import | Owns |
|---|---|---|
| `api/` | services, schemas, deps | HTTP shapes, status codes, docs |
| `services/` | repositories, integrations, schemas | business rules, `db.commit()`, storage compensation |
| `repositories/` | models, schemas | queries, `flush()`; never `commit()` |
| `integrations/` | config | external I/O; no DB access |
| `models/`, `schemas/` | database.base | structure only |

Transactions (changed in 3.2): the **service** function is the unit of work and calls `db.commit()`, because
uploads/deletes must coordinate the commit with Storage (a failed commit deletes the uploaded object; an object is
deleted only after its row is committed away). Routers stay thin. If anything raises, `get_db` rolls back; the
session is always closed.

## URL map

| Path | Purpose |
|---|---|
| `GET /health` | liveness, no DB |
| `GET /health/db` | `select version()`; 200 or 503 with `{status, error, detail}` (no internal details) |
| `GET /api/v1/` | API version info |
| `/api/v1/zebras`, `/images`, `/gallery`, `/sightings`, `/identifications` | business APIs, see `docs/API.md` |
| `GET /docs`, `/openapi.json`, `/redoc` | API docs |

Health probes stay unversioned: they are operational, not part of the public API contract, and the frontend status panel already calls them.

## Errors

Every error except `/health/db` uses one envelope:

```json
{"error": {"code": "not_found", "message": "Zebra … not found", "details": null, "request_id": "…"}}
```

`details` is present only when set. `request_id` equals the `X-Request-ID` response header.

| Exception | Status | `code` |
|---|---|---|
| `AppError` (and subclasses) | its `status_code` | its `code` |
| `ServiceUnavailableError` | 503 | `service_unavailable` / custom |
| `HTTPException` | its status | `not_found`, `method_not_allowed`, … |
| `RequestValidationError` | 422 | `validation_error` (details: `loc`, `msg`, `type`; input not echoed) |
| `repositories.base.NotFoundError` | 404 | `not_found` |
| `repositories.base.DomainRuleError` | 422 | `domain_rule_violation` |
| `sqlalchemy IntegrityError` | 409 | `integrity_conflict` (generic message; DB text logged only) |
| `sqlalchemy OperationalError`, `DatabaseNotConfiguredError` | 503 | `database_unavailable` |
| `ConflictError` / `InvalidReferenceError` | 409 / 422 | per raise site (see `docs/API.md`) |
| pydantic `ValidationError` raised in a service | 422 | `validation_error` |
| `ImageTooLargeError` | 413 | `image_too_large` |
| `UnsupportedImageTypeError` | 415 | `unsupported_image_type` |
| `ImageValidationError` (empty, corrupt, type mismatch) | 422 | `invalid_image` |
| `StorageNotFoundError` | 404 | `storage_object_not_found` |
| `StorageError` | 502 | `storage_error` |
| any other exception | 500 | `internal_error` (logged with traceback) |

Raise `AppError("message", status_code=…, code="…")` from services for new cases. The message goes to the client: keep internal details out of it.

## Middleware order

`CORSMiddleware` (outer) → `RequestContextMiddleware` → FastAPI exception handlers → routes.
CORS is outermost so 500 responses also carry CORS headers.

## Request ids and logging

- Incoming `X-Request-ID` is reused if it matches `[A-Za-z0-9._-]{1,64}`; otherwise a UUID4 hex is generated.
- The `app.*` logger tree logs `... [req=<id>] message` at `LOG_LEVEL`. Uvicorn keeps its own handlers.
- Access log line: method, path (no query string), status, duration.

## CORS

- Origins come from `CORS_ORIGINS` (comma-separated). `*` is rejected at startup because credentials are allowed.
- Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS. Headers: Authorization, Content-Type, X-Request-ID. `X-Request-ID` is exposed.

## Configuration

New in 3.1: `APP_VERSION` (default `0.1.0`), `LOG_LEVEL` (default `INFO`). All others unchanged; see `backend/.env.example`.

## Dependencies (`app/api/deps.py`)

- `DbSession`: `Annotated[Session, Depends(get_db)]`. 503 `database_unavailable` when `DATABASE_URL` is empty.
- `Storage`: process-wide `SupabaseStorage`. 503 `storage_not_configured` when URL/key are missing.
- On shutdown the lifespan closes the Storage HTTP client and disposes the engine pool.

## Adding a resource

1. `app/api/v1/endpoints/<name>.py` with `router = APIRouter(prefix=..., tags=[...])`; add the module to the
   tuple in `app/api/v1/router.py`.
2. Business rules and `db.commit()` in `app/services/<name>.py`; queries in `app/repositories/`.
3. Document errors with `responses=error_responses(...)` from `app.core.errors`.

## Tests

- `tests/unit/test_app_foundation.py`: routing, versioning, docs, error envelope, exception mapping, request ids, CORS, `get_db` rollback/close, settings validation. No network.
- `tests/integration/test_api_foundation.py`: live `/health/db` and `DbSession` against Supabase (skipped without `DATABASE_URL`).

- Phase 3.2 API tests (`tests/integration/test_api_*.py`) run against the real database inside the rolled-back
  `db` session (`api` fixture) with an in-memory `FakeStorage` (failure switches). `test_api_storage_live.py`
  uses the real private bucket and deletes every object it uploads.
- Lint: `.venv/bin/ruff check app tests` (`ruff.toml`).

## Known gaps

- No authentication or ownership yet; `Authorization` header is only allowed by CORS.
- `/health/db` keeps its pre-3.1 body shape for frontend compatibility, not the error envelope.
