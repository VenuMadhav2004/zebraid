"""End-to-end API checks against the REAL private bucket (marked `storage`).

DB rows are rolled back by the `db` fixture; every object uploaded here is
tracked and removed in teardown, and teardown asserts none are left.
"""
import uuid

import httpx
import pytest

from app.api import deps
from app.integrations.supabase_storage import StorageNotFoundError, SupabaseStorage
from tests.conftest import image_bytes, unique_color, upload

pytestmark = pytest.mark.storage


@pytest.fixture
def live_api(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database.session import get_db
    from app.main import create_app

    storage = SupabaseStorage.from_settings()
    uploaded: list[str] = []
    real_upload = storage.upload

    def tracking_upload(path, content, content_type):
        uploaded.append(path)
        return real_upload(path, content, content_type)

    monkeypatch.setattr(storage, "upload", tracking_upload)
    monkeypatch.setattr(deps, "_storage", storage)
    app = create_app()

    def _test_db():
        yield db

    app.dependency_overrides[get_db] = _test_db
    yield TestClient(app, raise_server_exceptions=False), storage, uploaded
    if uploaded:
        storage.delete(uploaded)
    left = []
    for p in uploaded:
        try:
            storage.download(p)
            left.append(p)
        except StorageNotFoundError:
            pass
    assert left == [], f"cleanup failed: {left}"


def test_upload_sign_fetch_delete(live_api):
    api, storage, uploaded = live_api
    content = image_bytes("PNG", size=(32, 32), color=unique_color())
    img = upload(api, content, content_type="image/png").json()
    assert len(uploaded) == 1

    signed = api.get(f"/api/v1/images/{img['id']}/url", params={"expires_in": 30}).json()
    fetched = httpx.get(signed["url"], timeout=30)
    assert fetched.status_code == 200 and fetched.content == content

    assert api.delete(f"/api/v1/images/{img['id']}").status_code == 204
    with pytest.raises(StorageNotFoundError):
        storage.download(uploaded[0])


def test_gallery_batch_signed_urls_live(live_api):
    api, _, uploaded = live_api
    zebra = api.post("/api/v1/zebras", json={"code": f"LIVE-{uuid.uuid4().hex[:8]}"}).json()
    contents = [image_bytes(color=unique_color()) for _ in range(2)]
    for c in contents:
        img = upload(api, c, kind="reference").json()
        api.post(f"/api/v1/zebras/{zebra['id']}/gallery", json={"image_asset_id": img["id"]})
    page = api.get(f"/api/v1/zebras/{zebra['id']}/gallery", params={"include_urls": True}).json()
    assert page["total"] == 2
    got = [httpx.get(i["image_url"]["url"], timeout=30).content for i in page["items"]]
    assert sorted(got) == sorted(contents)


def test_no_public_or_unsigned_access(live_api):
    api, storage, uploaded = live_api
    upload(api, image_bytes(color=unique_color()))
    base = storage._api
    assert httpx.get(f"{base}/object/public/{storage.bucket}/{uploaded[0]}", timeout=30).status_code >= 400
    assert httpx.get(f"{base}/object/{storage.bucket}/{uploaded[0]}", timeout=30).status_code >= 400
