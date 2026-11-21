"""Shared repository helpers.

Repositories take a Session, flush (to surface DB errors and get defaults) and
never commit. The caller (API handler / job) owns the transaction.
"""
import uuid
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.base import Base

T = TypeVar("T", bound=Base)

# Pydantic field name -> ORM attribute name (where the column name is reserved)
_FIELD_ALIASES = {"metadata": "metadata_"}


class RepositoryError(Exception):
    """Base for domain errors raised by repositories."""


class NotFoundError(RepositoryError):
    pass


class DomainRuleError(RepositoryError):
    """A request violates a business rule that the schema alone cannot express."""


LIKE_ESCAPE = "\\"


def like_pattern(term: str) -> str:
    """Substring ILIKE pattern with %, _ and the escape character escaped."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def get_or_raise(db: Session, model: type[T], obj_id: uuid.UUID) -> T:
    obj = db.get(model, obj_id)
    if obj is None:
        raise NotFoundError(f"{model.__name__} {obj_id} not found")
    return obj


def orm_kwargs(data: BaseModel, *, exclude_unset: bool = False) -> dict:
    raw = data.model_dump(exclude_unset=exclude_unset)
    return {_FIELD_ALIASES.get(k, k): v for k, v in raw.items()}


def apply_update(db: Session, obj: T, data: BaseModel) -> T:
    """Apply only fields the client actually sent (PATCH semantics)."""
    for key, value in orm_kwargs(data, exclude_unset=True).items():
        setattr(obj, key, value)
    db.flush()
    return obj
