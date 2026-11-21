"""Application-level gallery management (which images show which zebra).

No embeddings, ML reference registration or model-gallery sync happens here;
that is added with the ML integration.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidReferenceError
from app.integrations.supabase_storage import SupabaseStorage
from app.models import GalleryEntry
from app.repositories import gallery as gallery_repo
from app.repositories import images as image_repo
from app.repositories import zebras as zebra_repo
from app.repositories.base import NotFoundError
from app.schemas import GalleryEntryCreate, GalleryEntryRegister, GalleryEntryWithImage, Page, SignedUrlResponse
from app.services import images as image_service


def _with_image(entry: GalleryEntry, url: SignedUrlResponse | None = None) -> GalleryEntryWithImage:
    out = GalleryEntryWithImage.model_validate(entry)
    out.image_url = url
    return out


def register(db: Session, zebra_id: uuid.UUID, body: GalleryEntryRegister) -> GalleryEntryWithImage:
    zebra_repo.get_zebra(db, zebra_id)  # 404 when the path zebra is missing
    try:
        image_repo.get_image_asset(db, body.image_asset_id)
    except NotFoundError:
        raise InvalidReferenceError("image not found", details={"field": "image_asset_id"}) from None
    existing = gallery_repo.get_entry_for_image(db, body.image_asset_id)
    if existing is not None:
        raise ConflictError(
            "image is already registered in a gallery",
            code="image_already_in_gallery",
            details={"gallery_entry_id": str(existing.id), "zebra_id": str(existing.zebra_id)},
        )
    entry = gallery_repo.register_gallery_entry(db, GalleryEntryCreate(zebra_id=zebra_id, **body.model_dump()))
    db.commit()
    db.refresh(entry, attribute_names=["image_asset"])
    return _with_image(entry)


def list_for_zebra(
    db: Session,
    storage: SupabaseStorage | None,
    zebra_id: uuid.UUID,
    *,
    include_inactive: bool,
    expires_in: int | None,
    limit: int,
    offset: int,
) -> Page[GalleryEntryWithImage]:
    """storage=None: no signed URLs. Otherwise one batched signing request."""
    zebra_repo.get_zebra(db, zebra_id)
    active_only = not include_inactive
    entries = gallery_repo.list_gallery_for_zebra(db, zebra_id, active_only=active_only, limit=limit, offset=offset)
    urls = image_service.signed_urls(storage, [e.image_asset for e in entries], expires_in) if storage else {}
    return Page[GalleryEntryWithImage](
        items=[_with_image(e, urls.get(e.image_asset_id)) for e in entries],
        total=gallery_repo.count_gallery_for_zebra(db, zebra_id, active_only=active_only),
        limit=limit,
        offset=offset,
    )


def remove(db: Session, entry_id: uuid.UUID) -> None:
    """Unlink the image from the zebra. The ImageAsset and its Storage object stay."""
    gallery_repo.delete_gallery_entry(db, entry_id)
    db.commit()
