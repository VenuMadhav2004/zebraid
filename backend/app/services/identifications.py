"""Identification runs, MegaDescriptor-L-384 v1 CPU candidate retrieval, and human review.

`similarity_score` is a cosine similarity, never an identity probability.
`predicted_unknown` stays `None` (no uncalibrated threshold claim), and no identity
is ever confirmed without an explicit human verification decision.
"""
from __future__ import annotations

import logging
import uuid
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, InvalidReferenceError, ServiceUnavailableError
from app.integrations.recognition import (
    MODEL_ID,
    RecognitionNotConfiguredError,
    RecognitionResult,
    RecognitionRuntimeError,
    get_recognition_status,
    identify_with_cached_gallery,
    model_load_state,
)
from app.integrations.supabase_storage import StorageError, SupabaseStorage
from app.models import IdentificationCandidate, IdentificationRun, RunStatus, Verification
from app.repositories import gallery as gallery_repo
from app.repositories import identifications as run_repo
from app.repositories import images as image_repo
from app.repositories import verifications as verification_repo
from app.repositories.base import DomainRuleError
from app.schemas import (
    CandidateCreate,
    IdentificationRunCreate,
    IdentificationRunRead,
    IdentificationSubmitRequest,
    Page,
    RecognitionCapabilityResponse,
    RunCompletion,
    RunFailure,
    VerificationCreate,
    VerificationSubmit,
)

logger = logging.getLogger(__name__)


def get_recognition_capabilities(settings: Settings | None = None) -> RecognitionCapabilityResponse:
    s = settings or get_settings()
    state = model_load_state()
    return RecognitionCapabilityResponse(
        **get_recognition_status(s), model_state=state["state"], model_load_seconds=state["seconds"]
    )


def list_runs(
    db: Session, *, status: RunStatus | None, query_image_id: uuid.UUID | None, limit: int, offset: int
) -> Page[IdentificationRunRead]:
    items = run_repo.list_runs(db, status=status, query_image_id=query_image_id, limit=limit, offset=offset)
    return Page[IdentificationRunRead](
        items=[IdentificationRunRead.model_validate(r) for r in items],
        total=run_repo.count_runs(db, status=status, query_image_id=query_image_id),
        limit=limit,
        offset=offset,
    )


def get_run(db: Session, run_id: uuid.UUID) -> IdentificationRun:
    return run_repo.get_run(db, run_id, with_candidates=True)


def list_candidates(db: Session, run_id: uuid.UUID) -> list[IdentificationCandidate]:
    run_repo.get_run(db, run_id)
    return run_repo.list_candidates(db, run_id)


def list_verifications(db: Session, run_id: uuid.UUID) -> list[Verification]:
    run_repo.get_run(db, run_id)
    return verification_repo.list_verifications(db, run_id)


