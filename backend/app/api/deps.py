"""Shared FastAPI dependencies for API routers.

Usage in a route:

    def handler(db: DbSession, storage: Storage, page: Paging): ...

`DbSession` yields a request-scoped Session; service functions commit and any
exception rolls it back (see app.database.session.get_db).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ServiceUnavailableError
from app.database.session import get_db
from app.integrations.supabase_storage import SupabaseStorage

DbSession = Annotated[Session, Depends(get_db)]

_storage: SupabaseStorage | None = None
_storage_lock = threading.Lock()


def get_storage() -> SupabaseStorage:
    """Process-wide Storage client (reuses one HTTP connection pool)."""
    global _storage
    if _storage is None:
        with _storage_lock:
            if _storage is None:
                settings = get_settings()
                if not (settings.supabase_url and settings.supabase_service_role_key.strip()):
                    raise ServiceUnavailableError("Storage is not configured", code="storage_not_configured")
                _storage = SupabaseStorage.from_settings(settings)
    return _storage


def close_storage() -> None:
    global _storage
    if _storage is not None:
        _storage._client.close()
    _storage = None


Storage = Annotated[SupabaseStorage, Depends(get_storage)]

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def get_pagination(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Page size")] = 20,
    offset: Annotated[int, Query(ge=0, description="Records to skip")] = 0,
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


Paging = Annotated[Pagination, Depends(get_pagination)]
