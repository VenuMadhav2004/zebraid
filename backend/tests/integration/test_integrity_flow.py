"""Phase 2.5 integrity checks: full relational flow, invalid operations, atomicity.

Runs in the rolled-back `db` fixture: nothing persists. Candidate scores are
hand-written fixtures, not model output.
"""
import math
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from app.models import (
    GalleryEntry,
    IdentificationCandidate,
    IdentificationRun,
    ImageAsset,
    ImageKind,
    RunStatus,
    Sighting,
    Verification,
    VerificationDecision,
    Zebra,
)
from app.repositories import gallery as gallery_repo
from app.repositories import identifications as run_repo
from app.repositories import sightings as sighting_repo
from app.repositories import verifications as ver_repo
from app.repositories import zebras as zebra_repo
from app.schemas import (
    CandidateCreate,
    GalleryEntryCreate,
    IdentificationRunCreate,
    RunCompletion,
    SightingCreate,
    VerificationCreate,
)
from tests.conftest import BUCKET, expect_integrity_error


def test_full_flow(db, make_zebra, make_image):
    zebra = make_zebra(name="Flow")                                            # 1
    ref = make_image(ImageKind.REFERENCE)                                      # 2
    entry = gallery_repo.register_gallery_entry(                               # 3
        db, GalleryEntryCreate(zebra_id=zebra.id, image_asset_id=ref.id, side="right")
    )
    db.expire_all()
    got = gallery_repo.get_gallery_entry(db, entry.id)                         # 4
    assert got.zebra.id == zebra.id and got.image_asset.id == ref.id

    query = make_image(ImageKind.QUERY)
    run = run_repo.create_run(db, IdentificationRunCreate(query_image_id=query.id, model_name="m"))  # 5
    run_repo.complete_run(db, run.id, RunCompletion(candidates=[                # 6, 7
        CandidateCreate(rank=1, zebra_id=zebra.id, similarity_score=0.71, matched_reference_image_id=ref.id)
    ]))
    cand = run_repo.top_candidate(db, run.id)
    ver = ver_repo.create_verification(db, VerificationCreate(                 # 8
        run_id=run.id, decision="confirmed", candidate_id=cand.id, verified_by="reviewer"))
    sighting = sighting_repo.create_sighting(db, SightingCreate(               # 9
        observed_at=datetime.now(timezone.utc), zebra_id=zebra.id, image_asset_id=query.id,
        identification_run_id=run.id, latitude=-2.3, longitude=34.8))

    db.expire_all()                                                            # 10
    z = zebra_repo.get_zebra(db, zebra.id)
    assert [e.image_asset_id for e in z.gallery_entries] == [ref.id]
    assert [s.id for s in z.sightings] == [sighting.id]
    r = run_repo.get_run(db, run.id, with_candidates=True)
    assert r.query_image.id == query.id and r.status == RunStatus.COMPLETED
    assert r.candidates[0].matched_reference_image.id == ref.id and r.candidates[0].zebra.id == zebra.id
    assert [v.id for v in r.verifications] == [ver.id] and r.verifications[0].candidate.id == cand.id
    s = sighting_repo.get_sighting(db, sighting.id)
    assert (s.zebra.id, s.image_asset.id, s.identification_run.id) == (zebra.id, query.id, run.id)


def test_gallery_missing_zebra_and_image(db, make_image):
    with expect_integrity_error(db, "fk_gallery_entries_zebra_id_zebras"):
        db.add(GalleryEntry(zebra_id=uuid.uuid4(), image_asset_id=make_image(ImageKind.REFERENCE).id))
    z = Zebra(code=f"T-{uuid.uuid4().hex[:8]}")
    db.add(z)
    db.flush()
    with expect_integrity_error(db, "fk_gallery_entries_image_asset_id_image_assets"):
        db.add(GalleryEntry(zebra_id=z.id, image_asset_id=uuid.uuid4()))


def test_candidate_invalid_run(db, make_zebra):
    with expect_integrity_error(db, "fk_identification_candidates_run_id_identification_runs"):
        db.add(IdentificationCandidate(run_id=uuid.uuid4(), rank=1, zebra_id=make_zebra().id, similarity_score=0.5))


def test_verification_invalid_candidate(db, make_image):
    run = run_repo.create_run(db, IdentificationRunCreate(query_image_id=make_image().id, model_name="m"))
    run_repo.complete_run(db, run.id, RunCompletion())
    with expect_integrity_error(db, "fk_verifications_candidate_run"):
        db.add(Verification(run_id=run.id, candidate_id=uuid.uuid4(), decision="rejected", verified_by="x"))


