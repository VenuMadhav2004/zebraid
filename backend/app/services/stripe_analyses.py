"""Scientific stripe analysis orchestration: submission, bounded dispatcher, artifact storage."""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ConflictError, ServiceUnavailableError
from app.database.session import session_scope
from app.integrations.science import (
    AnalysisLimitError,
    AnalysisValidationError,
    WorkerOutcome,
    probe_capabilities,
    run_analysis_in_subprocess,
    validate_and_resolve_roi,
)
from app.integrations.science.worker import provider_metadata
from app.integrations.supabase_storage import StorageError, SupabaseStorage
from app.models import AnalysisKind, RoiMode, RunStatus
from app.repositories import images as image_repo
from app.repositories import stripe_analyses as analysis_repo
from app.repositories.base import NotFoundError
from app.schemas import (
    AnalysisCapabilitiesResponse,
    AnalysisCapabilityItem,
    AnalysisJobRead,
    AnalysisLimitsRead,
    CombinedAnalysisRequest,
    CombinedAnalysisResponse,
    FrequencyAnalysisRequest,
    MorphologyAnalysisRequest,
    Page,
    SignedUrlResponse,
)
from app.services import image_storage

logger = logging.getLogger(__name__)

_cap_lock = threading.Lock()
_cap_cache: dict[str, dict[str, dict[str, Any]]] = {}


def clear_capability_cache() -> None:
    with _cap_lock:
        _cap_cache.clear()


TABLE_MISSING_REASON = (
    "Analysis results cannot be stored yet: the stripe_analyses table is not migrated "
    "(migration a8d3f2c91b40 is prepared and awaiting approval)."
)


def get_capabilities(
    settings: Settings | None = None, *, refresh: bool = False, db: Session | None = None
) -> AnalysisCapabilitiesResponse:
    """Runtime availability (vendored code + packages). With `db`, also requires the results table,
    because without it every submission would be rejected with 503."""
    s = settings or get_settings()
    vendor_key = s.science_vendor_dir or ""
    with _cap_lock:
        probed = None if refresh else _cap_cache.get(vendor_key)
    if probed is None:
        probed = probe_capabilities(s.science_vendor_dir or None)
        with _cap_lock:
            _cap_cache[vendor_key] = probed
    items = {k: dict(v) for k, v in probed.items()}
    if db is not None and not analysis_repo.table_exists(db):
        for item in items.values():
            if item["available"]:
                item["available"] = False
                item["reason"] = TABLE_MISSING_REASON
    return AnalysisCapabilitiesResponse(
        stripe_morphology=AnalysisCapabilityItem(**items["stripe_morphology"]),
        spatial_frequency=AnalysisCapabilityItem(**items["spatial_frequency"]),
        limits=AnalysisLimitsRead(
            max_pixels=s.analysis_max_pixels,
            max_source_pixels=s.analysis_max_source_pixels,
            max_dimension=s.analysis_max_dimension,
            queue_limit=s.analysis_queue_limit,
            timeout_seconds=s.analysis_timeout_seconds,
        ),
    )


def _require_table(db: Session) -> None:
    if not analysis_repo.table_exists(db):
        raise ServiceUnavailableError(
            "Stripe analysis storage table is not migrated yet.",
            code="analysis_unavailable",
        )


def _artifact_storage_path(job_id: uuid.UUID, artifact_name: str, now: datetime | None = None) -> str:
    ts = now or datetime.now(timezone.utc)
    return f"analysis/{ts:%Y/%m}/{job_id}/{artifact_name}.png"


