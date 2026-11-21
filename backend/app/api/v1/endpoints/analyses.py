"""Scientific stripe analysis endpoints (Member 1 morphology + Member 2 spatial frequency)."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import DbSession, Paging, Storage
from app.core.config import get_settings
from app.core.errors import error_responses
from app.models import AnalysisKind, RunStatus
from app.schemas import (
    AnalysisCapabilitiesResponse,
    AnalysisJobRead,
    CombinedAnalysisRequest,
    CombinedAnalysisResponse,
    FrequencyAnalysisRequest,
    MorphologyAnalysisRequest,
    Page,
    SignedUrlResponse,
)
from app.services import stripe_analyses as analysis_service

router = APIRouter(prefix="/analyses", tags=["analyses"])


def _notify_dispatcher(request: Request) -> None:
    dispatcher = getattr(request.app.state, "analysis_dispatcher", None)
    if dispatcher is not None:
        dispatcher.notify()


@router.get(
    "/capabilities",
    response_model=AnalysisCapabilitiesResponse,
    summary="Check scientific analysis availability and limits",
)
def get_capabilities(db: DbSession, refresh: bool = False):
    return analysis_service.get_capabilities(get_settings(), refresh=refresh, db=db)


@router.post(
    "/stripe-morphology",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AnalysisJobRead,
    summary="Submit a Member 1 stripe morphology analysis job",
    responses=error_responses(404, 422, 503),
)
def submit_stripe_morphology(request: Request, db: DbSession, body: MorphologyAnalysisRequest):
    return analysis_service.submit_morphology(
        db,
        get_settings(),
        body,
        on_enqueued=lambda: _notify_dispatcher(request),
    )


@router.post(
    "/spatial-frequency",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AnalysisJobRead,
    summary="Submit a Member 2 spatial-frequency analysis job",
    responses=error_responses(404, 422, 503),
)
def submit_spatial_frequency(request: Request, db: DbSession, body: FrequencyAnalysisRequest):
    return analysis_service.submit_frequency(
        db,
        get_settings(),
        body,
        on_enqueued=lambda: _notify_dispatcher(request),
    )


@router.post(
    "/combined",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CombinedAnalysisResponse,
    summary="Submit both Member 1 morphology and Member 2 spatial-frequency jobs on the same image and ROI",
    responses=error_responses(404, 422, 503),
)
def submit_combined_analysis(request: Request, db: DbSession, body: CombinedAnalysisRequest):
    return analysis_service.submit_combined(
        db,
        get_settings(),
        body,
        on_enqueued=lambda: _notify_dispatcher(request),
    )


@router.get(
    "",
    response_model=Page[AnalysisJobRead],
    summary="List scientific analysis jobs",
    responses=error_responses(422, 503),
)
def list_analyses(
    db: DbSession,
    page: Paging,
    image_id: uuid.UUID | None = None,
    kind: AnalysisKind | None = None,
    status_: Annotated[RunStatus | None, Query(alias="status")] = None,
):
    return analysis_service.list_analyses(
        db,
        image_id=image_id,
        kind=kind,
        status=status_,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{analysis_id}",
    response_model=AnalysisJobRead,
    summary="Get an analysis job and sanitized results",
    responses=error_responses(404, 422, 503),
)
def get_analysis(db: DbSession, analysis_id: uuid.UUID):
    return analysis_service.get_analysis(db, analysis_id)


@router.get(
    "/{analysis_id}/artifacts/{artifact_name}/url",
    response_model=SignedUrlResponse,
    summary="Get a temporary signed URL for a generated artifact PNG",
    responses=error_responses(404, 422, 502, 503),
)
def get_artifact_url(
    db: DbSession,
    storage: Storage,
    analysis_id: uuid.UUID,
    artifact_name: str,
    expires_in: Annotated[int | None, Query(ge=1, le=3600, description="Seconds; default 60")] = None,
):
    return analysis_service.artifact_signed_url(db, storage, analysis_id, artifact_name, expires_in)


@router.delete(
    "/{analysis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete an analysis job and its stored PNG artifacts",
    responses=error_responses(404, 409, 422, 503),
)
def delete_analysis(db: DbSession, storage: Storage, analysis_id: uuid.UUID) -> None:
    analysis_service.delete_analysis(db, storage, analysis_id)