def test_confirmed_zebra_must_match_candidate_in_db(db, make_zebra, make_image):
    z1, z2 = make_zebra(), make_zebra()
    run = run_repo.create_run(db, IdentificationRunCreate(query_image_id=make_image().id, model_name="m"))
    run_repo.complete_run(db, run.id, RunCompletion(candidates=[CandidateCreate(rank=1, zebra_id=z1.id, similarity_score=0.9)]))
    cand = run_repo.top_candidate(db, run.id)
    with expect_integrity_error(db, "fk_verifications_candidate_zebra"):
        db.add(Verification(run_id=run.id, candidate_id=cand.id, zebra_id=z2.id,
                            decision=VerificationDecision.CONFIRMED, verified_by="x"))


@pytest.mark.parametrize("score", [math.inf, -math.inf, math.nan])
def test_non_finite_scores_rejected_by_db(db, make_zebra, make_image, score):
    run = run_repo.create_run(db, IdentificationRunCreate(query_image_id=make_image().id, model_name="m"))
    with expect_integrity_error(db, "ck_identification_candidates_score_finite"):
        db.add(IdentificationCandidate(run_id=run.id, rank=1, zebra_id=make_zebra().id, similarity_score=score))


@pytest.mark.filterwarnings("ignore:New instance .* conflicts with persistent instance")
def test_duplicate_identifiers(db, make_zebra, make_image):
    z = make_zebra()
    with expect_integrity_error(db, "pk_zebras"):
        db.add(Zebra(id=z.id, code=f"T-{uuid.uuid4().hex[:8]}"))
    with expect_integrity_error(db, "uq_zebras_code"):
        db.add(Zebra(code=z.code))
    img = make_image()
    with expect_integrity_error(db, "uq_image_assets_storage_object"):
        db.add(ImageAsset(kind=ImageKind.QUERY, storage_bucket=BUCKET, storage_path=img.storage_path, content_type="image/png"))


@pytest.mark.parametrize(
    "model,kwargs",
    [
        (Zebra, {}),                                                     # code
        (ImageAsset, {"kind": "query", "storage_bucket": BUCKET, "storage_path": "test/x.jpg"}),  # content_type
        (IdentificationRun, {"query_image_id": None, "model_name": "m"}),
        (Sighting, {}),                                                  # observed_at
        (Verification, {"decision": "unknown", "verified_by": None}),    # run_id / verified_by
    ],
)
def test_missing_required_fields(db, model, kwargs):
    with expect_integrity_error(db, "not-null"):
        db.add(model(**kwargs))


@pytest.mark.parametrize("path", ["a/../b.jpg", "../b.jpg", "a\\b.jpg", "a\nb.jpg"])
def test_db_rejects_unsafe_paths(db, path):
    with expect_integrity_error(db, "ck_image_assets_path_safe"):
        db.add(ImageAsset(kind=ImageKind.QUERY, storage_bucket=BUCKET, storage_path=path, content_type="image/jpeg"))


@pytest.mark.parametrize("ctype", ["image/gif", "text/html", "application/pdf"])
def test_db_rejects_disallowed_mime(db, ctype):
    with expect_integrity_error(db, "ck_image_assets_content_type_allowed"):
        db.add(ImageAsset(kind=ImageKind.QUERY, storage_bucket=BUCKET, storage_path=f"test/{uuid.uuid4().hex}", content_type=ctype))


def test_failed_transaction_leaves_nothing(db):
    """A multi-row write that fails part-way is rolled back as a unit."""
    code = f"T-atomic-{uuid.uuid4().hex[:8]}"
    sp = db.begin_nested()
    zebra = Zebra(code=code)
    db.add(zebra)
    db.flush()
    db.add(GalleryEntry(zebra_id=zebra.id, image_asset_id=uuid.uuid4()))  # invalid FK
    with pytest.raises(Exception):
        db.flush()
    sp.rollback()
    assert db.scalar(select(Zebra).where(Zebra.code == code)) is None
    assert db.execute(text("select count(*) from gallery_entries where zebra_id = :z"), {"z": zebra.id}).scalar() == 0


def test_search_wildcards_are_literal(db, make_zebra):
    target = make_zebra(code=f"T_{uuid.uuid4().hex[:6]}", name="100% stripes")
    other = make_zebra(code=f"T-{uuid.uuid4().hex[:6]}", name="1000 stripes")
    found = {z.id for z in zebra_repo.list_zebras(db, search="100%")}
    assert target.id in found and other.id not in found
    assert other.id not in {z.id for z in zebra_repo.list_zebras(db, search="T_")}


def test_no_binary_or_embedding_columns(engine):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "select table_name, column_name from information_schema.columns "
            "where table_schema='public' and (data_type in ('bytea','ARRAY') or udt_name in ('vector','bytea'))"
        )).all()
    assert rows == []