def _submit_job(
    db: Session,
    settings: Settings,
    *,
    image_id: uuid.UUID,
    kind: AnalysisKind,
    roi: dict[str, int] | None,
    parameters: dict[str, Any],
    on_enqueued: Callable[[], None] | None = None,
) -> AnalysisJobRead:
    caps = get_capabilities(settings)
    cap_item = caps.stripe_morphology if kind == AnalysisKind.STRIPE_MORPHOLOGY else caps.spatial_frequency
    if not cap_item.available:
        raise ServiceUnavailableError(
            cap_item.reason or "Scientific analysis runtime is unavailable.",
            code="analysis_unavailable",
        )

    _require_table(db)

    image = image_repo.get_image_asset(db, image_id)
    if image.width is None or image.height is None:
        raise AppError("Image dimensions are missing; cannot validate ROI.", status_code=422, code="validation_error")

    try:
        resolved_roi, roi_mode_str = validate_and_resolve_roi(
            roi,
            image.width,
            image.height,
            kind=kind.value,
            max_pixels=settings.analysis_max_pixels,
            max_source_pixels=settings.analysis_max_source_pixels,
            max_dimension=settings.analysis_max_dimension,
        )
    except AnalysisLimitError as exc:
        raise AppError(str(exc), status_code=422, code="analysis_limit_exceeded", details=exc.details) from None
    except AnalysisValidationError as exc:
        raise AppError(str(exc), status_code=422, code="validation_error") from None

    pending_count = analysis_repo.count_pending(db)
    if pending_count >= settings.analysis_queue_limit:
        raise ServiceUnavailableError(
            "Analysis queue is full — try again shortly.",
            code="analysis_busy",
            details={"pending": pending_count, "queue_limit": settings.analysis_queue_limit},
        )

    job = analysis_repo.create_analysis(
        db,
        image_asset_id=image.id,
        kind=kind,
        roi=resolved_roi,
        roi_mode=RoiMode(roi_mode_str),
        parameters=parameters,
        provider=provider_metadata(kind.value),
    )
    db.commit()
    if on_enqueued is not None:
        on_enqueued()
    return AnalysisJobRead.from_orm_job(job)


def submit_morphology(
    db: Session,
    settings: Settings,
    body: MorphologyAnalysisRequest,
    *,
    on_enqueued: Callable[[], None] | None = None,
) -> AnalysisJobRead:
    config_dict = body.config.model_dump(exclude_none=True)
    roi_dict = body.roi.model_dump() if body.roi is not None else None
    return _submit_job(
        db,
        settings,
        image_id=body.image_id,
        kind=AnalysisKind.STRIPE_MORPHOLOGY,
        roi=roi_dict,
        parameters={"config": config_dict},
        on_enqueued=on_enqueued,
    )


def submit_frequency(
    db: Session,
    settings: Settings,
    body: FrequencyAnalysisRequest,
    *,
    on_enqueued: Callable[[], None] | None = None,
) -> AnalysisJobRead:
    options_dict = body.options.model_dump()
    roi_dict = body.roi.model_dump() if body.roi is not None else None
    return _submit_job(
        db,
        settings,
        image_id=body.image_id,
        kind=AnalysisKind.SPATIAL_FREQUENCY,
        roi=roi_dict,
        parameters={"options": options_dict},
        on_enqueued=on_enqueued,
    )


def submit_combined(
    db: Session,
    settings: Settings,
    body: CombinedAnalysisRequest,
    *,
    on_enqueued: Callable[[], None] | None = None,
) -> CombinedAnalysisResponse:
    """Validate and enqueue Member 1 morphology + Member 2 spatial frequency on the same image & ROI."""
    caps = get_capabilities(settings)
    if not caps.stripe_morphology.available or not caps.spatial_frequency.available:
        reasons = [
            r for r in (caps.stripe_morphology.reason, caps.spatial_frequency.reason) if r
        ]
        raise ServiceUnavailableError(
            " ".join(dict.fromkeys(reasons)) or "Scientific analysis runtime is unavailable.",
            code="analysis_unavailable",
        )

    _require_table(db)

    image = image_repo.get_image_asset(db, body.image_id)
    if image.width is None or image.height is None:
        raise AppError("Image dimensions are missing; cannot validate ROI.", status_code=422, code="validation_error")

    roi_dict = body.roi.model_dump() if body.roi is not None else None
    try:
        m1_roi, m1_mode = validate_and_resolve_roi(
            roi_dict,
            image.width,
            image.height,
            kind=AnalysisKind.STRIPE_MORPHOLOGY.value,
            max_pixels=settings.analysis_max_pixels,
            max_source_pixels=settings.analysis_max_source_pixels,
            max_dimension=settings.analysis_max_dimension,
        )
        m2_roi, m2_mode = validate_and_resolve_roi(
            roi_dict,
            image.width,
            image.height,
            kind=AnalysisKind.SPATIAL_FREQUENCY.value,
            max_pixels=settings.analysis_max_pixels,
            max_source_pixels=settings.analysis_max_source_pixels,
            max_dimension=settings.analysis_max_dimension,
        )
    except AnalysisLimitError as exc:
        raise AppError(str(exc), status_code=422, code="analysis_limit_exceeded", details=exc.details) from None
    except AnalysisValidationError as exc:
        raise AppError(str(exc), status_code=422, code="validation_error") from None

    pending_count = analysis_repo.count_pending(db)
    if pending_count + 2 > settings.analysis_queue_limit:
        raise ServiceUnavailableError(
            "Analysis queue does not have capacity for a combined job pair — try again shortly.",
            code="analysis_busy",
            details={"pending": pending_count, "required": 2, "queue_limit": settings.analysis_queue_limit},
        )

    m1_job = analysis_repo.create_analysis(
        db,
        image_asset_id=image.id,
        kind=AnalysisKind.STRIPE_MORPHOLOGY,
        roi=m1_roi,
        roi_mode=RoiMode(m1_mode),
        parameters={"config": body.morphology_config.model_dump(exclude_none=True)},
        provider=provider_metadata(AnalysisKind.STRIPE_MORPHOLOGY.value),
    )
    m2_job = analysis_repo.create_analysis(
        db,
        image_asset_id=image.id,
        kind=AnalysisKind.SPATIAL_FREQUENCY,
        roi=m2_roi,
        roi_mode=RoiMode(m2_mode),
        parameters={"options": body.frequency_options.model_dump()},
        provider=provider_metadata(AnalysisKind.SPATIAL_FREQUENCY.value),
    )
    db.commit()
    if on_enqueued is not None:
        on_enqueued()
    return CombinedAnalysisResponse(
        stripe_morphology=AnalysisJobRead.from_orm_job(m1_job),
        spatial_frequency=AnalysisJobRead.from_orm_job(m2_job),
    )


