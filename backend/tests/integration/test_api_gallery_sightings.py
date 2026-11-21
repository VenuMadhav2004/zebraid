"""Gallery and sighting APIs against the real database (rolled back per test)."""
import uuid
from datetime import datetime, timedelta, timezone

from app.models import ImageAsset
from app.repositories import identifications as run_repo
from app.schemas import IdentificationRunCreate
from tests.conftest import image_bytes, unique_color, upload

S = "/api/v1/sightings"
IMAGES = "/api/v1/images"


def _zebra(api) -> dict:
    return api.post("/api/v1/zebras", json={"code": f"GS-{uuid.uuid4().hex[:8]}"}).json()


def _image(api, kind="reference") -> dict:
    return upload(api, image_bytes(color=unique_color()), kind=kind).json()


def _gallery(zebra_id) -> str:
    return f"/api/v1/zebras/{zebra_id}/gallery"


# -- gallery ----------------------------------------------------------------------
def test_gallery_add_and_list_with_image_metadata(api):
    z = _zebra(api)
    img = _image(api)
    resp = api.post(_gallery(z["id"]), json={"image_asset_id": img["id"], "side": "left", "registered_by": "curator"})
    assert resp.status_code == 201, resp.text
    entry = resp.json()
    assert entry["zebra_id"] == z["id"] and entry["side"] == "left" and entry["is_active"] is True
    assert entry["image"]["id"] == img["id"] and entry["image"]["width"] == 64 and entry["image_url"] is None
    assert "storage_path" not in entry["image"]
    page = api.get(_gallery(z["id"])).json()
    assert page["total"] == 1 and page["items"][0]["id"] == entry["id"]


def test_gallery_signed_urls_on_request(api):
    z = _zebra(api)
    for _ in range(2):
        api.post(_gallery(z["id"]), json={"image_asset_id": _image(api)["id"]})
    page = api.get(_gallery(z["id"]), params={"include_urls": True, "expires_in": 90}).json()
    assert [i["image_url"]["expires_in"] for i in page["items"]] == [90, 90]


def test_gallery_pagination_and_inactive(api, db):
    from app.models import GalleryEntry

    z = _zebra(api)
    ids = [api.post(_gallery(z["id"]), json={"image_asset_id": _image(api)["id"]}).json()["id"] for _ in range(3)]
    db.get(GalleryEntry, uuid.UUID(ids[0])).is_active = False
    db.flush()
    assert api.get(_gallery(z["id"])).json()["total"] == 2
    assert api.get(_gallery(z["id"]), params={"include_inactive": True}).json()["total"] == 3
    page = api.get(_gallery(z["id"]), params={"include_inactive": True, "limit": 2, "offset": 2}).json()
    assert [i["id"] for i in page["items"]] == [ids[2]]


def test_gallery_rules(api):
    z = _zebra(api)
    query_img = _image(api, kind="query")
    wrong_kind = api.post(_gallery(z["id"]), json={"image_asset_id": query_img["id"]})
    assert wrong_kind.status_code == 422 and wrong_kind.json()["error"]["code"] == "domain_rule_violation"
    missing_img = api.post(_gallery(z["id"]), json={"image_asset_id": str(uuid.uuid4())})
    assert missing_img.status_code == 422 and missing_img.json()["error"]["code"] == "invalid_reference"
    assert api.post(_gallery(uuid.uuid4()), json={"image_asset_id": _image(api)["id"]}).status_code == 404
    assert api.get(_gallery(uuid.uuid4())).status_code == 404


def test_gallery_duplicate_association(api):
    z1, z2 = _zebra(api), _zebra(api)
    img = _image(api)
    first = api.post(_gallery(z1["id"]), json={"image_asset_id": img["id"]}).json()
    for zid in (z1["id"], z2["id"]):
        resp = api.post(_gallery(zid), json={"image_asset_id": img["id"]})
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "image_already_in_gallery"
        assert resp.json()["error"]["details"]["gallery_entry_id"] == first["id"]


def test_gallery_remove_keeps_image(api, fake_storage):
    z = _zebra(api)
    img = _image(api)
    entry = api.post(_gallery(z["id"]), json={"image_asset_id": img["id"]}).json()
    assert api.delete(f"/api/v1/gallery/{entry['id']}").status_code == 204
    assert api.get(_gallery(z["id"])).json()["total"] == 0
    assert api.get(f"/api/v1/images/{img['id']}").status_code == 200 and len(fake_storage.objects) == 1
    assert api.delete(f"/api/v1/gallery/{entry['id']}").status_code == 404


# -- sightings ----------------------------------------------------------------------
def _at(days: int = 0) -> str:
    return (datetime(2026, 6, 1, 12, tzinfo=timezone.utc) + timedelta(days=days)).isoformat()


