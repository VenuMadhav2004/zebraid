"""Persistence for identification runs and their ranked candidates.

These functions only STORE results produced elsewhere (Member 1/2 engine).
They never compute embeddings, similarities or rankings themselves.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import IdentificationCandidate, IdentificationRun, ImageAsset, ImageKind, RunStatus
from app.repositories.base import DomainRuleError, get_or_raise
from app.repositories.gallery import is_gallery_image_of
from app.schemas import IdentificationRunCreate, RunCompletion, RunFailure

_QUERYABLE_KINDS = (ImageKind.QUERY, ImageKind.CROP)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(db: Session, data: IdentificationRunCreate) -> IdentificationRun:
    image = get_or_raise(db, ImageAsset, data.query_image_id)
    if image.kind not in _QUERYABLE_KINDS:
        raise DomainRuleError(f"runs need a query or crop image, got {image.kind.value}")
    run = IdentificationRun(**data.model_dump(), status=RunStatus.PENDING)
    db.add(run)
    db.flush()
    return run


def get_run(db: Session, run_id: uuid.UUID, *, with_candidates: bool = False) -> IdentificationRun:
    if with_candidates:
        run = db.scalar(
            select(IdentificationRun)
            .where(IdentificationRun.id == run_id)
            .options(selectinload(IdentificationRun.candidates))
        )
        if run is None:
            return get_or_raise(db, IdentificationRun, run_id)  # raises NotFoundError
        return run
    return get_or_raise(db, IdentificationRun, run_id)


def _run_filters(stmt: Select, *, status: RunStatus | None, query_image_id: uuid.UUID | None) -> Select:
    if status is not None:
        stmt = stmt.where(IdentificationRun.status == status)
    if query_image_id is not None:
        stmt = stmt.where(IdentificationRun.query_image_id == query_image_id)
    return stmt


def list_runs(
    db: Session,
    *,
    status: RunStatus | None = None,
    query_image_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[IdentificationRun]:
    stmt = _run_filters(select(IdentificationRun), status=status, query_image_id=query_image_id)
    return list(db.scalars(stmt.order_by(IdentificationRun.created_at.desc(), IdentificationRun.id).limit(limit).offset(offset)))


def count_runs(db: Session, *, status: RunStatus | None = None, query_image_id: uuid.UUID | None = None) -> int:
    stmt = _run_filters(select(func.count()).select_from(IdentificationRun), status=status, query_image_id=query_image_id)
    return db.scalar(stmt) or 0


def mark_running(db: Session, run_id: uuid.UUID) -> IdentificationRun:
    run = get_run(db, run_id)
    if run.status != RunStatus.PENDING:
        raise DomainRuleError(f"cannot start a {run.status.value} run")
    run.status = RunStatus.RUNNING
    run.started_at = _now()
    db.flush()
    return run


def complete_run(db: Session, run_id: uuid.UUID, result: RunCompletion) -> IdentificationRun:
    """Store ranked candidates exactly as supplied by the recognition engine."""
    run = get_run(db, run_id)
    if run.status not in (RunStatus.PENDING, RunStatus.RUNNING):
        raise DomainRuleError(f"cannot complete a {run.status.value} run")
    for c in result.candidates:
        if c.matched_reference_image_id is not None:
            if c.zebra_id is None or not is_gallery_image_of(db, c.matched_reference_image_id, c.zebra_id):
                raise DomainRuleError("matched_reference_image_id must be a gallery image of the candidate zebra")
        db.add(IdentificationCandidate(run_id=run.id, **c.model_dump()))
    now = _now()
    run.started_at = run.started_at or now
    run.completed_at = now
    run.status = RunStatus.COMPLETED
    run.processing_metadata = result.processing_metadata
    run.predicted_unknown = result.predicted_unknown
    if result.model_version:
        run.model_version = result.model_version
    db.flush()
    db.refresh(run, attribute_names=["candidates"])
    return run


def fail_run(db: Session, run_id: uuid.UUID, failure: RunFailure) -> IdentificationRun:
    run = get_run(db, run_id)
    if run.status not in (RunStatus.PENDING, RunStatus.RUNNING):
        raise DomainRuleError(f"cannot fail a {run.status.value} run")
    now = _now()
    run.status = RunStatus.FAILED
    run.error_message = failure.error_message
    run.error_code = failure.error_code
    run.processing_metadata = failure.processing_metadata
    run.started_at = run.started_at or now
    run.completed_at = now
    db.flush()
    return run


def list_candidates(db: Session, run_id: uuid.UUID) -> list[IdentificationCandidate]:
    return list(
        db.scalars(
            select(IdentificationCandidate)
            .where(IdentificationCandidate.run_id == run_id)
            .order_by(IdentificationCandidate.rank)
        )
    )


def top_candidate(db: Session, run_id: uuid.UUID) -> IdentificationCandidate | None:
    return db.scalar(
        select(IdentificationCandidate)
        .where(IdentificationCandidate.run_id == run_id)
        .order_by(IdentificationCandidate.rank)
        .limit(1)
    )


def list_candidate_runs_for_zebra(db: Session, zebra_id: uuid.UUID, limit: int = 50) -> list[IdentificationCandidate]:
    """Every time a zebra was suggested, newest first."""
    return list(
        db.scalars(
            select(IdentificationCandidate)
            .where(IdentificationCandidate.zebra_id == zebra_id)
            .order_by(IdentificationCandidate.created_at.desc())
            .limit(limit)
        )
    )


def delete_run(db: Session, run_id: uuid.UUID) -> None:
    """Deletes candidates (CASCADE). Fails (IntegrityError) once a verification exists."""
    db.delete(get_run(db, run_id))
    db.flush()
