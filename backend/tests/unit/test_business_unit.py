"""Phase 3.2 pure logic: image inspection, error subclasses, batch signing request
shape, PATCH null rules, error mapping. No network, no database."""
import io
import json
import uuid

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from app.integrations.supabase_storage import (
    ImageTooLargeError,
    ImageValidationError,
    SupabaseStorage,
    UnsupportedImageTypeError,
    validate_image,
)
from app.schemas import GalleryEntryUpdate, SightingUpdate, ZebraUpdate
from app.services.images import inspect_image
from tests.conftest import image_bytes


def test_inspect_image_reads_dimensions():
    assert inspect_image(image_bytes("PNG", size=(31, 17))) == (31, 17)
    assert inspect_image(image_bytes("WEBP", size=(8, 9))) == (8, 9)


def test_inspect_image_rejects_corrupt_and_truncated():
    with pytest.raises(ImageValidationError):
        inspect_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    with pytest.raises(ImageValidationError):
        inspect_image(image_bytes("PNG", size=(64, 64))[:40])


def test_inspect_image_rejects_decompression_bomb(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(ImageValidationError, match="too large"):
        inspect_image(image_bytes("PNG", size=(20, 20)))


def test_validate_image_error_classes():
    jpeg = image_bytes()
    with pytest.raises(ImageTooLargeError):
        validate_image(jpeg, "image/jpeg", max_bytes=10)
    with pytest.raises(UnsupportedImageTypeError):
        validate_image(jpeg, "image/gif", max_bytes=10**6)
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="GIF")
    with pytest.raises(UnsupportedImageTypeError):
        validate_image(buf.getvalue(), "image/png", max_bytes=10**6)
    with pytest.raises(ImageValidationError) as exc:  # wrong-but-allowed type: plain 422 class
        validate_image(image_bytes("PNG"), "image/jpeg", max_bytes=10**6)
    assert type(exc.value) is ImageValidationError


def test_signed_urls_batch_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=[
                {"path": "a.jpg", "signedURL": "/object/sign/zebra_images/a.jpg?token=x", "error": None},
                {"path": "gone.jpg", "signedURL": None, "error": "Either the object does not exist or you do not have access to it"},
            ],
        )

    st = SupabaseStorage(base_url="https://e.supabase.co", service_key="k", bucket="zebra_images", max_upload_bytes=1,
                         client=httpx.Client(transport=httpx.MockTransport(handler)))
    out = st.signed_urls(["a.jpg", "gone.jpg"], 45)
    assert seen == {"path": "/storage/v1/object/sign/zebra_images", "body": {"expiresIn": 45, "paths": ["a.jpg", "gone.jpg"]}}
    assert out["a.jpg"].url.endswith("/object/sign/zebra_images/a.jpg?token=x") and out["a.jpg"].expires_in == 45
    assert out["gone.jpg"] is None
    assert st.signed_urls([], 45) == {}
    with pytest.raises(ValueError):
        st.signed_urls(["a.jpg"], 0)


@pytest.mark.parametrize(
    "model,body",
    [
        (ZebraUpdate, {"status": None}),
        (ZebraUpdate, {"attributes": None}),
        (GalleryEntryUpdate, {"is_active": None}),
        (SightingUpdate, {"observed_at": None}),
        (SightingUpdate, {"metadata": None}),
        (SightingUpdate, {"latitude": 1.0}),
        (SightingUpdate, {"latitude": 1.0, "longitude": None}),
    ],
)
def test_patch_rejects(model, body):
    with pytest.raises(ValidationError):
        model.model_validate(body)


def test_patch_accepts_omission_and_clearing():
    assert ZebraUpdate.model_validate({}).model_fields_set == set()
    assert SightingUpdate.model_validate({"zebra_id": None}).zebra_id is None
    cleared = SightingUpdate.model_validate({"latitude": None, "longitude": None})
    assert cleared.model_fields_set == {"latitude", "longitude"}
    assert SightingUpdate.model_validate({"zebra_id": str(uuid.uuid4()), "latitude": 0, "longitude": 0})


def test_new_error_mappings():
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.core.errors import ConflictError, InvalidReferenceError
    from app.main import create_app

    app = create_app(Settings(_env_file=None, cors_origins="http://localhost:5173"))
    cases = {
        "/big": (ImageTooLargeError("file exceeds 10 bytes"), 413, "image_too_large"),
        "/type": (UnsupportedImageTypeError("unsupported content type image/gif"), 415, "unsupported_image_type"),
        "/dup": (ConflictError("dup", code="duplicate_image"), 409, "duplicate_image"),
        "/ref": (InvalidReferenceError("missing", details={"field": "zebra_id"}), 422, "invalid_reference"),
    }
    for path, (exc, *_ ) in cases.items():
        def raiser(exc=exc):
            raise exc
        app.add_api_route(path, raiser, methods=["GET"])

    def bad_model():
        GalleryEntryUpdate.model_validate({"side": "top"})

    app.add_api_route("/model", bad_model, methods=["GET"])
    client = TestClient(app, raise_server_exceptions=False)
    for path, (_, status, code) in cases.items():
        resp = client.get(path)
        assert (resp.status_code, resp.json()["error"]["code"]) == (status, code)
    resp = client.get("/model")
    assert resp.status_code == 422 and resp.json()["error"]["details"][0]["loc"] == ["side"]


def test_openapi_documents_business_endpoints():
    from fastapi.testclient import TestClient

    from app.main import app

    spec = TestClient(app).get("/openapi.json").json()
    paths = spec["paths"]
    expected = {
        "/api/v1/zebras": {"get", "post"},
        "/api/v1/zebras/{zebra_id}": {"get", "patch", "delete"},
        "/api/v1/images": {"get", "post"},
        "/api/v1/images/{image_id}": {"get", "delete"},
        "/api/v1/images/{image_id}/url": {"get"},
        "/api/v1/zebras/{zebra_id}/gallery": {"get", "post"},
        "/api/v1/gallery/{gallery_entry_id}": {"delete"},
        "/api/v1/sightings": {"get", "post"},
        "/api/v1/sightings/{sighting_id}": {"get", "patch", "delete"},
        "/api/v1/identifications": {"get", "post"},
        "/api/v1/identifications/capabilities": {"get"},
        "/api/v1/identifications/{run_id}": {"get"},
        "/api/v1/identifications/{run_id}/candidates": {"get"},
        "/api/v1/identifications/{run_id}/verifications": {"get", "post"},
        "/api/v1/analyses/combined": {"post"},
    }
    for path, methods in expected.items():
        assert set(paths[path]) == methods, path
    upload_op = paths["/api/v1/images"]["post"]
    assert "multipart/form-data" in upload_op["requestBody"]["content"]
    assert {"409", "413", "415", "422"} <= set(upload_op["responses"])
    assert upload_op["responses"]["413"]["content"]["application/json"]["schema"]["$ref"].endswith("ErrorEnvelope")
    assert "storage_path" not in spec["components"]["schemas"]["ImageAssetResponse"]["properties"]
