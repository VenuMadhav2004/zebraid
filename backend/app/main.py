"""FastAPI application factory.

Layout:
  /health, /health/db   unversioned operational probes (used by the frontend status panel)
  /api/v1/...           versioned public API
  /docs, /openapi.json  Swagger UI and schema
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import close_storage, get_storage
from app.api.health import router as health_router
from app.api.v1 import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.database.session import dispose_engine
from app.integrations.recognition import preload_model_in_background
from app.services.stripe_analyses import AnalysisDispatcher


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    dispatcher = getattr(app.state, "analysis_dispatcher", None)
    if dispatcher is not None:
        await dispatcher.start()
    settings = get_settings()
    if settings.recognition_preload:
        # Background thread: the API serves requests immediately; identification waits for the
        # same lock if it arrives before the weights are ready.
        preload_model_in_background(settings)
    try:
        yield
    finally:
        if dispatcher is not None:
            await dispatcher.stop()
        close_storage()
        dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.state.analysis_dispatcher = AnalysisDispatcher(settings, get_storage)

    register_exception_handlers(app)

    # Added first = innermost. CORS wraps RequestContext so error responses keep CORS headers.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.include_router(health_router)
    app.include_router(api_router)

    @app.get("/", tags=["meta"])
    def root() -> dict:
        return {"name": settings.app_name, "docs": "/docs", "health": "/health", "api": api_router.prefix}

    return app


app = create_app()
