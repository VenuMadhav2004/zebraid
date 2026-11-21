import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Double, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.identification import IdentificationRun
    from app.models.image_asset import ImageAsset
    from app.models.zebra import Zebra


class Sighting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A field observation. zebra_id may be null (individual not yet identified)."""

    __tablename__ = "sightings"
    __table_args__ = (
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="lat_range"),
        CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="lon_range"),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="lat_lon_pair"),
        Index("ix_sightings_zebra_observed", "zebra_id", "observed_at"),
    )

    zebra_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zebras.id", ondelete="RESTRICT"))
    image_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("image_assets.id", ondelete="SET NULL"), index=True
    )
    identification_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("identification_runs.id", ondelete="SET NULL"), index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    latitude: Mapped[float | None] = mapped_column(Double)
    longitude: Mapped[float | None] = mapped_column(Double)
    location_name: Mapped[str | None] = mapped_column(String(200))
    observer: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default="{}", nullable=False)

    zebra: Mapped["Zebra | None"] = relationship(back_populates="sightings")
    image_asset: Mapped["ImageAsset | None"] = relationship()
    identification_run: Mapped["IdentificationRun | None"] = relationship()
