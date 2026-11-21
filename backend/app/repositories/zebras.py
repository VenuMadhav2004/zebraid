import uuid
from collections.abc import Iterable

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import Zebra, ZebraStatus
from app.repositories.base import LIKE_ESCAPE, apply_update, get_or_raise, like_pattern, orm_kwargs
from app.schemas import ZebraCreate, ZebraUpdate


def create_zebra(db: Session, data: ZebraCreate) -> Zebra:
    zebra = Zebra(**orm_kwargs(data))
    db.add(zebra)
    db.flush()
    return zebra


def get_zebra(db: Session, zebra_id: uuid.UUID) -> Zebra:
    return get_or_raise(db, Zebra, zebra_id)


def get_zebra_by_code(db: Session, code: str) -> Zebra | None:
    return db.scalar(select(Zebra).where(Zebra.code == code))


def _zebra_filters(
    stmt: Select, *, status: ZebraStatus | None, search: str | None, species: str | None, sex: str | None
) -> Select:
    if status is not None:
        stmt = stmt.where(Zebra.status == status)
    if search:
        like = like_pattern(search)
        stmt = stmt.where(or_(Zebra.code.ilike(like, escape=LIKE_ESCAPE), Zebra.name.ilike(like, escape=LIKE_ESCAPE)))
    if species:
        stmt = stmt.where(func.lower(Zebra.species) == species.lower())
    if sex:
        stmt = stmt.where(func.lower(Zebra.sex) == sex.lower())
    return stmt


def list_zebras(
    db: Session,
    *,
    status: ZebraStatus | None = None,
    search: str | None = None,
    species: str | None = None,
    sex: str | None = None,
    sort: str = "code",
    limit: int = 100,
    offset: int = 0,
) -> list[Zebra]:
    """sort: "code" (A-Z) or "-created_at" (newest first)."""
    stmt = _zebra_filters(select(Zebra), status=status, search=search, species=species, sex=sex)
    order = (Zebra.created_at.desc(), Zebra.id) if sort == "-created_at" else (Zebra.code,)
    return list(db.scalars(stmt.order_by(*order).limit(limit).offset(offset)))


def count_zebras(
    db: Session,
    *,
    status: ZebraStatus | None = None,
    search: str | None = None,
    species: str | None = None,
    sex: str | None = None,
) -> int:
    stmt = _zebra_filters(select(func.count()).select_from(Zebra), status=status, search=search, species=species, sex=sex)
    return db.scalar(stmt) or 0


def reference_counts(db: Session, zebra_id: uuid.UUID) -> dict[str, int]:
    """Rows that block deleting a zebra (RESTRICT foreign keys)."""
    from app.models import IdentificationCandidate, Sighting, Verification

    def n(model) -> int:
        return db.scalar(select(func.count()).select_from(model).where(model.zebra_id == zebra_id)) or 0

    return {
        "sightings": n(Sighting),
        "identification_candidates": n(IdentificationCandidate),
        "verifications": n(Verification),
    }


def update_zebra(db: Session, zebra_id: uuid.UUID, data: ZebraUpdate) -> Zebra:
    return apply_update(db, get_zebra(db, zebra_id), data)


def delete_zebra(db: Session, zebra_id: uuid.UUID) -> None:
    """Deletes gallery links (CASCADE). Fails (IntegrityError) if sightings,
    candidates or verifications reference the zebra: retire it via status instead."""
    db.delete(get_zebra(db, zebra_id))
    db.flush()


def resolve_labels(db: Session, labels: Iterable[str]) -> dict[str, uuid.UUID | None]:
    """Map recognition-engine identity labels to registered Zebra ids.

    ASSUMPTION: the gallery handed to the recognition engine labels each reference
    with str(zebra.id) or zebra.code. Labels matching neither map to None and must be
    stored as IdentificationCandidate.external_label (no Zebra is invented).
    """
    labels = list(dict.fromkeys(labels))
    as_uuid: dict[str, uuid.UUID] = {}
    for label in labels:
        try:
            as_uuid[label] = uuid.UUID(label)
        except ValueError:
            pass
    found_ids = set(db.scalars(select(Zebra.id).where(Zebra.id.in_(as_uuid.values())))) if as_uuid else set()
    by_code = dict(db.execute(select(Zebra.code, Zebra.id).where(Zebra.code.in_(labels))).tuples().all())
    result: dict[str, uuid.UUID | None] = {}
    for label in labels:
        if label in as_uuid and as_uuid[label] in found_ids:
            result[label] = as_uuid[label]
        else:
            result[label] = by_code.get(label)
    return result
