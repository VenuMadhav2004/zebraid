"""Storage client + service logic with the HTTP layer and DB mocked (no network)."""
import json
import re
from unittest.mock import MagicMock

import httpx
import pytest

from app.integrations.supabase_storage import (
    ImageValidationError,
    StorageConflictError,
    StorageError,
    StorageNotFoundError,
    SupabaseStorage,
    generate_storage_path,
    sniff_image_type,
    validate_image,
)
from app.models import ImageKind
from app.services import image_storage

FAKE_KEY = "fake-service-key-for-unit-tests"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32


def make_storage(handler, **kw) -> SupabaseStorage:
    return SupabaseStorage(
        base_url="https://example.supabase.co",
        service_key=FAKE_KEY,
        bucket="zebra_images",
        max_upload_bytes=kw.pop("max_upload_bytes", 1024),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        **kw,
    )


@pytest.mark.parametrize("content,expected", [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp"), (b"GIF89a", None)])
def test_sniff(content, expected):
    assert sniff_image_type(content) == expected


def test_validate_accepts_matching_types():
    assert validate_image(JPEG, "image/jpeg", max_bytes=1024) == "image/jpeg"
    assert validate_image(PNG, "IMAGE/PNG; charset=binary", max_bytes=1024) == "image/png"


@pytest.mark.parametrize(
    "content,ctype,why",
    [
        (b"", "image/jpeg", "empty"),
        (JPEG, "image/gif", "unsupported"),
        (b"hello", "text/plain", "unsupported"),
        (PNG, "image/jpeg", "mismatch"),       # renamed file / spoofed header
        (b"<svg/>", "image/png", "mismatch"),
        (JPEG + b"\x00" * 2000, "image/jpeg", "oversize"),
    ],
)
def test_validate_rejects(content, ctype, why):
    with pytest.raises(ImageValidationError):
        validate_image(content, ctype, max_bytes=1024)


def test_generated_paths_unique_and_safe():
    paths = {generate_storage_path(ImageKind.QUERY, "image/png") for _ in range(200)}
    assert len(paths) == 200
    assert all(re.fullmatch(r"query/\d{4}/\d{2}/[0-9a-f]{32}\.png", p) for p in paths)
    assert generate_storage_path(ImageKind.CROP, "image/webp", prefix="_healthcheck/phase25").startswith(
        "_healthcheck/phase25/crop/"
    )


@pytest.mark.parametrize("prefix", ["../x", "a/../b", "/abs", "a b", "a//b", "a\\b"])
def test_unsafe_prefix_rejected(prefix):
    with pytest.raises(ValueError):
        generate_storage_path(ImageKind.QUERY, "image/jpeg", prefix=prefix)


def test_upload_never_upserts_and_sends_validated_type():
    seen = {}

    def handler(req: httpx.Request):
        seen.update(method=req.method, url=str(req.url), headers=dict(req.headers))
        return httpx.Response(200, json={"Key": "zebra_images/p.jpg"})

    make_storage(handler).upload("q/2026/11/p.jpg", JPEG, "image/jpeg")
    assert seen["method"] == "POST"
    assert seen["url"].endswith("/storage/v1/object/zebra_images/q/2026/11/p.jpg")
    assert seen["headers"]["x-upsert"] == "false"
    assert seen["headers"]["content-type"] == "image/jpeg"


def test_upload_rejects_before_network():
    handler = MagicMock()
    with pytest.raises(ImageValidationError):
        make_storage(handler).upload("p.jpg", b"not an image", "image/jpeg")
    handler.assert_not_called()


@pytest.mark.parametrize(
    "status,body,exc",
    [
        (400, {"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"}, StorageConflictError),
        (409, {"message": "duplicate"}, StorageConflictError),
        (400, {"statusCode": "404", "error": "not_found", "message": "Object not found"}, StorageNotFoundError),
        (403, {"statusCode": "403", "message": "new row violates row-level security policy"}, StorageError),
    ],
)
def test_error_mapping(status, body, exc):
    storage = make_storage(lambda req: httpx.Response(status, json=body))
    with pytest.raises(exc) as info:
        storage.download("p.jpg")
    assert FAKE_KEY not in str(info.value)


def test_network_error_hides_details():
    def handler(req):
        raise httpx.ConnectError(f"boom {req.headers['authorization']}")

    with pytest.raises(StorageError) as info:
        make_storage(handler).download("p.jpg")
    assert FAKE_KEY not in str(info.value)


def test_signed_url_ttl_bounds_and_shape():
    def handler(req):
        assert json.loads(req.content) == {"expiresIn": 120}
        return httpx.Response(200, json={"signedURL": "/object/sign/zebra_images/p.jpg?token=abc"})

    storage = make_storage(handler, max_ttl=600)
    signed = storage.signed_url("p.jpg", expires_in=120)
    assert signed.url == "https://example.supabase.co/storage/v1/object/sign/zebra_images/p.jpg?token=abc"
    assert signed.expires_in == 120 and signed.expires_at is not None
    for bad in (0, -1, 601):
        with pytest.raises(ValueError):
            storage.signed_url("p.jpg", expires_in=bad)


def test_missing_config_refused():
    with pytest.raises(StorageError):
        SupabaseStorage(base_url="", service_key="", bucket="b", max_upload_bytes=1)


def test_store_image_upload_failure_writes_no_row():
    storage = MagicMock(bucket="zebra_images", max_upload_bytes=1024)
    storage.upload.side_effect = StorageError("upload failed", 500)
    db = MagicMock()
    with pytest.raises(StorageError):
        image_storage.store_image(db, storage, kind=ImageKind.QUERY, content=JPEG, content_type="image/jpeg")
    db.begin_nested.assert_not_called()
    db.add.assert_not_called()


def test_store_image_db_failure_deletes_object(monkeypatch):
    storage = MagicMock(bucket="zebra_images", max_upload_bytes=1024)
    db = MagicMock()
    monkeypatch.setattr(image_storage.image_repo, "create_image_asset", MagicMock(side_effect=RuntimeError("db down")))
    with pytest.raises(RuntimeError):
        image_storage.store_image(db, storage, kind=ImageKind.QUERY, content=JPEG, content_type="image/jpeg")
    uploaded_path = storage.upload.call_args.args[0]
    storage.delete.assert_called_once_with([uploaded_path])


def test_store_image_invalid_file_touches_nothing():
    storage, db = MagicMock(bucket="zebra_images", max_upload_bytes=1024), MagicMock()
    with pytest.raises(ImageValidationError):
        image_storage.store_image(db, storage, kind=ImageKind.QUERY, content=b"%PDF-1.7", content_type="image/png")
    storage.upload.assert_not_called()
    db.begin_nested.assert_not_called()
