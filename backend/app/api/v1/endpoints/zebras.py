import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, Paging
from app.core.errors import error_responses
from app.models import ZebraStatus
from app.schemas import Page, ZebraCreate, ZebraRead, ZebraUpdate
from app.services import zebras as zebra_service

router = APIRouter(prefix="/zebras", tags=["zebras"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ZebraRead,
    summary="Create a zebra profile",
    responses=error_responses(409, 422),
)
def create_zebra(db: DbSession, body: ZebraCreate):
    """`code` must be unique (409 `zebra_code_exists`). Profiles are created by people only."""
    return zebra_service.create_zebra(db, body)


@router.get("", response_model=Page[ZebraRead], summary="List zebras", responses=error_responses(422))
def list_zebras(
    db: DbSession,
    page: Paging,
    status_: Annotated[ZebraStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=120, description="Substring of code or name")] = None,
    species: Annotated[str | None, Query(max_length=80, description="Exact match, case-insensitive")] = None,
    sex: Annotated[str | None, Query(max_length=20, description="Exact match, case-insensitive")] = None,
    sort: Annotated[Literal["code", "-created_at"], Query(description="`code` (A-Z, default) or `-created_at` (newest first)")] = "code",
):
    return zebra_service.list_zebras(
        db, status=status_, search=search, species=species, sex=sex, sort=sort, limit=page.limit, offset=page.offset
    )


@router.get("/{zebra_id}", response_model=ZebraRead, summary="Get a zebra", responses=error_responses(404, 422))
def get_zebra(db: DbSession, zebra_id: uuid.UUID):
    return zebra_service.get_zebra(db, zebra_id)


@router.patch(
    "/{zebra_id}", response_model=ZebraRead, summary="Update a zebra", responses=error_responses(404, 422)
)
def update_zebra(db: DbSession, zebra_id: uuid.UUID, body: ZebraUpdate):
    """Only sent fields change. `code` is immutable. `status` and `attributes` cannot be null."""
    return zebra_service.update_zebra(db, zebra_id, body)


@router.delete(
    "/{zebra_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a zebra",
    responses=error_responses(404, 409, 422),
)
def delete_zebra(db: DbSession, zebra_id: uuid.UUID) -> None:
    """Allowed only when no sightings, identification candidates or verifications reference
    the zebra (otherwise 409 `zebra_in_use`: retire it with `status` instead).
    Its gallery links are removed; the image assets are kept."""
    zebra_service.delete_zebra(db, zebra_id)
