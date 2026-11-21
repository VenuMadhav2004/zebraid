"""Image upload, listing, signed URLs and deletion.

Uploads: validate bytes -> decode check (Pillow) -> duplicate check -> upload
object + insert row (image_storage.store_image) -> commit. A failed commit
deletes the uploaded object again.
Deletes: refuse while referenced -> delete row -> commit -> delete object.
"""
from __future__ import annotations

import io
import logging
import uuid
import warnings
from datetime import datetime

from PIL import ExifTags, Image
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, InvalidReferenceError
from app.integrations.supabase_storage import ImageValidationError, SupabaseStorage, sniff_image_type, validate_image
from app.models import ImageAsset, ImageKind
from app.repositories import images as image_repo
from app.repositories.base import NotFoundError
from app.schemas import CropBox, ImageAssetResponse, Page, SignedUrlResponse
from app.services import image_storage

logger = logging.getLogger(__name__)

_PIL_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
_EXIF_ORIENTATION_TAG = int(ExifTags.Base.Orientation)
# EXIF orientations 5-8 apply a 90/270-degree rotation or transpose, swapping width and height.
_EXIF_TRANSPOSE_ORIENTATIONS = frozenset({5, 6, 7, 8})


def _exif_oriented_size(im: Image.Image) -> tuple[int, int]:
    """Return display (width, height) matching ImageOps.exif_transpose / browser rendering."""
    width, height = im.size
    try:
        orientation = im.getexif().get(_EXIF_ORIENTATION_TAG)
    except Exception:
        orientation = None
    if orientation in _EXIF_TRANSPOSE_ORIENTATIONS:
        return height, width
    return width, height


def inspect_image(content: bytes) -> tuple[int, int]:
    """Return EXIF-oriented (width, height) after checking the bytes decode as the sniffed format.
    Rejects decompression bombs (more than Pillow's MAX_IMAGE_PIXELS). Stored bytes are untouched."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as im:
                fmt = im.format
                im.verify()
            with Image.open(io.BytesIO(content)) as im:
                size = _exif_oriented_size(im)
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ImageValidationError("image pixel dimensions are too large") from None
    except Exception:
        raise ImageValidationError("file is not a readable image") from None
    if _PIL_FORMATS.get(fmt or "") != sniff_image_type(content):
        raise ImageValidationError("image data does not match its file signature")
    return size


def upload_image(
    db: Session,
    storage: SupabaseStorage,
    *,
    kind: ImageKind,
    content: bytes,
    content_type: str,
    captured_at: datetime | None = None,
    uploaded_by: str | None = None,
    source_image_id: uuid.UUID | None = None,
    crop_bbox: CropBox | None = None,
    metadata: dict | None = None,
) -> ImageAsset:
    content_type = validate_image(content, content_type, max_bytes=storage.max_upload_bytes)
    width, height = inspect_image(content)

    is_crop = kind == ImageKind.CROP
    if is_crop != (source_image_id is not None and crop_bbox is not None):
        raise AppError(
            "crop images need source_image_id and crop_bbox; other kinds must not set them",
            status_code=422,
            code="validation_error",
        )
    if source_image_id is not None:
        try:
            image_repo.get_image_asset(db, source_image_id)
        except NotFoundError:
            raise InvalidReferenceError("source image not found", details={"field": "source_image_id"}) from None

    sha256 = image_storage.sha256_hex(content)
    duplicate = image_repo.find_duplicate(db, sha256, kind)
    if duplicate is not None:
        raise ConflictError(
            f"an identical {kind.value} image already exists",
            code="duplicate_image",
            details={"existing_image_id": str(duplicate.id)},
        )

    image = image_storage.store_image(
        db,
        storage,
        kind=kind,
        content=content,
        content_type=content_type,
        width=width,
        height=height,
        captured_at=captured_at,
        uploaded_by=uploaded_by,
        source_image_id=source_image_id,
        crop_bbox=crop_bbox,
        metadata=metadata,
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        image_storage.discard_objects(storage, [image.storage_path])
        raise
    return image


def list_images(
    db: Session, *, kind: ImageKind | None, sha256: str | None, limit: int, offset: int
) -> Page[ImageAssetResponse]:
    items = image_repo.list_image_assets(db, kind=kind, sha256=sha256, limit=limit, offset=offset)
    return Page[ImageAssetResponse](
        items=[ImageAssetResponse.model_validate(i) for i in items],
        total=image_repo.count_image_assets(db, kind=kind, sha256=sha256),
        limit=limit,
        offset=offset,
    )


def get_image(db: Session, image_id: uuid.UUID) -> ImageAsset:
    return image_repo.get_image_asset(db, image_id)


def _check_ttl(storage: SupabaseStorage, expires_in: int | None) -> None:
    if expires_in is not None and not 1 <= expires_in <= storage.max_ttl:
        raise AppError(
            f"expires_in must be between 1 and {storage.max_ttl} seconds", status_code=422, code="validation_error"
        )


def _check_bucket(storage: SupabaseStorage, image: ImageAsset) -> None:
    if image.storage_bucket != storage.bucket:
        raise ConflictError("image is stored in a bucket this server does not serve", code="storage_bucket_mismatch")


def signed_url(db: Session, storage: SupabaseStorage, image_id: uuid.UUID, expires_in: int | None) -> SignedUrlResponse:
    _check_ttl(storage, expires_in)
    image = image_repo.get_image_asset(db, image_id)
    _check_bucket(storage, image)
    signed = storage.signed_url(image.storage_path, expires_in)
    return SignedUrlResponse(url=signed.url, expires_in=signed.expires_in, expires_at=signed.expires_at)


def signed_urls(
    storage: SupabaseStorage, images: list[ImageAsset], expires_in: int | None
) -> dict[uuid.UUID, SignedUrlResponse | None]:
    """One Storage request for many images. Missing objects map to None."""
    _check_ttl(storage, expires_in)
    servable = [i for i in images if i.storage_bucket == storage.bucket]
    signed = storage.signed_urls([i.storage_path for i in servable], expires_in)
    result: dict[uuid.UUID, SignedUrlResponse | None] = {i.id: None for i in images}
    for image in servable:
        s = signed.get(image.storage_path)
        if s is not None:
            result[image.id] = SignedUrlResponse(url=s.url, expires_in=s.expires_in, expires_at=s.expires_at)
    return result


def delete_image(db: Session, storage: SupabaseStorage, image_id: uuid.UUID) -> None:
    image = image_repo.get_image_asset(db, image_id)
    _check_bucket(storage, image)
    in_use = {k: v for k, v in image_repo.usage_counts(db, image_id).items() if v}
    if in_use:
        raise ConflictError("image is still referenced by other records", code="image_in_use", details=in_use)
    path = image_storage.remove_image(db, image_id)
    db.commit()
    # After commit: a failed object delete leaves an orphan object (logged), never a dangling row.
    image_storage.discard_objects(storage, [path])
