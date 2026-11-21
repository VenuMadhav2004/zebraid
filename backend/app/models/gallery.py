import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import FlankSide, str_enum

if TYPE_CHECKING:
    from app.models.image_asset import ImageAsset
    from app.models.zebra import Zebra


class GalleryEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Registers a reference (or crop) ImageAsset as a known view of a Zebra.

    An image can belong to at most one zebra's gallery (unique image_asset_id).
    Embeddings are NOT stored here: the recognition engine (Member 1) owns them.
    The image kind (reference|crop) is enforced in the repository layer.
    """

    __tablename__ = "gallery_entries"
    __table_args__ = (Index("ix_gallery_entries_zebra_active", "zebra_id", "is_active"),)

    zebra_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zebras.id", ondelete="CASCADE"), nullable=False)
    image_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("image_assets.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    side: Mapped[FlankSide] = mapped_column(
        str_enum(FlankSide, "flank_side"), default=FlankSide.UNKNOWN, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    quality_notes: Mapped[str | None] = mapped_column(Text)
    registered_by: Mapped[str | None] = mapped_column(String(120))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default="{}", nullable=False)

    zebra: Mapped["Zebra"] = relationship(back_populates="gallery_entries")
    image_asset: Mapped["ImageAsset"] = relationship(back_populates="gallery_entry")
