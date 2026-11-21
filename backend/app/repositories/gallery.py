import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import GalleryEntry, ImageAsset, ImageKind, Zebra, ZebraStatus
from app.repositories.base import DomainRuleError, apply_update, get_or_raise, orm_kwargs
from app.schemas import GalleryEntryCreate, GalleryEntryUpdate

GALLERY_IMAGE_KINDS = (ImageKind.REFERENCE, ImageKind.CROP)


def register_gallery_entry(db: Session, data: GalleryEntryCreate) -> GalleryEntry:
    """Link a reference/crop image to a known zebra. Query images are refused so
    unverified uploads never enter the gallery."""
    get_or_raise(db, Zebra, data.zebra_id)
    image = get_or_raise(db, ImageAsset, data.image_asset_id)
    if image.kind not in GALLERY_IMAGE_KINDS:
        raise DomainRuleError(f"gallery images must be reference or crop, got {image.kind.value}")
    entry = GalleryEntry(**orm_kwargs(data))
    db.add(entry)
    db.flush()
    return entry


def get_gallery_entry(db: Session, entry_id: uuid.UUID) -> GalleryEntry:
    return get_or_raise(db, GalleryEntry, entry_id)


def _zebra_gallery(stmt: Select, zebra_id: uuid.UUID, active_only: bool) -> Select:
    stmt = stmt.where(GalleryEntry.zebra_id == zebra_id)
    if active_only:
        stmt = stmt.where(GalleryEntry.is_active.is_(True))
    return stmt


def list_gallery_for_zebra(
    db: Session, zebra_id: uuid.UUID, *, active_only: bool = True, limit: int | None = None, offset: int = 0
) -> list[GalleryEntry]:
    stmt = _zebra_gallery(select(GalleryEntry), zebra_id, active_only).options(joinedload(GalleryEntry.image_asset))
    stmt = stmt.order_by(GalleryEntry.created_at, GalleryEntry.id).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def count_gallery_for_zebra(db: Session, zebra_id: uuid.UUID, *, active_only: bool = True) -> int:
    return db.scalar(_zebra_gallery(select(func.count()).select_from(GalleryEntry), zebra_id, active_only)) or 0


def get_entry_for_image(db: Session, image_id: uuid.UUID) -> GalleryEntry | None:
    return db.scalar(select(GalleryEntry).where(GalleryEntry.image_asset_id == image_id))


def list_active_gallery(db: Session) -> list[GalleryEntry]:
    """Every active entry of every active zebra, with zebra + image loaded.

    This is the input a caller would download from Storage and hand to the
    Member 1 build_gallery(images, identities) function (not called here).
    """
    stmt = (
        select(GalleryEntry)
        .join(GalleryEntry.zebra)
        .where(GalleryEntry.is_active.is_(True), Zebra.status == ZebraStatus.ACTIVE)
        .options(joinedload(GalleryEntry.zebra), joinedload(GalleryEntry.image_asset))
        .order_by(Zebra.code, GalleryEntry.created_at)
    )
    return list(db.scalars(stmt))


def update_gallery_entry(db: Session, entry_id: uuid.UUID, data: GalleryEntryUpdate) -> GalleryEntry:
    return apply_update(db, get_gallery_entry(db, entry_id), data)


def deactivate_gallery_entry(db: Session, entry_id: uuid.UUID) -> GalleryEntry:
    entry = get_gallery_entry(db, entry_id)
    entry.is_active = False
    db.flush()
    return entry


def delete_gallery_entry(db: Session, entry_id: uuid.UUID) -> None:
    db.delete(get_gallery_entry(db, entry_id))
    db.flush()


def is_gallery_image_of(db: Session, image_id: uuid.UUID, zebra_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(GalleryEntry.id).where(GalleryEntry.image_asset_id == image_id, GalleryEntry.zebra_id == zebra_id)
        )
        is not None
    )
