"""Read-only access to authorized 3D hide scans for the Three.js viewer."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import AppError, error_responses
from app.services import hide_scans as scan_service

router = APIRouter(prefix="/hide-scans", tags=["3d-hide-scans"])

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_MEDIA = {"obj": "text/plain", "mtl": "text/plain"}


class HideScanFileRead(BaseModel):
    name: str
    role: str
    size_bytes: int


class HideScanRead(BaseModel):
    id: str
    label: str
    total_bytes: int
    files: list[HideScanFileRead]


class HideScanListResponse(BaseModel):
    available: bool
    reason: str | None = None
    scans: list[HideScanRead]


def _check_client(request: Request) -> None:
    settings = get_settings()
    host = request.client.host if request.client else ""
    if not settings.hide_scans_allow_remote and host not in _LOOPBACK:
        raise AppError(
            "Private 3D scans can only be loaded through the local proxy or an SSH tunnel.",
            status_code=403,
            code="forbidden",
        )


@router.get("", response_model=HideScanListResponse, summary="List authorized 3D hide scans", responses=error_responses(403))
def list_hide_scans(request: Request):
    _check_client(request)
    settings = get_settings()
    try:
        root = scan_service.require_root(settings.hide_scans_dir)
    except AppError as exc:
        return HideScanListResponse(available=False, reason=exc.message, scans=[])
    scans = scan_service.discover_scans(root)
    return HideScanListResponse(
        available=bool(scans),
        reason=None if scans else "No .obj scans found in the configured directory.",
        scans=[
            HideScanRead(
                id=s.id,
                label=s.label,
                total_bytes=s.total_bytes,
                files=[HideScanFileRead(name=f.name, role=f.role, size_bytes=f.size_bytes) for f in s.files],
            )
            for s in scans.values()
        ],
    )


@router.get(
    "/{scan_id}/files/{file_name}",
    summary="Download one file of an authorized 3D hide scan",
    responses=error_responses(403, 404, 503),
)
def get_hide_scan_file(request: Request, scan_id: str, file_name: str):
    _check_client(request)
    f = scan_service.get_scan_file(get_settings().hide_scans_dir, scan_id, file_name)
    return FileResponse(f.path, media_type=_MEDIA.get(f.role), filename=f.name, headers={"Cache-Control": "private, max-age=3600"})