def test_sighting_unidentified_and_identified(api):
    unknown = api.post(S, json={"observed_at": _at(), "location_name": "Waterhole A", "latitude": -1.5, "longitude": 35.1})
    assert unknown.status_code == 201, unknown.text
    assert unknown.json()["zebra_id"] is None
    z = _zebra(api)
    known = api.post(S, json={"observed_at": _at(), "zebra_id": z["id"]}).json()
    assert known["zebra_id"] == z["id"]
    assert api.get(f"{S}/{known['id']}").json() == known


def test_sighting_validation_and_references(api):
    assert api.post(S, json={"observed_at": _at(), "latitude": 1.0}).status_code == 422
    assert api.post(S, json={"observed_at": _at(), "latitude": 91, "longitude": 0}).status_code == 422
    assert api.post(S, json={}).status_code == 422
    for field in ("zebra_id", "image_asset_id", "identification_run_id"):
        resp = api.post(S, json={"observed_at": _at(), field: str(uuid.uuid4())})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_reference" and resp.json()["error"]["details"] == {"field": field}


def test_sighting_run_must_match_image(api, db):
    photo, other = _image(api, kind="query"), _image(api, kind="query")
    run = run_repo.create_run(db, IdentificationRunCreate(query_image_id=uuid.UUID(photo["id"]), model_name="test"))
    ok = api.post(S, json={"observed_at": _at(), "image_asset_id": photo["id"], "identification_run_id": str(run.id)})
    assert ok.status_code == 201
    bad = api.post(S, json={"observed_at": _at(), "image_asset_id": other["id"], "identification_run_id": str(run.id)})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "inconsistent_reference"


def test_sighting_list_filters_and_pagination(api):
    z = _zebra(api)
    place = f"Plain-{uuid.uuid4().hex[:6]}"
    for day in range(4):
        api.post(S, json={"observed_at": _at(day), "zebra_id": z["id"] if day < 3 else None, "location_name": place,
                          "latitude": -2.0 + day, "longitude": 34.0})
    by_place = api.get(S, params={"location_name": place.lower()}).json()
    assert by_place["total"] == 4 and by_place["items"][0]["observed_at"].startswith("2026-06-04")  # newest first
    assert api.get(S, params={"zebra_id": z["id"]}).json()["total"] == 3
    assert api.get(S, params={"location_name": place, "unidentified_only": True}).json()["total"] == 1
    window = api.get(S, params={"zebra_id": z["id"], "since": _at(1), "until": _at(2)}).json()
    assert window["total"] == 1 and window["items"][0]["observed_at"].startswith("2026-06-02")
    box = api.get(S, params={"location_name": place, "min_lat": -1.5, "max_lat": 0.5}).json()
    assert box["total"] == 2
    page = api.get(S, params={"zebra_id": z["id"], "limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1


def test_sighting_patch(api):
    z = _zebra(api)
    s = api.post(S, json={"observed_at": _at(), "latitude": 1.0, "longitude": 2.0}).json()
    url = f"{S}/{s['id']}"
    assert api.patch(url, json={"zebra_id": z["id"], "notes": "ear notch"}).json()["zebra_id"] == z["id"]
    assert api.patch(url, json={"zebra_id": None}).json()["zebra_id"] is None
    moved = api.patch(url, json={"latitude": 3.0, "longitude": 4.0}).json()
    assert (moved["latitude"], moved["longitude"]) == (3.0, 4.0)
    cleared = api.patch(url, json={"latitude": None, "longitude": None}).json()
    assert cleared["latitude"] is None and cleared["longitude"] is None
    assert api.patch(url, json={"latitude": 5.0}).status_code == 422
    assert api.patch(url, json={"observed_at": None}).status_code == 422
    bad_zebra = api.patch(url, json={"zebra_id": str(uuid.uuid4())})
    assert bad_zebra.status_code == 422 and bad_zebra.json()["error"]["code"] == "invalid_reference"
    assert api.patch(f"{S}/{uuid.uuid4()}", json={"notes": "x"}).status_code == 404


def test_sighting_delete_keeps_image(api, db):
    img = _image(api, kind="query")
    s = api.post(S, json={"observed_at": _at(), "image_asset_id": img["id"]}).json()
    assert api.delete(f"{IMAGES}/{img['id']}").status_code == 409  # image in use by the sighting
    assert api.delete(f"{S}/{s['id']}").status_code == 204
    assert api.get(f"{S}/{s['id']}").status_code == 404
    assert db.get(ImageAsset, uuid.UUID(img["id"])) is not None
    assert api.delete(f"{S}/{s['id']}").status_code == 404