def submit_identification_run(
    db: Session,
    storage: SupabaseStorage,
    settings: Settings,
    body: IdentificationSubmitRequest,
    *,
    recognizer: Callable[..., RecognitionResult] = identify_with_cached_gallery,
) -> IdentificationRun:
    """Execute MegaDescriptor-L-384 v1 candidate retrieval against active gallery entries."""
    caps = get_recognition_capabilities(settings)
    if not caps.available:
        raise ServiceUnavailableError(
            caps.reason or "MegaDescriptor recognition runtime is unavailable.",
            code="recognition_unavailable",
        )

    query_image = image_repo.get_image_asset(db, body.query_image_id)
    active_gallery = gallery_repo.list_active_gallery(db)
    gallery_specs = [
        (str(entry.image_asset_id), str(entry.zebra_id), entry.image_asset.storage_path)
        for entry in active_gallery
        if entry.image_asset_id != query_image.id
    ]
    if not gallery_specs:
        raise DomainRuleError(
            "At least one active gallery reference image of an active zebra is required before running identification."
        )

    run = run_repo.create_run(
        db,
        IdentificationRunCreate(
            query_image_id=query_image.id,
            model_name=MODEL_ID,
            parameters={"top_k": body.top_k, "preprocessing": caps.preprocessing, "device": "cpu"},
            requested_by=body.requested_by,
        ),
    )
    run_repo.mark_running(db, run.id)
    db.commit()

    try:
        query_bytes = storage.download(query_image.storage_path)
        result = recognizer(
            settings=settings,
            query_bytes=query_bytes,
            gallery_specs=gallery_specs,
            download_bytes=storage.download,
            top_k=body.top_k,
            exclude_image_id=str(query_image.id),
        )
    except StorageError as exc:
        logger.error("Storage download failed for identification run %s: %s", run.id, exc)
        run_repo.fail_run(
            db,
            run.id,
            RunFailure(
                error_code="storage_error",
                error_message="Could not download query or reference image from private storage.",
            ),
        )
        db.commit()
        raise AppError(
            "Could not download image from private storage for identification.",
            status_code=502,
            code="storage_error",
        ) from None
    except RecognitionNotConfiguredError as exc:
        run_repo.fail_run(
            db,
            run.id,
            RunFailure(error_code="recognition_unavailable", error_message=str(exc)),
        )
        db.commit()
        raise ServiceUnavailableError(str(exc), code="recognition_unavailable") from None
    except (RecognitionRuntimeError, ValueError) as exc:
        logger.error("Recognition error for run %s: %s", run.id, exc)
        run_repo.fail_run(
            db,
            run.id,
            RunFailure(error_code="recognition_failed", error_message="Recognition engine failed to process the image."),
        )
        db.commit()
        raise AppError(
            "Recognition engine failed to process the image.",
            status_code=502,
            code="recognition_failed",
        ) from None
    except Exception as exc:
        logger.exception("Unexpected error during identification run %s", run.id)
        run_repo.fail_run(
            db,
            run.id,
            RunFailure(error_code="recognition_error", error_message=f"Unexpected recognition failure ({type(exc).__name__})."),
        )
        db.commit()
        raise AppError(
            "Unexpected failure during MegaDescriptor identification.",
            status_code=502,
            code="recognition_error",
        ) from None

    candidates = [
        CandidateCreate(
            rank=c.rank,
            zebra_id=uuid.UUID(c.zebra_id),
            matched_reference_image_id=uuid.UUID(c.matched_reference_image_id),
            similarity_score=c.similarity_score,
            score_type=result.score_type,
            evidence={
                "method": "megadescriptor_l_384_v1",
                "preprocessing": result.preprocessing,
                "top1_top2_margin": result.margin if c.rank == 1 else None,
            },
        )
        for c in result.candidates
    ]

    completed = run_repo.complete_run(
        db,
        run.id,
        RunCompletion(
            candidates=candidates,
            model_version=result.model_version,
            predicted_unknown=None,
            processing_metadata={
                "device": result.device,
                "preprocessing": result.preprocessing,
                "score_type": result.score_type,
                "margin": result.margin,
                "inference_seconds": result.inference_seconds,
                "model_load_seconds": result.model_load_seconds,
                "total_seconds": result.total_seconds,
                "rss_mb": result.rss_mb,
                "gallery_reference_count": result.gallery_reference_count,
                "gallery_identity_count": result.gallery_identity_count,
                "gallery_cache_hits": result.gallery_cache_hits,
                "gallery_cache_misses": result.gallery_cache_misses,
                "gallery_cache_removals": result.gallery_cache_removals,
            },
        ),
    )
    db.commit()
    return completed


def submit_verification(db: Session, run_id: uuid.UUID, body: VerificationSubmit) -> Verification:
    """Append a human decision. Repository rules: run must be completed; candidate must
    belong to the run; confirmed needs a candidate linked to a registered zebra."""
    run_repo.get_run(db, run_id)
    if body.candidate_id is not None and db.get(IdentificationCandidate, body.candidate_id) is None:
        raise InvalidReferenceError("candidate not found", details={"field": "candidate_id"})
    verification = verification_repo.create_verification(db, VerificationCreate(run_id=run_id, **body.model_dump()))
    db.commit()
    return verification
