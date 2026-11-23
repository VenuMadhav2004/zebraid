"""Read-only serving, dataset import, and registry management for authorized 3D hide scans."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.errors import AppError, error_responses
from app.services import hide_scan_importer as importer
from app.services import hide_scans as scan_service

router = APIRouter(prefix="/hide-scans", tags=["3d-hide-scans"])

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_MEDIA = {"obj": "text/plain", "mtl": "text/plain"}


class HideScanFileRead(BaseModel):
    name: str
    role: str
    size_bytes: int
    sha256: str | None = None


class HideScanRead(BaseModel):
    id: str
    label: str
    total_bytes: int
    model_format: str = "obj"
    dataset_source: str = "local"
    import_status: str = "discovered"
    validation_status: str = "valid"
    registered_at: str | None = None
    sha256: str | None = None
    mtl_file: str | None = None
    texture_files: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    files: list[HideScanFileRead]


class HideScanListResponse(BaseModel):
    available: bool
    reason: str | None = None
    unsupported_count: int = 0
    incomplete_count: int = 0
    scans: list[HideScanRead]


class HideScanImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drive_folder_id: str | None = Field(default=importer.DEFAULT_DRIVE_FOLDER_ID, min_length=5, max_length=128)
    source_dir: str | None = Field(default=None, max_length=500)


class HideScanImportResponse(BaseModel):
    source: str
    imported: list[str]
    skipped_existing: list[str]
    duplicates: list[dict[str, str]]
    failed: list[dict[str, Any]]
    unsupported_count: int
    registered_total: int


class HideScanRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder_name: str = Field(..., min_length=1, max_length=128)
    dataset_source: str = Field(default="manual", min_length=1, max_length=128)


def _check_client(request: Request) -> None:
    settings = get_settings()
    host = request.client.host if request.client else ""
    if not settings.hide_scans_allow_remote and host not in _LOOPBACK:
        raise AppError(
            "Private 3D scans can only be loaded through the local proxy or an SSH tunnel.",
            status_code=403,
            code="forbidden",
        )


def _to_scan_read(s: scan_service.HideScan) -> HideScanRead:
    return HideScanRead(
        id=s.id,
        label=s.label,
        total_bytes=s.total_bytes,
        model_format=s.model_format,
        dataset_source=s.dataset_source,
        import_status=s.import_status,
        validation_status=s.validation_status,
        registered_at=s.registered_at,
        sha256=s.sha256,
        mtl_file=s.mtl_file,
        texture_files=list(s.texture_files),
        notes=list(s.notes),
        files=[HideScanFileRead(name=f.name, role=f.role, size_bytes=f.size_bytes, sha256=f.sha256) for f in s.files],
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
    summary = scan_service.registry_summary(root)
    return HideScanListResponse(
        available=bool(scans),
        reason=None if scans else "No .obj scans found in the configured directory.",
        unsupported_count=summary["unsupported_count"],
        incomplete_count=summary["incomplete_count"],
        scans=[_to_scan_read(s) for s in scans.values()],
    )


@router.get(
    "/{asset_id}",
    response_model=HideScanRead,
    summary="Get metadata for one registered 3D hide scan",
    responses=error_responses(403, 404, 503),
)
def get_hide_scan(request: Request, asset_id: str):
    _check_client(request)
    scan = scan_service.get_scan_record(get_settings().hide_scans_dir, asset_id)
    return _to_scan_read(scan)


@router.post(
    "/import",
    response_model=HideScanImportResponse,
    summary="Import and register Zebra 3D models from Google Drive or a local dataset folder",
    responses=error_responses(403, 422, 503),
)
def import_hide_scans(request: Request, body: HideScanImportRequest):
    _check_client(request)
    root = scan_service.require_root(get_settings().hide_scans_dir)
    if body.source_dir:
        src = Path(body.source_dir).resolve()
        if not src.is_dir():
            raise AppError("Configured source_dir was not found.", status_code=422, code="validation_error")
        res = importer.import_from_local_directory(src, root, dataset_source="local_import")
    else:
        folder_id = (body.drive_folder_id or importer.DEFAULT_DRIVE_FOLDER_ID).strip()
        try:
            res = importer.import_from_google_drive(folder_id, root)
        except PermissionError as exc:
            raise AppError(str(exc), status_code=422, code="drive_auth_required") from None
    return HideScanImportResponse(
        source=res["source"],
        imported=res["imported"],
        skipped_existing=res["skipped_existing"],
        duplicates=res["duplicates"],
        failed=res["failed"],
        unsupported_count=res["unsupported_count"],
        registered_total=res["registered_total"],
    )


@router.post(
    "/register",
    response_model=list[HideScanRead],
    status_code=status.HTTP_201_CREATED,
    summary="Validate and register a scan subfolder already inside HIDE_SCANS_DIR",
    responses=error_responses(403, 404, 422, 503),
)
def register_hide_scan(request: Request, body: HideScanRegisterRequest):
    _check_client(request)
    hide_dir = get_settings().hide_scans_dir
    entries = scan_service.register_scan_folder(hide_dir, body.folder_name, dataset_source=body.dataset_source)
    return [_to_scan_read(scan_service.get_scan_record(hide_dir, e["asset_id"])) for e in entries]


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Unregister a 3D hide scan from the asset registry",
    responses=error_responses(403, 404, 503),
)
def delete_hide_scan(request: Request, asset_id: str) -> None:
    _check_client(request)
    scan_service.unregister_scan(get_settings().hide_scans_dir, asset_id)


@router.get(
    "/{scan_id}/files/{file_name}",
    summary="Download one file of an authorized 3D hide scan",
    responses=error_responses(403, 404, 503),
)
def get_hide_scan_file(request: Request, scan_id: str, file_name: str):
    _check_client(request)
    f = scan_service.get_scan_file(get_settings().hide_scans_dir, scan_id, file_name)
    return FileResponse(f.path, media_type=_MEDIA.get(f.role), filename=f.name, headers={"Cache-Control": "private, max-age=3600"})
