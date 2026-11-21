"""Zebra profile workflows. Profiles are created by people, never by inference."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import Zebra, ZebraStatus
from app.repositories import zebras as zebra_repo
from app.schemas import Page, ZebraCreate, ZebraRead, ZebraUpdate


def create_zebra(db: Session, data: ZebraCreate) -> Zebra:
    existing = zebra_repo.get_zebra_by_code(db, data.code)
    if existing is not None:
        raise ConflictError(
            f"zebra code {data.code!r} already exists", code="zebra_code_exists", details={"zebra_id": str(existing.id)}
        )
    zebra = zebra_repo.create_zebra(db, data)
    db.commit()
    return zebra


def list_zebras(
    db: Session,
    *,
    status: ZebraStatus | None,
    search: str | None,
    species: str | None,
    sex: str | None,
    limit: int,
    offset: int,
    sort: str = "code",
) -> Page[ZebraRead]:
    filters = dict(status=status, search=search, species=species, sex=sex)
    items = zebra_repo.list_zebras(db, **filters, sort=sort, limit=limit, offset=offset)
    return Page[ZebraRead](
        items=[ZebraRead.model_validate(z) for z in items],
        total=zebra_repo.count_zebras(db, **filters),
        limit=limit,
        offset=offset,
    )


def get_zebra(db: Session, zebra_id: uuid.UUID) -> Zebra:
    return zebra_repo.get_zebra(db, zebra_id)


def update_zebra(db: Session, zebra_id: uuid.UUID, data: ZebraUpdate) -> Zebra:
    zebra = zebra_repo.update_zebra(db, zebra_id, data)
    db.commit()
    return zebra


def delete_zebra(db: Session, zebra_id: uuid.UUID) -> None:
    """Hard delete only for profiles nothing else refers to. Gallery links are
    removed with the zebra; their image assets are kept."""
    zebra_repo.get_zebra(db, zebra_id)
    refs = {k: v for k, v in zebra_repo.reference_counts(db, zebra_id).items() if v}
    if refs:
        raise ConflictError(
            "zebra is referenced by other records; set status to inactive or deceased instead",
            code="zebra_in_use",
            details=refs,
        )
    zebra_repo.delete_zebra(db, zebra_id)
    db.commit()
