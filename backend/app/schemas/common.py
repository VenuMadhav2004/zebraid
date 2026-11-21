import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Timestamped(ORMModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class Page(BaseModel, Generic[T]):
    """Offset pagination envelope used by every list endpoint."""

    items: list[T]
    total: int = Field(description="Number of records matching the filters (all pages)")
    limit: int
    offset: int


def reject_nulls(model: BaseModel, *fields: str) -> None:
    """PATCH bodies: a field may be omitted, but these must not be sent as null
    (the column is NOT NULL)."""
    for name in fields:
        if name in model.model_fields_set and getattr(model, name) is None:
            raise ValueError(f"{name} cannot be null")
