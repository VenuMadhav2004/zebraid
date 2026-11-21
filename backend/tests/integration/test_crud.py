from datetime import datetime, timedelta, timezone

import pytest

from app.models import ImageKind, ZebraStatus
from app.repositories import images as image_repo
from app.repositories import sightings as sighting_repo
from app.repositories import zebras as zebra_repo
from app.repositories.base import DomainRuleError, NotFoundError
from app.schemas import CropBox, ImageAssetUpdate, SightingCreate, SightingUpdate, ZebraUpdate
from tests.conftest import BUCKET, expect_integrity_error


def test_zebra_crud(db, make_zebra):
    z = make_zebra(name="Stripes", species="Equus quagga")
    assert z.id and z.created_at and z.status == ZebraStatus.ACTIVE
    assert zebra_repo.get_zebra(db, z.id) is z
    assert zebra_repo.get_zebra_by_code(db, z.code).id == z.id

    zebra_repo.update_zebra(db, z.id, ZebraUpdate(notes="scar on left flank"))
    assert z.notes == "scar on left flank" and z.name == "Stripes"  # partial update

    assert z.id in {x.id for x in zebra_repo.list_zebras(db, search="Strip")}
    zebra_repo.delete_zebra(db, z.id)
    with pytest.raises(NotFoundError):
        zebra_repo.get_zebra(db, z.id)


def test_zebra_code_unique(db, make_zebra):
    z = make_zebra()
    with expect_integrity_error(db, "uq_zebras_code"):
        make_zebra(code=z.code)


def test_image_crud_and_kinds(db, make_image):
    q = make_image(ImageKind.QUERY, sha256="a" * 64)
    r = make_image(ImageKind.REFERENCE)
    c = make_image(ImageKind.CROP, source_image_id=q.id, crop_bbox=CropBox(x=0, y=0, width=100, height=100))
    assert {q.kind, r.kind, c.kind} == {ImageKind.QUERY, ImageKind.REFERENCE, ImageKind.CROP}
    assert c.source_image is q and c in q.crops
    assert c.crop_bbox == {"x": 0, "y": 0, "width": 100, "height": 100}
    assert image_repo.get_by_storage_path(db, BUCKET, q.storage_path).id == q.id
    assert [i.id for i in image_repo.find_by_sha256(db, "a" * 64)] == [q.id]
    assert [i.id for i in image_repo.list_crops(db, q.id)] == [c.id]

    image_repo.update_image_asset(db, r.id, ImageAssetUpdate(metadata={"camera": "trap-7"}))
    assert r.metadata_ == {"camera": "trap-7"}

    assert image_repo.delete_image_asset(db, r.id) == r.storage_path


def test_crop_outside_source_rejected(db, make_image):
    q = make_image(ImageKind.QUERY, width=100, height=100)
    with pytest.raises(DomainRuleError):
        make_image(ImageKind.CROP, source_image_id=q.id, crop_bbox=CropBox(x=50, y=50, width=80, height=80))


def test_image_storage_object_unique(db, make_image):
    img = make_image()
    with expect_integrity_error(db, "uq_image_assets_storage_object"):
        make_image(storage_path=img.storage_path)


def test_db_rejects_url_as_storage_path(db):
    """Bypass Pydantic to prove the DB CHECK also guards storage_path."""
    from app.models import ImageAsset

    with expect_integrity_error(db, "ck_image_assets_relative_path"):
        db.add(ImageAsset(kind=ImageKind.QUERY, storage_bucket=BUCKET, storage_path="https://x.supabase.co/a.jpg", content_type="image/jpeg"))


def test_db_rejects_crop_without_source(db):
    from app.models import ImageAsset

    with expect_integrity_error(db, "ck_image_assets_crop_has_source"):
        db.add(ImageAsset(kind=ImageKind.CROP, storage_bucket=BUCKET, storage_path="test/orphan-crop.jpg", content_type="image/jpeg"))


def test_sighting_crud(db, make_zebra, make_image):
    z = make_zebra()
    now = datetime.now(timezone.utc)
    s = sighting_repo.create_sighting(
        db,
        SightingCreate(
            observed_at=now, zebra_id=z.id, image_asset_id=make_image().id,
            latitude=-1.5, longitude=35.1, location_name="Mara North", observer="team",
        ),
    )
    unidentified = sighting_repo.create_sighting(db, SightingCreate(observed_at=now - timedelta(days=1)))
    assert s.zebra is z and s in z.sightings
    assert [x.id for x in sighting_repo.list_sightings(db, zebra_id=z.id)] == [s.id]
    assert unidentified.id in {x.id for x in sighting_repo.list_sightings(db, unidentified_only=True)}
    assert s.id not in {x.id for x in sighting_repo.list_sightings(db, since=now + timedelta(seconds=1))}

    sighting_repo.update_sighting(db, s.id, SightingUpdate(notes="grazing"))
    assert s.notes == "grazing" and s.latitude == -1.5

    sighting_repo.delete_sighting(db, s.id)
    with pytest.raises(NotFoundError):
        sighting_repo.get_sighting(db, s.id)


def test_sighting_db_checks(db):
    from app.models import Sighting

    now = datetime.now(timezone.utc)
    with expect_integrity_error(db, "ck_sightings_lat_range"):
        db.add(Sighting(observed_at=now, latitude=95, longitude=10))
    with expect_integrity_error(db, "ck_sightings_lat_lon_pair"):
        db.add(Sighting(observed_at=now, latitude=10))


def test_updated_at_changes(db, make_zebra):
    z = make_zebra()
    before = z.updated_at
    zebra_repo.update_zebra(db, z.id, ZebraUpdate(name="new"))
    db.refresh(z)
    assert z.updated_at > before
