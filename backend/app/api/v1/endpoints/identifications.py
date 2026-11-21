"""Identification runs, MegaDescriptor-L-384 v1 candidate retrieval, and human review.

`similarity_score` is a cosine similarity, not a probability or confidence percentage.
Human verification is always required to confirm an identity.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, Paging, Storage
from app.core.config import get_settings
from app.core.errors import error_responses
from app.models import RunStatus
from app.schemas import (
    CandidateRead,
    IdentificationRunDetail,
    IdentificationRunRead,
    IdentificationSubmitRequest,
    Page,
    RecognitionCapabilityResponse,
    VerificationRead,
    VerificationSubmit,
)
from app.services import identifications as identification_service

router = APIRouter(prefix="/identifications", tags=["identifications"])


@router.get(
    "/capabilities",
    response_model=RecognitionCapabilityResponse,
    summary="Check MegaDescriptor-L-384 v1 CPU recognition availability",
)
def get_recognition_capabilities():
    return identification_service.get_recognition_capabilities(get_settings())


@router.get(
    "", response_model=Page[IdentificationRunRead], summary="List identification runs", responses=error_responses(422)
)
def list_runs(
    db: DbSession,
    page: Paging,
    status_: Annotated[RunStatus | None, Query(alias="status")] = None,
    query_image_id: uuid.UUID | None = None,
):
    """Newest first."""
    return identification_service.list_runs(
        db, status=status_, query_image_id=query_image_id, limit=page.limit, offset=page.offset
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=IdentificationRunDetail,
    summary="Run MegaDescriptor-L-384 v1 candidate retrieval on a stored query/crop image",
    responses=error_responses(404, 422, 502, 503),
)
def submit_identification(db: DbSession, storage: Storage, body: IdentificationSubmitRequest):
    """Retrieves ranked gallery candidates using cached CPU embeddings; never auto-confirms identity."""
    return identification_service.submit_identification_run(db, storage, get_settings(), body)


@router.get(
    "/{run_id}",
    response_model=IdentificationRunDetail,
    summary="Get a run with its ranked candidates",
    responses=error_responses(404, 422),
)
def get_run(db: DbSession, run_id: uuid.UUID):
    return identification_service.get_run(db, run_id)


@router.get(
    "/{run_id}/candidates",
    response_model=list[CandidateRead],
    summary="Ranked candidates of a run",
    responses=error_responses(404, 422),
)
def list_candidates(db: DbSession, run_id: uuid.UUID):
    """Suggestions only, ordered by rank. A candidate is never an identity claim."""
    return identification_service.list_candidates(db, run_id)


@router.get(
    "/{run_id}/verifications",
    response_model=list[VerificationRead],
    summary="Human review history of a run",
    responses=error_responses(404, 422),
)
def list_verifications(db: DbSession, run_id: uuid.UUID):
    """Oldest first; the latest row is the current decision."""
    return identification_service.list_verifications(db, run_id)


@router.post(
    "/{run_id}/verifications",
    status_code=status.HTTP_201_CREATED,
    response_model=VerificationRead,
    summary="Record a human review decision",
    responses=error_responses(404, 422),
)
def submit_verification(db: DbSession, run_id: uuid.UUID, body: VerificationSubmit):
    """`confirmed` and `rejected` need `candidate_id` of this run; `unknown` must not set it.
    Only completed runs can be reviewed, and only candidates linked to a registered zebra
    can be confirmed. Decisions are append-only."""
    return identification_service.submit_verification(db, run_id, body)
