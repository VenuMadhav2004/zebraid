"""Image API: upload validation, metadata persistence, signed URLs, deletion and
storage/database failure handling. Real database (rolled back), in-memory storage fake."""
import hashlib
import json
import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app.models import ImageAsset
from tests.conftest import image_bytes, unique_color, upload

IMAGES = "/api/v1/images"


@pytest.mark.parametrize("fmt,ctype", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
def test_upload_formats_persist_metadata(api, db, fake_storage, fmt, ctype):
    content = image_bytes(fmt, size=(80, 60), color=unique_color())
    resp = upload(api, content, content_type=ctype, uploaded_by="tester", captured_at="2026-01-02T03:04:05Z",
                  metadata=json.dumps({"camera": "trap-7"}))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["content_type"] == ctype and body["size_bytes"] == len(content)
    assert (body["width"], body["height"]) == (80, 60)
    assert body["sha256"] == hashlib.sha256(content).hexdigest()
    assert body["metadata"] == {"camera": "trap-7"} and body["uploaded_by"] == "tester"
    assert "storage_path" not in body and "storage_bucket" not in body
    row = db.get(ImageAsset, uuid.UUID(body["id"]))
    assert row is not None and fake_storage.objects[row.storage_path] == content  # bytes in Storage only


def test_upload_too_large(api, fake_storage):
    fake_storage.max_upload_bytes = 1000
    resp = upload(api, image_bytes("PNG", size=(400, 400), color=unique_color()), content_type="image/png")
    assert resp.status_code == 413 and resp.json()["error"]["code"] == "image_too_large"
    assert fake_storage.objects == {}


def test_upload_unsupported_types(api, fake_storage):
    gif = upload(api, image_bytes("GIF"), content_type="image/gif")
    assert gif.status_code == 415 and gif.json()["error"]["code"] == "unsupported_image_type"
    gif_as_jpeg = upload(api, image_bytes("GIF"), content_type="image/jpeg")
    assert gif_as_jpeg.status_code == 415
    assert fake_storage.objects == {}


def test_upload_spoofed_and_corrupt(api, fake_storage):
    png_as_jpeg = upload(api, image_bytes("PNG"), content_type="image/jpeg")
    assert png_as_jpeg.status_code == 422 and png_as_jpeg.json()["error"]["code"] == "invalid_image"
    corrupt = upload(api, b"\xff\xd8\xff\xe0" + b"\x00" * 200, content_type="image/jpeg")
    assert corrupt.status_code == 422 and corrupt.json()["error"]["code"] == "invalid_image"
    empty = upload(api, b"", content_type="image/jpeg")
    assert empty.status_code == 422
    assert fake_storage.objects == {}


def test_upload_form_validation(api):
    assert upload(api, kind="banana").status_code == 422
    assert api.post(IMAGES, data={"kind": "query"}).status_code == 422  # no file
    bad_meta = upload(api, image_bytes(color=unique_color()), metadata="[1,2]")
    assert bad_meta.status_code == 422 and bad_meta.json()["error"]["details"] == {"field": "metadata"}


def test_duplicate_upload_same_kind_conflicts(api):
    content = image_bytes(color=unique_color())
    first = upload(api, content).json()
    dup = upload(api, content)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate_image"
    assert dup.json()["error"]["details"]["existing_image_id"] == first["id"]
    assert upload(api, content, kind="reference").status_code == 201  # same bytes, other kind


def test_crop_lineage(api):
    source = upload(api, image_bytes(size=(200, 100), color=unique_color())).json()
    crop_bytes = image_bytes(size=(50, 50), color=unique_color())
    missing = upload(api, crop_bytes, kind="crop")
    assert missing.status_code == 422
    ok = upload(api, crop_bytes, kind="crop", source_image_id=source["id"],
                crop_bbox=json.dumps({"x": 10, "y": 10, "width": 50, "height": 50}))
    assert ok.status_code == 201, ok.text
    assert ok.json()["source_image_id"] == source["id"] and ok.json()["crop_bbox"]["width"] == 50
    outside = upload(api, image_bytes(size=(50, 50), color=unique_color()), kind="crop", source_image_id=source["id"],
                     crop_bbox=json.dumps({"x": 190, "y": 10, "width": 50, "height": 50}))
    assert outside.status_code == 422 and outside.json()["error"]["code"] == "domain_rule_violation"
    bad_box = upload(api, image_bytes(size=(50, 50), color=unique_color()), kind="crop", source_image_id=source["id"],
                     crop_bbox=json.dumps({"x": -1, "y": 0, "width": 5, "height": 5}))
    assert bad_box.status_code == 422 and bad_box.json()["error"]["code"] == "validation_error"
    no_source = upload(api, image_bytes(size=(50, 50), color=unique_color()), kind="crop", source_image_id=str(uuid.uuid4()),
                       crop_bbox=json.dumps({"x": 0, "y": 0, "width": 5, "height": 5}))
    assert no_source.status_code == 422 and no_source.json()["error"]["code"] == "invalid_reference"
    assert upload(api, image_bytes(color=unique_color()), kind="query", source_image_id=source["id"],
                  crop_bbox=json.dumps({"x": 0, "y": 0, "width": 5, "height": 5})).status_code == 422


def test_list_get_and_filters(api):
    content = image_bytes(color=unique_color())
    created = upload(api, content, kind="reference").json()
    listed = api.get(IMAGES, params={"sha256": created["sha256"]}).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == created["id"]
    assert api.get(IMAGES, params={"sha256": created["sha256"], "kind": "query"}).json()["total"] == 0
    assert api.get(IMAGES, params={"sha256": "nothex"}).status_code == 422
    assert api.get(IMAGES, params={"limit": 1}).json()["limit"] == 1
    assert api.get(f"{IMAGES}/{created['id']}").json() == created
    assert api.get(f"{IMAGES}/{uuid.uuid4()}").status_code == 404


def test_signed_url(api):
    img = upload(api, image_bytes(color=unique_color())).json()
    resp = api.get(f"{IMAGES}/{img['id']}/url", params={"expires_in": 120})
    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in"] == 120 and "token=" in body["url"] and body["expires_at"]
    assert api.get(f"{IMAGES}/{img['id']}/url", params={"expires_in": 0}).status_code == 422
    assert api.get(f"{IMAGES}/{img['id']}/url", params={"expires_in": 3601}).status_code == 422
    assert api.get(f"{IMAGES}/{uuid.uuid4()}/url").status_code == 404


def test_signed_url_missing_object_and_storage_failure(api, db, fake_storage):
    img = upload(api, image_bytes(color=unique_color())).json()
    fake_storage.objects.clear()
    resp = api.get(f"{IMAGES}/{img['id']}/url")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "storage_object_not_found"
    fake_storage.fail_sign = True
    failed = api.get(f"{IMAGES}/{img['id']}/url")
    assert failed.status_code == 502 and failed.json()["error"]["code"] == "storage_error"
    assert "fake.supabase.co" not in failed.text


def test_delete_removes_row_and_object(api, db, fake_storage):
    img = upload(api, image_bytes(color=unique_color())).json()
    path = db.get(ImageAsset, uuid.UUID(img["id"])).storage_path
    assert api.delete(f"{IMAGES}/{img['id']}").status_code == 204
    assert api.get(f"{IMAGES}/{img['id']}").status_code == 404
    assert path not in fake_storage.objects
    assert api.delete(f"{IMAGES}/{img['id']}").status_code == 404


def test_delete_refused_while_in_use(api, fake_storage):
    z = api.post("/api/v1/zebras", json={"code": f"IMG-{uuid.uuid4().hex[:8]}"}).json()
    ref = upload(api, image_bytes(color=unique_color()), kind="reference").json()
    api.post(f"/api/v1/zebras/{z['id']}/gallery", json={"image_asset_id": ref["id"]})
    resp = api.delete(f"{IMAGES}/{ref['id']}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "image_in_use" and resp.json()["error"]["details"] == {"gallery_entries": 1}
    assert len(fake_storage.objects) == 1


def test_delete_with_storage_failure_keeps_db_consistent(api, fake_storage):
    img = upload(api, image_bytes(color=unique_color())).json()
    fake_storage.fail_delete = True
    assert api.delete(f"{IMAGES}/{img['id']}").status_code == 204  # row gone; orphan object logged
    assert api.get(f"{IMAGES}/{img['id']}").status_code == 404


def test_storage_upload_failure_writes_no_row(api, fake_storage):
    content = image_bytes(color=unique_color())
    fake_storage.fail_upload = True
    resp = upload(api, content)
    assert resp.status_code == 502 and resp.json()["error"]["code"] == "storage_error"
    assert api.get(IMAGES, params={"sha256": hashlib.sha256(content).hexdigest()}).json()["total"] == 0


def test_commit_failure_discards_uploaded_object(api, db, fake_storage, monkeypatch):
    content = image_bytes(color=unique_color())
    real_commit = db.commit

    def failing_commit():
        monkeypatch.setattr(db, "commit", real_commit)
        raise OperationalError("COMMIT", {}, Exception("server closed the connection"))

    monkeypatch.setattr(db, "commit", failing_commit)
    resp = upload(api, content)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "database_unavailable"
    assert "server closed" not in resp.text
    assert fake_storage.objects == {}
    assert api.get(IMAGES, params={"sha256": hashlib.sha256(content).hexdigest()}).json()["total"] == 0


def test_storage_not_configured(api, monkeypatch):
    from app.api import deps
    from app.core.config import Settings

    monkeypatch.setattr(deps, "_storage", None)
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(_env_file=None, supabase_url="", supabase_service_role_key=""))
    resp = upload(api, image_bytes(color=unique_color()))
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "storage_not_configured"


def test_exif_rotated_image_records_display_dimensions_and_accepts_browser_crop_bbox(api, db, fake_storage):
    import io

    from PIL import ExifTags, Image

    # Raw 120x60 JPEG with EXIF orientation 6 (90 deg CW) -> browser displays 60x120.
    im = Image.new("RGB", (120, 60), unique_color())
    exif = Image.Exif()
    exif[int(ExifTags.Base.Orientation)] = 6
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif.tobytes())
    raw = buf.getvalue()

    src = upload(api, raw, content_type="image/jpeg")
    assert src.status_code == 201, src.text
    src_body = src.json()
    assert (src_body["width"], src_body["height"]) == (60, 120)
    # Original bytes are preserved untouched in storage.
    row = db.get(ImageAsset, uuid.UUID(src_body["id"]))
    assert fake_storage.objects[row.storage_path] == raw

    # A crop in browser-oriented coordinates (y + height = 110 <= 120) succeeds.
    crop_ok = upload(
        api,
        image_bytes(size=(40, 50), color=unique_color()),
        kind="crop",
        source_image_id=src_body["id"],
        crop_bbox=json.dumps({"x": 10, "y": 60, "width": 40, "height": 50}),
    )
    assert crop_ok.status_code == 201, crop_ok.text

    # A crop using unrotated raw coordinates (x + width = 100 > 60) is rejected.
    crop_oob = upload(
        api,
        image_bytes(size=(40, 40), color=unique_color()),
        kind="crop",
        source_image_id=src_body["id"],
        crop_bbox=json.dumps({"x": 60, "y": 10, "width": 40, "height": 40}),
    )
    assert crop_oob.status_code == 422 and crop_oob.json()["error"]["code"] == "domain_rule_violation"
