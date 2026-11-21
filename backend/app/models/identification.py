import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RunStatus, str_enum

if TYPE_CHECKING:
    from app.models.image_asset import ImageAsset
    from app.models.verification import Verification
    from app.models.zebra import Zebra


class IdentificationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of the (external) recognition pipeline on a query image.

    Stores what was run and what happened; raw ML output is kept verbatim in
    processing_metadata because the final ML JSON contract is not frozen.
    """

    __tablename__ = "identification_runs"
    __table_args__ = (
        CheckConstraint("status <> 'failed' OR error_message IS NOT NULL", name="failed_has_error"),
        CheckConstraint("status <> 'completed' OR completed_at IS NOT NULL", name="completed_has_time"),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at", name="time_order"
        ),
        Index("ix_identification_runs_status_created", "status", "created_at"),
    )

    query_image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("image_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus, "run_status"), default=RunStatus.PENDING, nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(300))  # e.g. checkpoint SHA / model_id
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    processing_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    # tri-state from the ML layer: None = no validated unknown threshold was applied
    predicted_unknown: Mapped[bool | None] = mapped_column()
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    query_image: Mapped["ImageAsset"] = relationship()
    candidates: Mapped[list["IdentificationCandidate"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="IdentificationCandidate.rank",
    )
    verifications: Mapped[list["Verification"]] = relationship(
        back_populates="run", order_by="Verification.created_at", passive_deletes="all"
    )


class IdentificationCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A ranked suggestion from a run. A suggestion, never an identity claim.

    zebra_id is null when the ML label does not map to a registered Zebra;
    the raw label is then kept in external_label (no Zebra is invented).
    """

    __tablename__ = "identification_candidates"
    __table_args__ = (
        UniqueConstraint("run_id", "rank", name="uq_identification_candidates_run_rank"),
        # target for the composite FK in verifications (candidate must belong to that run)
        UniqueConstraint("id", "run_id", name="uq_identification_candidates_id_run"),
        CheckConstraint("rank >= 1", name="rank_positive"),
        CheckConstraint("zebra_id IS NOT NULL OR external_label IS NOT NULL", name="has_identity_ref"),
        # finite: rejects NaN and +/-Infinity (scores are similarities, not probabilities; no range implied)
        CheckConstraint(
            "similarity_score > '-Infinity'::float8 AND similarity_score < 'Infinity'::float8",
            name="score_finite",
        ),
        # target for verifications (candidate_id, zebra_id): confirmed zebra must equal candidate zebra
        UniqueConstraint("id", "zebra_id", name="uq_identification_candidates_id_zebra"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("identification_runs.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    zebra_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("zebras.id", ondelete="RESTRICT"), index=True
    )
    external_label: Mapped[str | None] = mapped_column(String(200))
    similarity_score: Mapped[float] = mapped_column(Double, nullable=False)
    score_type: Mapped[str | None] = mapped_column(String(80))  # e.g. "cosine similarity, not probability"
    matched_reference_image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("image_assets.id", ondelete="SET NULL"), index=True
    )
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)

    run: Mapped[IdentificationRun] = relationship(back_populates="candidates")
    zebra: Mapped["Zebra | None"] = relationship()
    matched_reference_image: Mapped["ImageAsset | None"] = relationship()
