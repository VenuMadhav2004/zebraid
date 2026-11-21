"""Integration fixtures against the configured Supabase PostgreSQL.

Every test runs inside an outer transaction that is rolled back, so nothing is
persisted. Repository flushes and savepoints work normally inside it.
Requires the migration to be applied (`alembic upgrade head`).
"""
import os
import uuid

# Never load the 1.9 GB recognition checkpoint just because a test app runs its lifespan.
os.environ.setdefault("RECOGNITION_PRELOAD", "false")
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ImageKind
from app.repositories import gallery as gallery_repo
from app.repositories import images as image_repo
from app.repositories import zebras as zebra_repo
from app.schemas import CropBox, GalleryEntryCreate, ImageAssetCreate, ZebraCreate

BUCKET = "zebra_images"


def pytest_collection_modifyitems(config, items):
    """Mark by folder; skip integration tests whose service is not configured."""
    s = get_settings()
    skip_db = pytest.mark.skip(reason="DATABASE_URL not configured")
    skip_storage = pytest.mark.skip(reason="SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
    for item in items:
        path = str(item.fspath)
        if "/tests/unit/" in path:
            item.add_marker(pytest.mark.unit)
            continue
        item.add_marker(pytest.mark.integration)
        if not s.database_url and ("db" in item.fixturenames or "engine" in item.fixturenames):
            item.add_marker(skip_db)
        if item.get_closest_marker("storage") and not (s.supabase_url and s.supabase_service_role_key.strip()):
            item.add_marker(skip_storage)


@pytest.fixture(scope="session")
def engine():
    from app.database.session import get_engine

    return get_engine()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@contextmanager
def expect_integrity_error(db: Session, constraint: str | None = None):
    """Run a block in a savepoint; assert the DB rejects it; keep the session usable."""
    sp = db.begin_nested()
    with pytest.raises(IntegrityError) as exc:
        yield
        db.flush()
    sp.rollback()
    if constraint:
        assert constraint in str(exc.value.orig), str(exc.value.orig)


def _uid() -> str:
    return uuid.uuid4().hex[:10]


@pytest.fixture
def make_zebra(db) -> Callable:
    def _make(**kw):
        kw.setdefault("code", f"T-{_uid()}")
        return zebra_repo.create_zebra(db, ZebraCreate(**kw))

    return _make


@pytest.fixture
def make_image(db) -> Callable:
    def _make(kind: ImageKind = ImageKind.QUERY, **kw):
        kw.setdefault("storage_bucket", BUCKET)
        kw.setdefault("storage_path", f"test/{_uid()}.jpg")
        kw.setdefault("content_type", "image/jpeg")
        kw.setdefault("width", 1000)
        kw.setdefault("height", 800)
        if kind == ImageKind.CROP and "source_image_id" not in kw:
            kw["source_image_id"] = _make(ImageKind.QUERY).id
            kw.setdefault("crop_bbox", CropBox(x=10, y=10, width=256, height=256))
        return image_repo.create_image_asset(db, ImageAssetCreate(kind=kind, **kw))

    return _make


@pytest.fixture
def make_gallery_zebra(db, make_zebra, make_image) -> Callable:
    """A zebra with `n` registered reference images."""

    def _make(n: int = 1, **zebra_kw):
        zebra = make_zebra(**zebra_kw)
        entries = [
            gallery_repo.register_gallery_entry(
                db, GalleryEntryCreate(zebra_id=zebra.id, image_asset_id=make_image(ImageKind.REFERENCE).id)
            )
            for _ in range(n)
        ]
        return zebra, entries

    return _make


# -- API fixtures (Phase 3.2) ---------------------------------------------------
import io  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.integrations.supabase_storage import (  # noqa: E402
    SignedUrl,
    StorageConflictError,
    StorageError,
    StorageNotFoundError,
    validate_image,
)


def image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (64, 48), color=(120, 40, 200)) -> bytes:
    """A real, decodable image. Vary `color` to get distinct bytes/sha256."""
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


class FakeStorage:
    """In-memory stand-in for SupabaseStorage with failure switches. Same validation."""

    def __init__(self, bucket: str = BUCKET, max_upload_bytes: int = 10 * 1024 * 1024):
        self.bucket = bucket
        self.max_upload_bytes = max_upload_bytes
        self.default_ttl = 60
        self.max_ttl = 3600
        self.objects: dict[str, bytes] = {}
        self.fail_upload = self.fail_delete = self.fail_sign = False
        self._client = SimpleNamespace(close=lambda: None)

    def upload(self, path, content, content_type):
        validate_image(content, content_type, max_bytes=self.max_upload_bytes)
        if self.fail_upload:
            raise StorageError("upstream failure", 500)
        if path in self.objects:
            raise StorageConflictError("The resource already exists", 409)
        self.objects[path] = content

    def download(self, path):
        if path not in self.objects:
            raise StorageNotFoundError("Object not found", 404)
        return self.objects[path]

    def delete(self, paths):
        if self.fail_delete:
            raise StorageError("upstream failure", 500)
        return [p for p in paths if self.objects.pop(p, None) is not None]

    def _signed(self, path, ttl):
        return SignedUrl(
            url=f"https://fake.supabase.co/storage/v1/object/sign/{self.bucket}/{path}?token=t",
            expires_in=ttl,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
        )

    def signed_url(self, path, expires_in=None):
        if self.fail_sign:
            raise StorageError("upstream failure", 500)
        if path not in self.objects:
            raise StorageNotFoundError("Object not found", 404)
        return self._signed(path, expires_in or self.default_ttl)

    def signed_urls(self, paths, expires_in=None):
        if self.fail_sign:
            raise StorageError("upstream failure", 500)
        ttl = expires_in or self.default_ttl
        return {p: (self._signed(p, ttl) if p in self.objects else None) for p in paths}


@pytest.fixture
def fake_storage(monkeypatch) -> FakeStorage:
    from app.api import deps

    storage = FakeStorage()
    monkeypatch.setattr(deps, "_storage", storage)
    return storage


@pytest.fixture
def api(db, fake_storage) -> TestClient:
    """TestClient whose requests share the rolled-back test session."""
    from app.database.session import get_db
    from app.main import create_app

    app = create_app()

    def _test_db():
        yield db

    app.dependency_overrides[get_db] = _test_db
    return TestClient(app, raise_server_exceptions=False)  # no `with`: lifespan (engine dispose) not run


def upload(api: TestClient, content: bytes | None = None, *, kind: str = "query", content_type: str = "image/jpeg", **form):
    content = image_bytes() if content is None else content
    data = {"kind": kind, **{k: v for k, v in form.items() if v is not None}}
    return api.post("/api/v1/images", data=data, files={"file": ("photo.bin", content, content_type)})


def unique_color() -> tuple[int, int, int]:
    raw = uuid.uuid4().bytes
    return raw[0], raw[1], raw[2]
