import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import VerificationDecision, str_enum

if TYPE_CHECKING:
    from app.models.identification import IdentificationCandidate, IdentificationRun
    from app.models.zebra import Zebra


class Verification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Human review decision on a run. Append-only history; latest row wins.

    confirmed -> candidate_id and zebra_id required (zebra must equal candidate's zebra)
    rejected  -> candidate_id required, zebra_id must be null
    unknown   -> candidate_id and zebra_id must be null (no Zebra is created)
    """

    __tablename__ = "verifications"
    __table_args__ = (
        # candidate must belong to the same run
        ForeignKeyConstraint(
            ["candidate_id", "run_id"],
            ["identification_candidates.id", "identification_candidates.run_id"],
            ondelete="RESTRICT",
            name="fk_verifications_candidate_run",
        ),
        # MATCH SIMPLE: only checked when zebra_id is set (i.e. confirmed)
        ForeignKeyConstraint(
            ["candidate_id", "zebra_id"],
            ["identification_candidates.id", "identification_candidates.zebra_id"],
            ondelete="RESTRICT",
            name="fk_verifications_candidate_zebra",
        ),
        CheckConstraint(
            "(decision = 'confirmed' AND candidate_id IS NOT NULL AND zebra_id IS NOT NULL)"
            " OR (decision = 'rejected' AND candidate_id IS NOT NULL AND zebra_id IS NULL)"
            " OR (decision = 'unknown' AND candidate_id IS NULL AND zebra_id IS NULL)",
            name="decision_shape",
        ),
        Index("ix_verifications_run_created", "run_id", "created_at"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("identification_runs.id", ondelete="RESTRICT"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    zebra_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zebras.id", ondelete="RESTRICT"), index=True)
    decision: Mapped[VerificationDecision] = mapped_column(
        str_enum(VerificationDecision, "verification_decision"), nullable=False
    )
    verified_by: Mapped[str] = mapped_column(String(120), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    run: Mapped["IdentificationRun"] = relationship(back_populates="verifications")
    candidate: Mapped["IdentificationCandidate | None"] = relationship(
        foreign_keys=[candidate_id],
        primaryjoin="Verification.candidate_id == IdentificationCandidate.id",
        viewonly=True,
    )
    zebra: Mapped["Zebra | None"] = relationship()
