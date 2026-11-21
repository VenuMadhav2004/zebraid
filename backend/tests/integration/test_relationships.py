"""Foreign keys, deletion policies and gallery registration."""
import uuid
from datetime import datetime, timezone

import pytest

from app.models import GalleryEntry, IdentificationRun, ImageKind, Sighting, ZebraStatus
from app.repositories import gallery as gallery_repo
from app.repositories import images as image_repo
from app.repositories import sightings as sighting_repo
from app.repositories import zebras as zebra_repo
from app.repositories.base import DomainRuleError
from app.schemas import GalleryEntryCreate, GalleryEntryUpdate, SightingCreate, ZebraUpdate
from tests.conftest import expect_integrity_error


def test_fk_rejects_missing_zebra(db, make_image):
    with expect_integrity_error(db, "fk_gallery_entries_zebra_id_zebras"):
        db.add(GalleryEntry(zebra_id=uuid.uuid4(), image_asset_id=make_image(ImageKind.REFERENCE).id))


def test_fk_rejects_missing_image(db):
    with expect_integrity_error(db, "fk_identification_runs_query_image_id_image_assets"):
        db.add(IdentificationRun(query_image_id=uuid.uuid4(), model_name="x"))


def test_register_reference_and_crop(db, make_zebra, make_image):
    z = make_zebra()
    ref = make_image(ImageKind.REFERENCE)
    crop = make_image(ImageKind.CROP)
    e1 = gallery_repo.register_gallery_entry(db, GalleryEntryCreate(zebra_id=z.id, image_asset_id=ref.id, side="left"))
    e2 = gallery_repo.register_gallery_entry(db, GalleryEntryCreate(zebra_id=z.id, image_asset_id=crop.id))
    assert e1.zebra is z and e1.image_asset is ref and ref.gallery_entry is e1
    assert {e.id for e in gallery_repo.list_gallery_for_zebra(db, z.id)} == {e1.id, e2.id}
    assert gallery_repo.is_gallery_image_of(db, ref.id, z.id)


def test_query_image_cannot_enter_gallery(db, make_zebra, make_image):
    with pytest.raises(DomainRuleError):
        gallery_repo.register_gallery_entry(
            db, GalleryEntryCreate(zebra_id=make_zebra().id, image_asset_id=make_image(ImageKind.QUERY).id)
        )


def test_image_in_one_gallery_only(db, make_zebra, make_image):
    ref = make_image(ImageKind.REFERENCE)
    gallery_repo.register_gallery_entry(db, GalleryEntryCreate(zebra_id=make_zebra().id, image_asset_id=ref.id))
    with expect_integrity_error(db, "uq_gallery_entries_image_asset_id"):
        gallery_repo.register_gallery_entry(db, GalleryEntryCreate(zebra_id=make_zebra().id, image_asset_id=ref.id))


def test_active_gallery_excludes_inactive(db, make_gallery_zebra):
    z1, (keep, drop) = make_gallery_zebra(n=2)
    z2, (retired_entry,) = make_gallery_zebra(n=1)
    gallery_repo.deactivate_gallery_entry(db, drop.id)
    zebra_repo.update_zebra(db, z2.id, ZebraUpdate(status=ZebraStatus.DECEASED))
    ids = {e.id for e in gallery_repo.list_active_gallery(db)}
    assert keep.id in ids and drop.id not in ids and retired_entry.id not in ids
    gallery_repo.update_gallery_entry(db, drop.id, GalleryEntryUpdate(is_active=True))
    assert drop.id in {e.id for e in gallery_repo.list_active_gallery(db)}


def test_delete_zebra_cascades_gallery_but_keeps_images(db, make_gallery_zebra):
    z, (entry,) = make_gallery_zebra(n=1)
    image_id, entry_id = entry.image_asset_id, entry.id
    zebra_repo.delete_zebra(db, z.id)
    db.expire_all()
    assert db.get(GalleryEntry, entry_id) is None
    assert image_repo.get_image_asset(db, image_id) is not None


def test_delete_zebra_with_sighting_restricted(db, make_zebra):
    z = make_zebra()
    sighting_repo.create_sighting(db, SightingCreate(observed_at=datetime.now(timezone.utc), zebra_id=z.id))
    with expect_integrity_error(db, "fk_sightings_zebra_id_zebras"):
        zebra_repo.delete_zebra(db, z.id)


def test_delete_gallery_image_restricted(db, make_gallery_zebra):
    _, (entry,) = make_gallery_zebra(n=1)
    with expect_integrity_error(db, "fk_gallery_entries_image_asset_id_image_assets"):
        image_repo.delete_image_asset(db, entry.image_asset_id)


def test_delete_source_of_crop_restricted(db, make_image):
    crop = make_image(ImageKind.CROP)
    with expect_integrity_error(db, "fk_image_assets_source_image_id_image_assets"):
        image_repo.delete_image_asset(db, crop.source_image_id)


def test_deleting_sighting_image_sets_null(db, make_image):
    img = make_image()
    s = sighting_repo.create_sighting(db, SightingCreate(observed_at=datetime.now(timezone.utc), image_asset_id=img.id))
    image_repo.delete_image_asset(db, img.id)
    db.expire_all()
    assert db.get(Sighting, s.id).image_asset_id is None
