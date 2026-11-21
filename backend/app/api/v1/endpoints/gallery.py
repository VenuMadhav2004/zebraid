import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, Paging, get_storage
from app.core.errors import error_responses
from app.schemas import GalleryEntryRegister, GalleryEntryWithImage, Page
from app.services import gallery as gallery_service

router = APIRouter(tags=["gallery"])


@router.post(
    "/zebras/{zebra_id}/gallery",
    status_code=status.HTTP_201_CREATED,
    response_model=GalleryEntryWithImage,
    summary="Add an image to a zebra's gallery",
    responses=error_responses(404, 409, 422),
)
def add_gallery_image(db: DbSession, zebra_id: uuid.UUID, body: GalleryEntryRegister):
    """The image must be of kind `reference` or `crop` (422 otherwise) and not already in any
    gallery (409 `image_already_in_gallery`). Application records only: no ML registration."""
    return gallery_service.register(db, zebra_id, body)


@router.get(
    "/zebras/{zebra_id}/gallery",
    response_model=Page[GalleryEntryWithImage],
    summary="List a zebra's gallery",
    responses=error_responses(404, 422, 502, 503),
)
def list_gallery(
    db: DbSession,
    zebra_id: uuid.UUID,
    page: Paging,
    include_inactive: bool = False,
    include_urls: Annotated[bool, Query(description="Add a short-lived signed URL per image")] = False,
    expires_in: Annotated[int | None, Query(ge=1, le=3600)] = None,
):
    storage = get_storage() if include_urls else None
    return gallery_service.list_for_zebra(
        db,
        storage,
        zebra_id,
        include_inactive=include_inactive,
        expires_in=expires_in,
        limit=page.limit,
        offset=page.offset,
    )


@router.delete(
    "/gallery/{gallery_entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an image from a gallery",
    responses=error_responses(404, 422),
)
def remove_gallery_entry(db: DbSession, gallery_entry_id: uuid.UUID) -> None:
    """Unlinks the image from the zebra. The image asset and its stored file are kept."""
    gallery_service.remove(db, gallery_entry_id)