def list_analyses(
    db: Session,
    *,
    image_id: uuid.UUID | None,
    kind: AnalysisKind | None,
    status: RunStatus | None,
    limit: int,
    offset: int,
) -> Page[AnalysisJobRead]:
    _require_table(db)
    items = analysis_repo.list_analyses(db, image_id=image_id, kind=kind, status=status, limit=limit, offset=offset)
    return Page[AnalysisJobRead](
        items=[AnalysisJobRead.from_orm_job(j) for j in items],
        total=analysis_repo.count_analyses(db, image_id=image_id, kind=kind, status=status),
        limit=limit,
        offset=offset,
    )


def get_analysis(db: Session, analysis_id: uuid.UUID) -> AnalysisJobRead:
    _require_table(db)
    return AnalysisJobRead.from_orm_job(analysis_repo.get_analysis(db, analysis_id))


def artifact_signed_url(
    db: Session,
    storage: SupabaseStorage,
    analysis_id: uuid.UUID,
    artifact_name: str,
    expires_in: int | None,
) -> SignedUrlResponse:
    _require_table(db)
    if expires_in is not None and not 1 <= expires_in <= storage.max_ttl:
        raise AppError(
            f"expires_in must be between 1 and {storage.max_ttl} seconds",
            status_code=422,
            code="validation_error",
        )
    job = analysis_repo.get_analysis(db, analysis_id)
    artifact_map = job.artifacts if isinstance(job.artifacts, dict) else {}
    storage_path = artifact_map.get(artifact_name)
    if not storage_path:
        raise NotFoundError(f"artifact '{artifact_name}' not found for analysis {analysis_id}")
    signed = storage.signed_url(storage_path, expires_in)
    return SignedUrlResponse(url=signed.url, expires_in=signed.expires_in, expires_at=signed.expires_at)


def delete_analysis(db: Session, storage: SupabaseStorage, analysis_id: uuid.UUID) -> None:
    _require_table(db)
    job = analysis_repo.get_analysis(db, analysis_id)
    if job.status == RunStatus.RUNNING:
        raise ConflictError("Cannot delete an analysis while it is running.", code="analysis_running")
    paths = analysis_repo.delete_analysis(db, analysis_id)
    db.commit()
    if paths:
        image_storage.discard_objects(storage, paths)


