import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ImageKind, str_enum

if TYPE_CHECKING:
    from app.models.gallery import GalleryEntry


class ImageAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata for one image object in private Supabase Storage.

    Only the bucket + object path is stored; image bytes never enter PostgreSQL.
    Access is via short-lived signed URLs generated server-side.
    """

    __tablename__ = "image_assets"
    __table_args__ = (
        UniqueConstraint("storage_bucket", "storage_path", name="uq_image_assets_storage_object"),
        # crops must reference their source image + region; other kinds must not
        CheckConstraint(
            "(kind = 'crop') = (source_image_id IS NOT NULL AND crop_bbox IS NOT NULL)",
            name="crop_has_source",
        ),
        CheckConstraint("source_image_id IS NULL OR source_image_id <> id", name="not_own_source"),
        # a storage path, not a URL (no public/signed URLs persisted)
        CheckConstraint("storage_path !~* '^[a-z]+://' AND storage_path !~ '^/'", name="relative_path"),
        # no '..' segments, backslashes or control characters in object keys
        CheckConstraint(
            r"storage_path !~ '(^|/)\.\.(/|$)' AND storage_path !~ '[\\[:cntrl:]]'",
            name="path_safe",
        ),
        CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp')", name="content_type_allowed"
        ),
        CheckConstraint("width IS NULL OR width > 0", name="width_positive"),
        CheckConstraint("height IS NULL OR height > 0", name="height_positive"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_nonneg"),
        CheckConstraint("sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        Index("ix_image_assets_kind_created", "kind", "created_at"),
    )

    kind: Mapped[ImageKind] = mapped_column(str_enum(ImageKind, "image_kind"), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[str | None] = mapped_column(String(120))

    # crop lineage: region (x, y, width, height in source pixels) cut from source_image_id
    source_image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("image_assets.id", ondelete="RESTRICT"), index=True
    )
    crop_bbox: Mapped[dict | None] = mapped_column(JSONB)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default="{}", nullable=False)

    source_image: Mapped["ImageAsset | None"] = relationship(remote_side="ImageAsset.id", back_populates="crops")
    # RESTRICT in DB: "all" stops the ORM from nulling children before delete
    crops: Mapped[list["ImageAsset"]] = relationship(back_populates="source_image", passive_deletes="all")
    gallery_entry: Mapped["GalleryEntry | None"] = relationship(back_populates="image_asset", passive_deletes="all")

    def __repr__(self) -> str:
        return f"<ImageAsset {self.kind.value} {self.storage_path}>"
