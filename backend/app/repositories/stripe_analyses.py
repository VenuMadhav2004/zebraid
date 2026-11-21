"""Database persistence for scientific stripe analysis jobs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from app.models import AnalysisKind, RoiMode, RunStatus, StripeAnalysis
from app.repositories.base import DomainRuleError, get_or_raise


def _now() -> datetime:
    return datetime.now(timezone.utc)


def table_exists(db: Session) -> bool:
    """Return True if the stripe_analyses migration has been applied."""
    return db.execute(text("SELECT to_regclass('public.stripe_analyses')")).scalar() is not None


def create_analysis(
    db: Session,
    *,
    image_asset_id: uuid.UUID,
    kind: AnalysisKind,
    roi: dict[str, int],
    roi_mode: RoiMode,
    parameters: dict[str, Any],
    provider: dict[str, Any],
) -> StripeAnalysis:
    job = StripeAnalysis(
        image_asset_id=image_asset_id,
        kind=kind,
        status=RunStatus.PENDING,
        roi=roi,
        roi_mode=roi_mode,
        parameters=parameters,
        provider=provider,
        artifacts={},
    )
    db.add(job)
    db.flush()
    return job


def get_analysis(db: Session, analysis_id: uuid.UUID) -> StripeAnalysis:
    return get_or_raise(db, StripeAnalysis, analysis_id)


def _filters(
    stmt: Select,
    *,
    image_id: uuid.UUID | None,
    kind: AnalysisKind | None,
    status: RunStatus | None,
) -> Select:
    if image_id is not None:
        stmt = stmt.where(StripeAnalysis.image_asset_id == image_id)
    if kind is not None:
        stmt = stmt.where(StripeAnalysis.kind == kind)
    if status is not None:
        stmt = stmt.where(StripeAnalysis.status == status)
    return stmt


def list_analyses(
    db: Session,
    *,
    image_id: uuid.UUID | None = None,
    kind: AnalysisKind | None = None,
    status: RunStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[StripeAnalysis]:
    stmt = _filters(select(StripeAnalysis), image_id=image_id, kind=kind, status=status)
    return list(db.scalars(stmt.order_by(StripeAnalysis.created_at.desc(), StripeAnalysis.id).limit(limit).offset(offset)))


def count_analyses(
    db: Session,
    *,
    image_id: uuid.UUID | None = None,
    kind: AnalysisKind | None = None,
    status: RunStatus | None = None,
) -> int:
    stmt = _filters(select(func.count()).select_from(StripeAnalysis), image_id=image_id, kind=kind, status=status)
    return db.scalar(stmt) or 0


def count_pending(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(StripeAnalysis).where(StripeAnalysis.status == RunStatus.PENDING)) or 0


def claim_next_pending(db: Session) -> StripeAnalysis | None:
    """Atomically claim the oldest pending job as running."""
    job = db.scalar(
        select(StripeAnalysis)
        .where(StripeAnalysis.status == RunStatus.PENDING)
        .order_by(StripeAnalysis.created_at.asc(), StripeAnalysis.id.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = RunStatus.RUNNING
    job.started_at = _now()
    db.flush()
    return job


def mark_running(db: Session, analysis_id: uuid.UUID) -> StripeAnalysis:
    job = get_analysis(db, analysis_id)
    if job.status != RunStatus.PENDING:
        raise DomainRuleError(f"cannot start a {job.status.value} analysis")
    job.status = RunStatus.RUNNING
    job.started_at = _now()
    db.flush()
    return job


def complete_analysis(
    db: Session,
    analysis_id: uuid.UUID,
    *,
    result: dict[str, Any],
    artifacts: dict[str, str],
) -> StripeAnalysis:
    job = get_analysis(db, analysis_id)
    if job.status not in (RunStatus.PENDING, RunStatus.RUNNING):
        raise DomainRuleError(f"cannot complete a {job.status.value} analysis")
    now = _now()
    job.started_at = job.started_at or now
    job.completed_at = now
    job.status = RunStatus.COMPLETED
    job.result = result
    job.artifacts = artifacts
    job.error_code = None
    job.error_message = None
    db.flush()
    return job


def fail_analysis(
    db: Session,
    analysis_id: uuid.UUID,
    *,
    error_code: str,
    error_message: str,
) -> StripeAnalysis:
    job = get_analysis(db, analysis_id)
    if job.status not in (RunStatus.PENDING, RunStatus.RUNNING):
        raise DomainRuleError(f"cannot fail a {job.status.value} analysis")
    now = _now()
    job.started_at = job.started_at or now
    job.completed_at = now
    job.status = RunStatus.FAILED
    job.error_code = error_code
    job.error_message = error_message
    db.flush()
    return job


def recover_interrupted_running(db: Session) -> int:
    """Mark any stale `running` jobs from before a server restart as failed/interrupted."""
    rows = list(db.scalars(select(StripeAnalysis).where(StripeAnalysis.status == RunStatus.RUNNING)))
    now = _now()
    for job in rows:
        job.status = RunStatus.FAILED
        job.error_code = "interrupted"
        job.error_message = "Analysis was interrupted by a server restart."
        job.started_at = job.started_at or now
        job.completed_at = now
    if rows:
        db.flush()
    return len(rows)


def delete_analysis(db: Session, analysis_id: uuid.UUID) -> list[str]:
    """Delete DB row and return private storage paths to remove AFTER commit."""
    job = get_analysis(db, analysis_id)
    paths = list(job.artifacts.values()) if isinstance(job.artifacts, dict) else []
    db.delete(job)
    db.flush()
    return paths
