import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AnalysisKind, RoiMode, RunStatus, str_enum

if TYPE_CHECKING:
    from app.models.image_asset import ImageAsset


class StripeAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One scientific stripe analysis job (Member 1 morphology or Member 2 spatial frequency).

    Stores canonical ROI, parameters, exact research commit provenance, sanitized library
    JSON output, and private bucket artifact paths (never exposed directly to clients).
    """

    __tablename__ = "stripe_analyses"
    __table_args__ = (
        CheckConstraint("status <> 'failed' OR error_message IS NOT NULL", name="failed_has_error"),
        CheckConstraint("status <> 'completed' OR completed_at IS NOT NULL", name="completed_has_time"),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="time_order",
        ),
        Index("ix_stripe_analyses_image_created", "image_asset_id", "created_at"),
        Index("ix_stripe_analyses_status_created", "status", "created_at"),
    )

    image_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("image_assets.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[AnalysisKind] = mapped_column(str_enum(AnalysisKind, "analysis_kind"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus, "analysis_status"), default=RunStatus.PENDING, nullable=False
    )
    roi: Mapped[dict] = mapped_column(JSONB, nullable=False)
    roi_mode: Mapped[RoiMode] = mapped_column(str_enum(RoiMode, "roi_mode"), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    provider: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB)
    # Private storage map {artifact_name: storage_path}; NEVER serialised directly to API clients.
    artifacts: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    image_asset: Mapped["ImageAsset"] = relationship()