def execute_analysis_job(
    db: Session,
    storage: SupabaseStorage,
    settings: Settings,
    job_id: uuid.UUID,
    *,
    runner: Callable[..., WorkerOutcome] = run_analysis_in_subprocess,
) -> AnalysisJobRead:
    """Download image bytes, run isolated worker, upload private PNG artifacts, persist result."""
    job = analysis_repo.get_analysis(db, job_id)
    if job.status == RunStatus.PENDING:
        job = analysis_repo.mark_running(db, job.id)
        db.commit()

    image = image_repo.get_image_asset(db, job.image_asset_id)
    try:
        image_bytes = storage.download(image.storage_path)
    except StorageError as exc:
        logger.error("Failed downloading source image for analysis %s: %s", job.id, exc)
        job = analysis_repo.fail_analysis(
            db,
            job.id,
            error_code="storage_error",
            error_message="Could not download the source photograph from private storage.",
        )
        db.commit()
        return AnalysisJobRead.from_orm_job(job)

    outcome = runner(
        kind=job.kind.value,
        image_id=str(image.id),
        image_bytes=image_bytes,
        roi=job.roi,
        roi_mode=job.roi_mode.value,
        parameters=job.parameters,
        vendor_dir=settings.science_vendor_dir or None,
        tmp_root=settings.analysis_tmp_dir or None,
        timeout_seconds=settings.analysis_timeout_seconds,
        max_source_pixels=settings.analysis_max_source_pixels,
        max_dimension=settings.analysis_max_dimension,
    )

    if not outcome.ok or outcome.result is None:
        job = analysis_repo.fail_analysis(
            db,
            job.id,
            error_code=outcome.error_code or "worker_error",
            error_message=outcome.error_message or "Analysis failed.",
        )
        db.commit()
        return AnalysisJobRead.from_orm_job(job)

    uploaded_paths: dict[str, str] = {}
    now = datetime.now(timezone.utc)
    try:
        for name, png_bytes in outcome.artifact_bytes.items():
            path = _artifact_storage_path(job.id, name, now=now)
            storage.upload(path, png_bytes, "image/png")
            uploaded_paths[name] = path
    except Exception as exc:
        logger.error("Failed uploading artifact for analysis %s: %s", job.id, exc)
        if uploaded_paths:
            image_storage.discard_objects(storage, list(uploaded_paths.values()))
        job = analysis_repo.fail_analysis(
            db,
            job.id,
            error_code="storage_error",
            error_message="Could not store analysis artifacts.",
        )
        db.commit()
        return AnalysisJobRead.from_orm_job(job)

    try:
        job = analysis_repo.complete_analysis(
            db,
            job.id,
            result=outcome.result,
            artifacts=uploaded_paths,
        )
        db.commit()
    except Exception:
        db.rollback()
        if uploaded_paths:
            image_storage.discard_objects(storage, list(uploaded_paths.values()))
        raise
    return AnalysisJobRead.from_orm_job(job)


class AnalysisDispatcher:
    """Single-worker bounded background dispatcher (1 subprocess at a time)."""

    def __init__(self, settings: Settings, storage_factory: Callable[[], SupabaseStorage]):
        self._settings = settings
        self._storage_factory = storage_factory
        self._wake = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def notify(self) -> None:
        if self._task is not None and not self._task.done():
            self._wake.set()

    async def start(self) -> None:
        if not self._settings.database_url:
            return
        try:
            await asyncio.to_thread(self._recover_stale)
        except Exception as exc:
            logger.debug("Skipping stale analysis recovery at startup: %s", exc)
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="stripe-analysis-dispatcher")

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
            except Exception:
                pass
            self._task = None

    def _recover_stale(self) -> None:
        with session_scope() as db:
            if not analysis_repo.table_exists(db):
                return
            recovered = analysis_repo.recover_interrupted_running(db)
            if recovered:
                logger.warning("Recovered %d interrupted running analysis job(s)", recovered)

    def _process_next_job(self) -> bool:
        with session_scope() as db:
            if not analysis_repo.table_exists(db):
                return False
            job = analysis_repo.claim_next_pending(db)
            if job is None:
                return False
            job_id = job.id
        try:
            storage = self._storage_factory()
            with session_scope() as db:
                execute_analysis_job(db, storage, self._settings, job_id)
        except Exception as exc:
            # Never leave a claimed job in 'running' (the UI would poll until its deadline).
            logger.exception("Analysis job %s crashed outside the worker: %s", job_id, exc)
            self._fail_crashed_job(job_id)
        return True

    @staticmethod
    def _fail_crashed_job(job_id: uuid.UUID) -> None:
        try:
            with session_scope() as db:
                job = analysis_repo.get_analysis(db, job_id)
                if job.status in (RunStatus.PENDING, RunStatus.RUNNING):
                    analysis_repo.fail_analysis(
                        db,
                        job_id,
                        error_code="worker_error",
                        error_message="The analysis worker exited unexpectedly.",
                    )
        except Exception as exc:  # job will be recovered as 'interrupted' on next startup
            logger.error("Could not mark crashed analysis %s as failed: %s", job_id, exc)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            try:
                ran = await asyncio.to_thread(self._process_next_job)
                if ran:
                    continue
            except Exception as exc:
                logger.exception("Analysis dispatcher tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
