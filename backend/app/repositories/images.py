import uuid

from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from app.models import ImageAsset, ImageKind
from app.repositories.base import DomainRuleError, apply_update, get_or_raise, orm_kwargs
from app.schemas import ImageAssetCreate, ImageAssetUpdate


def create_image_asset(db: Session, data: ImageAssetCreate) -> ImageAsset:
    """Record metadata for an object ALREADY uploaded to private Storage."""
    kwargs = orm_kwargs(data)
    if data.crop_bbox is not None:
        source = get_or_raise(db, ImageAsset, data.source_image_id)
        box = data.crop_bbox
        if source.width and source.height and (box.x + box.width > source.width or box.y + box.height > source.height):
            raise DomainRuleError("crop_bbox lies outside the source image")
        kwargs["crop_bbox"] = box.model_dump()
    image = ImageAsset(**kwargs)
    db.add(image)
    db.flush()
    return image


def get_image_asset(db: Session, image_id: uuid.UUID) -> ImageAsset:
    return get_or_raise(db, ImageAsset, image_id)


def get_by_storage_path(db: Session, bucket: str, path: str) -> ImageAsset | None:
    return db.scalar(select(ImageAsset).where(ImageAsset.storage_bucket == bucket, ImageAsset.storage_path == path))


def find_by_sha256(db: Session, sha256: str) -> list[ImageAsset]:
    return list(db.scalars(select(ImageAsset).where(ImageAsset.sha256 == sha256)))


def _image_filters(stmt: Select, *, kind: ImageKind | None, sha256: str | None) -> Select:
    if kind is not None:
        stmt = stmt.where(ImageAsset.kind == kind)
    if sha256 is not None:
        stmt = stmt.where(ImageAsset.sha256 == sha256)
    return stmt


def list_image_assets(
    db: Session, *, kind: ImageKind | None = None, sha256: str | None = None, limit: int = 100, offset: int = 0
) -> list[ImageAsset]:
    stmt = _image_filters(select(ImageAsset), kind=kind, sha256=sha256)
    return list(db.scalars(stmt.order_by(ImageAsset.created_at.desc(), ImageAsset.id).limit(limit).offset(offset)))


def count_image_assets(db: Session, *, kind: ImageKind | None = None, sha256: str | None = None) -> int:
    return db.scalar(_image_filters(select(func.count()).select_from(ImageAsset), kind=kind, sha256=sha256)) or 0


def find_duplicate(db: Session, sha256: str, kind: ImageKind) -> ImageAsset | None:
    return db.scalar(select(ImageAsset).where(ImageAsset.sha256 == sha256, ImageAsset.kind == kind).limit(1))


def usage_counts(db: Session, image_id: uuid.UUID) -> dict[str, int]:
    """Records that still use an image. Any non-zero count blocks deletion: some FKs
    are RESTRICT, others (sightings, matched references) would silently lose evidence."""
    from app.models import GalleryEntry, IdentificationCandidate, IdentificationRun, Sighting, StripeAnalysis

    def n(column) -> int:
        return db.scalar(select(func.count()).where(column == image_id)) or 0

    counts = {
        "crops": n(ImageAsset.source_image_id),
        "gallery_entries": n(GalleryEntry.image_asset_id),
        "identification_runs": n(IdentificationRun.query_image_id),
        "identification_candidates": n(IdentificationCandidate.matched_reference_image_id),
        "sightings": n(Sighting.image_asset_id),
    }
    # Guard until the stripe_analyses migration is applied to live Supabase.
    if db.execute(text("SELECT to_regclass('public.stripe_analyses')")).scalar() is not None:
        counts["stripe_analyses"] = n(StripeAnalysis.image_asset_id)
    return counts


def list_crops(db: Session, source_image_id: uuid.UUID) -> list[ImageAsset]:
    return list(
        db.scalars(select(ImageAsset).where(ImageAsset.source_image_id == source_image_id).order_by(ImageAsset.created_at))
    )


def update_image_asset(db: Session, image_id: uuid.UUID, data: ImageAssetUpdate) -> ImageAsset:
    return apply_update(db, get_image_asset(db, image_id), data)


def delete_image_asset(db: Session, image_id: uuid.UUID) -> str:
    """Delete the DB row and return the storage path so the caller can remove the
    Storage object AFTER commit. Fails (IntegrityError) while crops, gallery
    entries or identification runs reference the image."""
    image = get_image_asset(db, image_id)
    path = image.storage_path
    db.delete(image)
    db.flush()
    return path
