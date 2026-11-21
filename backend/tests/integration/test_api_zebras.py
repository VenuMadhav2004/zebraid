"""Zebra CRUD API against the real database (rolled back per test)."""
import uuid
from datetime import datetime, timezone

from app.models import ImageKind
from tests.conftest import upload

Z = "/api/v1/zebras"


def _code(prefix="API") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def test_create_and_get(api):
    resp = api.post(Z, json={"code": _code(), "name": "Stripes", "species": "Equus quagga", "attributes": {"ear": "notch"}})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "active" and body["attributes"] == {"ear": "notch"}
    got = api.get(f"{Z}/{body['id']}")
    assert got.status_code == 200 and got.json() == body


def test_create_minimal_has_no_invented_attributes(api):
    body = api.post(Z, json={"code": _code()}).json()
    assert body["name"] is None and body["species"] is None and body["sex"] is None and body["attributes"] == {}


def test_duplicate_code_conflict(api):
    code = _code()
    first = api.post(Z, json={"code": code}).json()
    resp = api.post(Z, json={"code": code})
    assert resp.status_code == 409
    err = resp.json()["error"]
    assert err["code"] == "zebra_code_exists" and err["details"]["zebra_id"] == first["id"]


def test_create_validation(api):
    for bad in ({"code": "has space"}, {"code": ""}, {}, {"code": _code(), "status": "flying"}, {"code": "x" * 41}):
        resp = api.post(Z, json=bad)
        assert resp.status_code == 422, bad
        assert resp.json()["error"]["code"] == "validation_error"


def test_get_missing_and_bad_id(api):
    assert api.get(f"{Z}/{uuid.uuid4()}").json()["error"]["code"] == "not_found"
    assert api.get(f"{Z}/not-a-uuid").status_code == 422


def test_list_pagination_search_filters(api):
    prefix = f"PG{uuid.uuid4().hex[:6]}"
    for i in range(5):
        api.post(Z, json={"code": f"{prefix}-{i}", "species": "Equus grevyi" if i % 2 else "Equus quagga",
                          "status": "inactive" if i == 4 else "active"})
    page1 = api.get(Z, params={"search": prefix, "limit": 2, "offset": 0}).json()
    page3 = api.get(Z, params={"search": prefix, "limit": 2, "offset": 4}).json()
    assert page1["total"] == 5 and page1["limit"] == 2 and [z["code"] for z in page1["items"]] == [f"{prefix}-0", f"{prefix}-1"]
    assert [z["code"] for z in page3["items"]] == [f"{prefix}-4"]
    assert api.get(Z, params={"search": prefix, "status": "inactive"}).json()["total"] == 1
    assert api.get(Z, params={"search": prefix, "species": "EQUUS GREVYI"}).json()["total"] == 2


def test_list_search_wildcards_are_literal(api):
    api.post(Z, json={"code": _code()})
    assert api.get(Z, params={"search": "%"}).json()["total"] == 0


def test_list_limit_bounds(api):
    assert api.get(Z, params={"limit": 0}).status_code == 422
    assert api.get(Z, params={"limit": 101}).status_code == 422
    assert api.get(Z, params={"offset": -1}).status_code == 422


def test_patch(api):
    z = api.post(Z, json={"code": _code(), "name": "Old"}).json()
    resp = api.patch(f"{Z}/{z['id']}", json={"name": "New", "status": "deceased"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New" and body["status"] == "deceased" and body["code"] == z["code"]


def test_patch_rejects_null_required_and_ignores_code(api):
    z = api.post(Z, json={"code": _code()}).json()
    assert api.patch(f"{Z}/{z['id']}", json={"status": None}).status_code == 422
    assert api.patch(f"{Z}/{z['id']}", json={"attributes": None}).status_code == 422
    assert api.patch(f"{Z}/{z['id']}", json={"code": "CHANGED"}).json()["code"] == z["code"]
    assert api.patch(f"{Z}/{uuid.uuid4()}", json={"name": "x"}).status_code == 404


def test_delete_removes_gallery_links_keeps_images(api):
    z = api.post(Z, json={"code": _code()}).json()
    img = upload(api, kind=ImageKind.REFERENCE.value).json()
    api.post(f"{Z}/{z['id']}/gallery", json={"image_asset_id": img["id"]})
    assert api.delete(f"{Z}/{z['id']}").status_code == 204
    assert api.get(f"{Z}/{z['id']}").status_code == 404
    assert api.get(f"/api/v1/images/{img['id']}").status_code == 200


def test_delete_blocked_by_sighting(api):
    z = api.post(Z, json={"code": _code()}).json()
    api.post("/api/v1/sightings", json={"observed_at": datetime.now(timezone.utc).isoformat(), "zebra_id": z["id"]})
    resp = api.delete(f"{Z}/{z['id']}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "zebra_in_use" and resp.json()["error"]["details"] == {"sightings": 1}
    assert api.get(f"{Z}/{z['id']}").status_code == 200


def test_delete_missing(api):
    assert api.delete(f"{Z}/{uuid.uuid4()}").status_code == 404


def test_list_sort_newest_first(api):
    prefix = f"SR{uuid.uuid4().hex[:6]}"
    for suffix in ("b", "a", "c"):  # created in this order
        api.post(Z, json={"code": f"{prefix}-{suffix}"})
    by_code = [z["code"] for z in api.get(Z, params={"search": prefix}).json()["items"]]
    newest = [z["code"] for z in api.get(Z, params={"search": prefix, "sort": "-created_at"}).json()["items"]]
    assert by_code == [f"{prefix}-a", f"{prefix}-b", f"{prefix}-c"]
    assert newest == [f"{prefix}-c", f"{prefix}-a", f"{prefix}-b"]
    assert api.get(Z, params={"sort": "name"}).status_code == 422
