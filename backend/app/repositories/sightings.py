import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Sighting
from app.repositories.base import LIKE_ESCAPE, apply_update, get_or_raise, like_pattern, orm_kwargs
from app.schemas import SightingCreate, SightingUpdate


def create_sighting(db: Session, data: SightingCreate) -> Sighting:
    sighting = Sighting(**orm_kwargs(data))
    db.add(sighting)
    db.flush()
    return sighting


def get_sighting(db: Session, sighting_id: uuid.UUID) -> Sighting:
    return get_or_raise(db, Sighting, sighting_id)


def _sighting_filters(
    stmt: Select,
    *,
    zebra_id: uuid.UUID | None = None,
    unidentified_only: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    location_name: str | None = None,
    min_lat: float | None = None,
    max_lat: float | None = None,
    min_lon: float | None = None,
    max_lon: float | None = None,
) -> Select:
    if zebra_id is not None:
        stmt = stmt.where(Sighting.zebra_id == zebra_id)
    if unidentified_only:
        stmt = stmt.where(Sighting.zebra_id.is_(None))
    if since is not None:
        stmt = stmt.where(Sighting.observed_at >= since)
    if until is not None:
        stmt = stmt.where(Sighting.observed_at < until)
    if location_name:
        stmt = stmt.where(Sighting.location_name.ilike(like_pattern(location_name), escape=LIKE_ESCAPE))
    if min_lat is not None:
        stmt = stmt.where(Sighting.latitude >= min_lat)
    if max_lat is not None:
        stmt = stmt.where(Sighting.latitude <= max_lat)
    if min_lon is not None:
        stmt = stmt.where(Sighting.longitude >= min_lon)
    if max_lon is not None:
        stmt = stmt.where(Sighting.longitude <= max_lon)
    return stmt


def list_sightings(db: Session, *, limit: int = 100, offset: int = 0, **filters) -> list[Sighting]:
    """Filters: zebra_id, unidentified_only, since, until (exclusive), location_name
    (substring), min_lat/max_lat/min_lon/max_lon (bounding box)."""
    stmt = _sighting_filters(select(Sighting), **filters)
    return list(db.scalars(stmt.order_by(Sighting.observed_at.desc(), Sighting.id).limit(limit).offset(offset)))


def count_sightings(db: Session, **filters) -> int:
    return db.scalar(_sighting_filters(select(func.count()).select_from(Sighting), **filters)) or 0


def update_sighting(db: Session, sighting_id: uuid.UUID, data: SightingUpdate) -> Sighting:
    return apply_update(db, get_sighting(db, sighting_id), data)


def delete_sighting(db: Session, sighting_id: uuid.UUID) -> None:
    db.delete(get_sighting(db, sighting_id))
    db.flush()
