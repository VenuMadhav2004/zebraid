"""Keeps Storage objects and image_assets rows consistent.

Order of operations:
  store:  validate -> upload object -> insert row (savepoint).
          upload fails  -> no row is written.
          insert fails  -> the uploaded object is deleted (compensation).
  remove: delete row (flush) -> caller commits -> delete object.

Remaining window: if the caller's final COMMIT fails after store_image()
returned, the caller must call discard_objects([...]) (or a future orphan
sweep must remove objects without a row). Documented in docs/STORAGE_AUDIT.md.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.integrations.supabase_storage import StorageError, SupabaseStorage, generate_storage_path, validate_image
from app.models import ImageAsset, ImageKind
from app.repositories import images as image_repo
from app.schemas import CropBox, ImageAssetCreate

logger = logging.getLogger(__name__)


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def store_image(
    db: Session,
    storage: SupabaseStorage,
    *,
    kind: ImageKind,
    content: bytes,
    content_type: str,
    width: int | None = None,
    height: int | None = None,
    captured_at: datetime | None = None,
    uploaded_by: str | None = None,
    source_image_id: uuid.UUID | None = None,
    crop_bbox: CropBox | None = None,
    metadata: dict | None = None,
    path_prefix: str | None = None,
) -> ImageAsset:
    content_type = validate_image(content, content_type, max_bytes=storage.max_upload_bytes)
    # Build + validate the row before touching Storage so bad metadata never uploads.
    path = generate_storage_path(kind, content_type, prefix=path_prefix)
    data = ImageAssetCreate(
        kind=kind,
        storage_bucket=storage.bucket,
        storage_path=path,
        content_type=content_type,
        size_bytes=len(content),
        width=width,
        height=height,
        sha256=sha256_hex(content),
        captured_at=captured_at,
        uploaded_by=uploaded_by,
        source_image_id=source_image_id,
        crop_bbox=crop_bbox,
        metadata=metadata or {},
    )

    storage.upload(path, content, content_type)  # raises -> nothing persisted

    try:
        with db.begin_nested():
            return image_repo.create_image_asset(db, data)
    except Exception:
        discard_objects(storage, [path])
        raise


def remove_image(db: Session, image_id: uuid.UUID) -> str:
    """Delete the row (flush only). Returns the object path: delete it with
    discard_objects() only AFTER the caller has committed."""
    return image_repo.delete_image_asset(db, image_id)


def discard_objects(storage: SupabaseStorage, paths: list[str]) -> None:
    """Best-effort object removal; failures are logged for an orphan sweep."""
    try:
        storage.delete(paths)
    except StorageError as exc:
        logger.error("failed to delete storage objects %s: %s", paths, exc)
