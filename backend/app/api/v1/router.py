"""Aggregates all /api/v1 routers. Each endpoints module defines its own prefix and tags."""
from fastapi import APIRouter

from app.api.v1.endpoints import analyses, assistant, gallery, hide_scans, identifications, images, sightings, zebras
from app.core.config import API_V1_PREFIX, get_settings

api_router = APIRouter(prefix=API_V1_PREFIX)


@api_router.get("/", tags=["meta"], summary="API version info")
def api_info() -> dict:
    settings = get_settings()
    return {"name": settings.app_name, "api_version": "v1", "app_version": settings.app_version}


for module in (zebras, images, gallery, sightings, identifications, analyses, assistant, hide_scans):
    api_router.include_router(module.router)
