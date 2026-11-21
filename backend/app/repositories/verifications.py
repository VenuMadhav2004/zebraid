import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IdentificationCandidate, IdentificationRun, RunStatus, Verification, VerificationDecision
from app.repositories.base import DomainRuleError, get_or_raise
from app.schemas import VerificationCreate


def create_verification(db: Session, data: VerificationCreate) -> Verification:
    """Record a human decision. Append-only: a new decision supersedes older ones.

    confirmed requires a candidate already linked to a registered Zebra; to confirm
    an unmapped external_label, register the zebra first (never auto-created here).
    """
    run = get_or_raise(db, IdentificationRun, data.run_id)
    if run.status != RunStatus.COMPLETED:
        raise DomainRuleError(f"only completed runs can be verified (run is {run.status.value})")

    zebra_id = None
    if data.candidate_id is not None:
        candidate = get_or_raise(db, IdentificationCandidate, data.candidate_id)
        if candidate.run_id != run.id:
            raise DomainRuleError("candidate does not belong to this run")
        if data.decision == VerificationDecision.CONFIRMED:
            if candidate.zebra_id is None:
                raise DomainRuleError("cannot confirm a candidate that is not a registered zebra")
            zebra_id = candidate.zebra_id

    verification = Verification(
        run_id=run.id,
        candidate_id=data.candidate_id,
        zebra_id=zebra_id,
        decision=data.decision,
        verified_by=data.verified_by,
        notes=data.notes,
    )
    db.add(verification)
    db.flush()
    return verification


def list_verifications(db: Session, run_id: uuid.UUID) -> list[Verification]:
    return list(
        db.scalars(select(Verification).where(Verification.run_id == run_id).order_by(Verification.created_at, Verification.id))
    )


def latest_verification(db: Session, run_id: uuid.UUID) -> Verification | None:
    return db.scalar(
        select(Verification)
        .where(Verification.run_id == run_id)
        .order_by(Verification.created_at.desc(), Verification.id.desc())
        .limit(1)
    )


def list_confirmed_for_zebra(db: Session, zebra_id: uuid.UUID) -> list[Verification]:
    return list(
        db.scalars(
            select(Verification)
            .where(Verification.zebra_id == zebra_id, Verification.decision == VerificationDecision.CONFIRMED)
            .order_by(Verification.created_at.desc())
        )
    )
