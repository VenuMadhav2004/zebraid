from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ZebraStatus, str_enum

if TYPE_CHECKING:
    from app.models.gallery import GalleryEntry
    from app.models.sighting import Sighting


class Zebra(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A known individual. Created only by a human/curation step, never by inference."""

    __tablename__ = "zebras"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)  # e.g. "ZB-0001"
    name: Mapped[str | None] = mapped_column(String(120))
    species: Mapped[str | None] = mapped_column(String(80))  # null = not yet confirmed
    sex: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[ZebraStatus] = mapped_column(
        str_enum(ZebraStatus, "zebra_status"), default=ZebraStatus.ACTIVE, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)

    gallery_entries: Mapped[list["GalleryEntry"]] = relationship(
        back_populates="zebra", cascade="all, delete-orphan", passive_deletes=True
    )
    # RESTRICT in DB: "all" stops the ORM from nulling children before delete
    sightings: Mapped[list["Sighting"]] = relationship(back_populates="zebra", passive_deletes="all")

    def __repr__(self) -> str:
        return f"<Zebra {self.code}>"
