import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.deps import DbSession, Paging, Storage
from app.core.errors import AppError, error_responses
from app.models import ImageKind
from app.schemas import CropBox, ImageAssetResponse, Page, SignedUrlResponse
from app.services import images as image_service

router = APIRouter(prefix="/images", tags=["images"])


def _json_object(raw: str | None, field: str) -> dict | None:
    if raw is None or raw == "":
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None
    if not isinstance(value, dict):
        raise AppError(f"{field} must be a JSON object", status_code=422, code="validation_error", details={"field": field})
    return value


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ImageAssetResponse,
    summary="Upload an image",
    responses=error_responses(409, 413, 415, 422, 502, 503),
)
def upload_image(
    db: DbSession,
    storage: Storage,
    file: Annotated[UploadFile, File(description="JPEG, PNG or WebP, at most 10 MB")],
    kind: Annotated[ImageKind, Form(description="query: photo to identify; reference: known zebra; crop: region of another image")],
    captured_at: Annotated[datetime | None, Form()] = None,
    uploaded_by: Annotated[str | None, Form(max_length=120)] = None,
    source_image_id: Annotated[uuid.UUID | None, Form(description="crop only: the image it was cut from")] = None,
    crop_bbox: Annotated[str | None, Form(description='crop only, JSON: {"x":0,"y":0,"width":256,"height":256}')] = None,
    metadata: Annotated[str | None, Form(description="optional JSON object")] = None,
):
    """`multipart/form-data`. The bytes go to the private Storage bucket; PostgreSQL stores
    metadata only. Type is checked from the file content, not the file name.
    Width/height are read from the image. 413 when larger than the limit, 415 for other
    formats, 409 `duplicate_image` when identical bytes of the same kind exist."""
    max_bytes = storage.max_upload_bytes
    content = file.file.read(max_bytes + 1)  # never read more than limit + 1 into memory
    bbox = _json_object(crop_bbox, "crop_bbox")
    return image_service.upload_image(
        db,
        storage,
        kind=kind,
        content=content,
        content_type=file.content_type or "",
        captured_at=captured_at,
        uploaded_by=uploaded_by,
        source_image_id=source_image_id,
        crop_bbox=CropBox.model_validate(bbox) if bbox is not None else None,
        metadata=_json_object(metadata, "metadata"),
    )


@router.get("", response_model=Page[ImageAssetResponse], summary="List images", responses=error_responses(422))
def list_images(
    db: DbSession,
    page: Paging,
    kind: ImageKind | None = None,
    sha256: Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")] = None,
):
    """Newest first."""
    return image_service.list_images(db, kind=kind, sha256=sha256, limit=page.limit, offset=page.offset)


@router.get(
    "/{image_id}", response_model=ImageAssetResponse, summary="Get image metadata", responses=error_responses(404, 422)
)
def get_image(db: DbSession, image_id: uuid.UUID):
    return image_service.get_image(db, image_id)


@router.get(
    "/{image_id}/url",
    response_model=SignedUrlResponse,
    summary="Get a temporary signed URL",
    responses=error_responses(404, 422, 502, 503),
)
def get_image_url(
    db: DbSession,
    storage: Storage,
    image_id: uuid.UUID,
    expires_in: Annotated[int | None, Query(ge=1, le=3600, description="Seconds; default 60")] = None,
):
    """Short-lived read URL for the private object. Do not store it."""
    return image_service.signed_url(db, storage, image_id, expires_in)


@router.delete(
    "/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an image",
    responses=error_responses(404, 409, 422, 503),
)
def delete_image(db: DbSession, storage: Storage, image_id: uuid.UUID) -> None:
    """Refused with 409 `image_in_use` while crops, gallery entries, identification runs,
    candidates or sightings reference it. Deletes the row, then the Storage object."""
    image_service.delete_image(db, storage, image_id)
