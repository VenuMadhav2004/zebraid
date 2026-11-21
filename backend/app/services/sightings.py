"""Sighting workflows. A sighting may stay unidentified (zebra_id null); identity
is never inferred here."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import AppError, InvalidReferenceError
from app.models import IdentificationRun, ImageAsset, Sighting, Zebra
from app.repositories import sightings as sighting_repo
from app.schemas import Page, SightingCreate, SightingRead, SightingUpdate


def _require(db: Session, model, obj_id: uuid.UUID | None, field: str):
    if obj_id is None:
        return None
    obj = db.get(model, obj_id)
    if obj is None:
        raise InvalidReferenceError(f"{field} does not reference an existing record", details={"field": field})
    return obj


def _check_run_matches_image(run: IdentificationRun | None, image: ImageAsset | None) -> None:
    """A linked run must have been run on the sighting's image (or a crop of it)."""
    if run is None or image is None:
        return
    query = run.query_image
    if query.id != image.id and query.source_image_id != image.id:
        raise AppError(
            "identification_run_id was not run on image_asset_id (or a crop of it)",
            status_code=422,
            code="inconsistent_reference",
        )


def create_sighting(db: Session, data: SightingCreate) -> Sighting:
    _require(db, Zebra, data.zebra_id, "zebra_id")
    image = _require(db, ImageAsset, data.image_asset_id, "image_asset_id")
    run = _require(db, IdentificationRun, data.identification_run_id, "identification_run_id")
    _check_run_matches_image(run, image)
    sighting = sighting_repo.create_sighting(db, data)
    db.commit()
    return sighting


def list_sightings(db: Session, *, limit: int, offset: int, **filters) -> Page[SightingRead]:
    items = sighting_repo.list_sightings(db, limit=limit, offset=offset, **filters)
    return Page[SightingRead](
        items=[SightingRead.model_validate(s) for s in items],
        total=sighting_repo.count_sightings(db, **filters),
        limit=limit,
        offset=offset,
    )


def get_sighting(db: Session, sighting_id: uuid.UUID) -> Sighting:
    return sighting_repo.get_sighting(db, sighting_id)


def update_sighting(db: Session, sighting_id: uuid.UUID, data: SightingUpdate) -> Sighting:
    sighting_repo.get_sighting(db, sighting_id)
    if "zebra_id" in data.model_fields_set:
        _require(db, Zebra, data.zebra_id, "zebra_id")
    sighting = sighting_repo.update_sighting(db, sighting_id, data)
    db.commit()
    return sighting


def delete_sighting(db: Session, sighting_id: uuid.UUID) -> None:
    """Removes the observation only; linked images and runs are kept."""
    sighting_repo.delete_sighting(db, sighting_id)
    db.commit()
