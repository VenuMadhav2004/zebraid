"""Live checks against the private bucket. Every object is written under
_healthcheck/phase25/ and removed in teardown. Payloads are synthetic: valid
magic bytes followed by padding (Storage does not decode images)."""
import time
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations.supabase_storage import (
    ImageValidationError,
    StorageConflictError,
    StorageError,
    StorageNotFoundError,
    SupabaseStorage,
    generate_storage_path,
)
from app.models import ImageAsset, ImageKind
from app.repositories.base import NotFoundError
from app.schemas import CropBox
from app.services import image_storage

pytestmark = pytest.mark.storage

PREFIX = "_healthcheck/phase25"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 512
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 512
WEBP = b"RIFF\x24\x02\x00\x00WEBPVP8 " + b"\x00" * 512


@pytest.fixture(scope="module")
def storage():
    st = SupabaseStorage.from_settings()
    st.created = []  # type: ignore[attr-defined]  # every path this module may have written
    yield st
    if st.created:
        st.delete(st.created)
    leftovers = [p for p in st.created if _exists(st, p)]
    assert leftovers == [], f"cleanup failed: {leftovers}"


def _exists(st: SupabaseStorage, path: str) -> bool:
    try:
        st.download(path)
        return True
    except StorageNotFoundError:
        return False


def _path(st, ctype="image/jpeg"):
    p = generate_storage_path(ImageKind.QUERY, ctype, prefix=PREFIX)
    st.created.append(p)
    return p


def test_bucket_private_and_limited(storage):
    b = storage.get_bucket()
    s = get_settings()
    assert b["id"] == s.supabase_storage_bucket == "zebra_images"
    assert b["public"] is False
    assert b["file_size_limit"] == s.storage_max_upload_bytes
    assert sorted(b["allowed_mime_types"]) == ["image/jpeg", "image/png", "image/webp"]


@pytest.mark.parametrize("content,ctype", [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")])
def test_upload_download_delete(storage, content, ctype):
    path = _path(storage, ctype)
    storage.upload(path, content, ctype)
    assert storage.download(path) == content
    assert storage.delete([path]) == [path]
    assert not _exists(storage, path)


def test_no_overwrite(storage):
    path = _path(storage)
    storage.upload(path, JPEG, "image/jpeg")
    with pytest.raises(StorageConflictError):
        storage.upload(path, JPEG + b"changed", "image/jpeg")
    assert storage.download(path) == JPEG


def test_server_rejects_disallowed_mime(storage):
    """Bypass client-side validation to prove the bucket itself refuses."""
    path = f"{PREFIX}/raw/{uuid.uuid4().hex}.txt"
    storage.created.append(path)
    with pytest.raises(StorageError) as info:
        storage._request("POST", f"/object/{storage._obj(path)}", content=b"hello",
                         headers={"Content-Type": "text/plain", "x-upsert": "false"})
    assert info.value.status_code in (400, 415, 422)
    assert not _exists(storage, path)


def test_server_rejects_oversize(storage):
    path = _path(storage)
    too_big = b"\xff\xd8\xff\xe0" + b"\x00" * storage.max_upload_bytes
    with pytest.raises(ImageValidationError):  # client refuses first
        storage.upload(path, too_big, "image/jpeg")
    with pytest.raises(StorageError) as info:  # and so does the bucket
        storage._request("POST", f"/object/{storage._obj(path)}", content=too_big,
                         headers={"Content-Type": "image/jpeg", "x-upsert": "false"})
    assert info.value.status_code in (400, 413)
    assert not _exists(storage, path)


def test_no_anonymous_access(storage):
    path = _path(storage)
    storage.upload(path, JPEG, "image/jpeg")
    base = get_settings().supabase_url.rstrip("/") + "/storage/v1/object"
    with httpx.Client(timeout=20) as anon:
        assert anon.get(f"{base}/public/zebra_images/{path}").status_code >= 400
        assert anon.get(f"{base}/zebra_images/{path}").status_code >= 400
        assert anon.get(f"{base}/authenticated/zebra_images/{path}").status_code >= 400


def test_signed_url_works_then_expires(storage):
    path = _path(storage)
    storage.upload(path, JPEG, "image/jpeg")
    signed = storage.signed_url(path, expires_in=2)
    assert "token=" in signed.url and signed.expires_in == 2
    with httpx.Client(timeout=20) as anon:
        assert anon.get(signed.url).content == JPEG
        time.sleep(4)
        expired = anon.get(signed.url)
    assert expired.status_code >= 400
    with pytest.raises(ValueError):
        storage.signed_url(path, expires_in=storage.max_ttl + 1)


def test_signed_url_for_missing_object(storage):
    with pytest.raises(StorageNotFoundError):
        storage.signed_url(f"{PREFIX}/missing/{uuid.uuid4().hex}.jpg", expires_in=10)


def test_store_image_happy_path(db, storage):
    img = image_storage.store_image(db, storage, kind=ImageKind.QUERY, content=PNG, content_type="image/png",
                                    path_prefix=PREFIX, uploaded_by="phase25-test")
    storage.created.append(img.storage_path)
    assert img.storage_path.startswith(f"{PREFIX}/query/") and img.size_bytes == len(PNG)
    assert img.content_type == "image/png" and len(img.sha256) == 64
    assert storage.download(img.storage_path) == PNG


def test_db_failure_removes_uploaded_object(db, storage, monkeypatch):
    uploaded = []
    real_upload = storage.upload
    monkeypatch.setattr(storage, "upload", lambda p, c, t: (uploaded.append(p), storage.created.append(p), real_upload(p, c, t)))
    with pytest.raises(NotFoundError):  # crop of a nonexistent source image -> DB write fails
        image_storage.store_image(db, storage, kind=ImageKind.CROP, content=JPEG, content_type="image/jpeg",
                                  source_image_id=uuid.uuid4(), crop_bbox=CropBox(x=0, y=0, width=4, height=4),
                                  path_prefix=PREFIX)
    assert len(uploaded) == 1 and not _exists(storage, uploaded[0])
    assert db.scalar(select(ImageAsset).where(ImageAsset.storage_path == uploaded[0])) is None


def test_upload_failure_leaves_no_row(db):
    s = get_settings()
    broken = SupabaseStorage(base_url=s.supabase_url, service_key=s.supabase_service_role_key.strip(),
                             bucket="zebra_images_does_not_exist", max_upload_bytes=s.storage_max_upload_bytes)
    before = db.scalar(select(ImageAsset.id).where(ImageAsset.uploaded_by == "phase25-orphan-check"))
    with pytest.raises(StorageError):
        image_storage.store_image(db, broken, kind=ImageKind.QUERY, content=JPEG, content_type="image/jpeg",
                                  path_prefix=PREFIX, uploaded_by="phase25-orphan-check")
    assert before is None
    assert db.scalar(select(ImageAsset.id).where(ImageAsset.uploaded_by == "phase25-orphan-check")) is None
