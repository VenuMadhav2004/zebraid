import logging
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.database.session import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


@router.get("/health/db")
def health_db() -> JSONResponse:
    start = time.perf_counter()
    try:
        engine = get_engine()
        with engine.connect() as conn:
            version = conn.execute(text("select version()")).scalar_one()
            database = conn.execute(text("select current_database()")).scalar_one()
        return JSONResponse(
            {
                "status": "ok",
                "database": database,
                "server_version": str(version).split(",")[0],
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
            }
        )
    except Exception as exc:  # surface connection problems without crashing
        # Full error (may include host/user names) goes to server logs only.
        logger.warning("database health check failed: %s", exc)
        configured = bool(get_settings().database_url)
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "error": type(exc).__name__,
                "detail": "database unreachable" if configured else "database not configured",
            },
        )
