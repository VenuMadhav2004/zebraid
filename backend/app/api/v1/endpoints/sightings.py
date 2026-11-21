import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, Paging
from app.core.errors import error_responses
from app.schemas import Page, SightingCreate, SightingRead, SightingUpdate
from app.services import sightings as sighting_service

router = APIRouter(prefix="/sightings", tags=["sightings"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SightingRead,
    summary="Record a sighting",
    responses=error_responses(422),
)
def create_sighting(db: DbSession, body: SightingCreate):
    """`zebra_id` is optional: omit it for an unidentified animal (no zebra is created).
    Referenced zebra/image/run must exist (422 `invalid_reference`)."""
    return sighting_service.create_sighting(db, body)


@router.get("", response_model=Page[SightingRead], summary="List sightings", responses=error_responses(422))
def list_sightings(
    db: DbSession,
    page: Paging,
    zebra_id: uuid.UUID | None = None,
    unidentified_only: bool = False,
    since: Annotated[datetime | None, Query(description="observed_at >= since")] = None,
    until: Annotated[datetime | None, Query(description="observed_at < until")] = None,
    location_name: Annotated[str | None, Query(max_length=200, description="Substring, case-insensitive")] = None,
    min_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    max_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    min_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    max_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
):
    """Newest observation first."""
    return sighting_service.list_sightings(
        db,
        limit=page.limit,
        offset=page.offset,
        zebra_id=zebra_id,
        unidentified_only=unidentified_only,
        since=since,
        until=until,
        location_name=location_name,
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
    )


@router.get(
    "/{sighting_id}", response_model=SightingRead, summary="Get a sighting", responses=error_responses(404, 422)
)
def get_sighting(db: DbSession, sighting_id: uuid.UUID):
    return sighting_service.get_sighting(db, sighting_id)


@router.patch(
    "/{sighting_id}", response_model=SightingRead, summary="Update a sighting", responses=error_responses(404, 422)
)
def update_sighting(db: DbSession, sighting_id: uuid.UUID, body: SightingUpdate):
    """Only sent fields change. `zebra_id: null` marks it unidentified."""
    return sighting_service.update_sighting(db, sighting_id, body)


@router.delete(
    "/{sighting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a sighting",
    responses=error_responses(404, 422),
)
def delete_sighting(db: DbSession, sighting_id: uuid.UUID) -> None:
    """Linked images and identification runs are kept."""
    sighting_service.delete_sighting(db, sighting_id)
