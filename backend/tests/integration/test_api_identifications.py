"""Identification history + human review API.

Runs/candidates are inserted through the existing repositories as rolled-back
TEST fixtures (the API itself has no way to create them). Scores here are
arbitrary test values, not model output.
"""
import uuid

import pytest

from app.models import ImageKind
from app.repositories import identifications as run_repo
from app.schemas import CandidateCreate, IdentificationRunCreate, RunCompletion

R = "/api/v1/identifications"


@pytest.fixture
def completed_run(db, make_image, make_gallery_zebra):
    zebra, entries = make_gallery_zebra(1)
    query = make_image(ImageKind.QUERY)
    run = run_repo.create_run(db, IdentificationRunCreate(query_image_id=query.id, model_name="test-fixture"))
    run_repo.complete_run(
        db,
        run.id,
        RunCompletion(
            candidates=[
                CandidateCreate(rank=2, similarity_score=0.41, external_label="unmapped-label"),
                CandidateCreate(rank=1, similarity_score=0.73, zebra_id=zebra.id,
                                matched_reference_image_id=entries[0].image_asset_id, score_type="cosine similarity"),
            ]
        ),
    )
    return run, zebra, query


def test_list_and_filter_runs(api, db, completed_run, make_image):
    run, _, query = completed_run
    pending = run_repo.create_run(db, IdentificationRunCreate(query_image_id=query.id, model_name="test-fixture"))
    page = api.get(R, params={"query_image_id": str(query.id)}).json()
    assert page["total"] == 2 and {r["id"] for r in page["items"]} == {str(run.id), str(pending.id)}
    only = api.get(R, params={"query_image_id": str(query.id), "status": "completed"}).json()
    assert [r["id"] for r in only["items"]] == [str(run.id)]
    assert api.get(R, params={"status": "bogus"}).status_code == 422


def test_run_detail_candidates_ranked(api, completed_run):
    run, zebra, _ = completed_run
    detail = api.get(f"{R}/{run.id}").json()
    assert detail["status"] == "completed" and [c["rank"] for c in detail["candidates"]] == [1, 2]
    top = detail["candidates"][0]
    assert top["zebra_id"] == str(zebra.id) and top["similarity_score"] == 0.73
    assert detail["candidates"][1]["zebra_id"] is None and detail["candidates"][1]["external_label"] == "unmapped-label"
    cands = api.get(f"{R}/{run.id}/candidates").json()
    assert [c["rank"] for c in cands] == [1, 2]
    for path in ("", "/candidates", "/verifications"):
        assert api.get(f"{R}/{uuid.uuid4()}{path}").status_code == 404


def test_inference_endpoint_validates_payload_and_reports_capabilities(api):
    caps = api.get(f"{R}/capabilities")
    assert caps.status_code == 200
    assert caps.json()["model_name"] == "BVRA/MegaDescriptor-L-384"
    assert caps.json()["device"] == "cpu"
    assert api.post(R, json={}).status_code == 422


def test_human_review_flow(api, completed_run):
    run, zebra, _ = completed_run
    cands = api.get(f"{R}/{run.id}/candidates").json()
    url = f"{R}/{run.id}/verifications"
    assert api.get(url).json() == []  # nothing confirmed automatically

    rejected = api.post(url, json={"decision": "rejected", "candidate_id": cands[1]["id"], "verified_by": "rev1"})
    assert rejected.status_code == 201 and rejected.json()["zebra_id"] is None
    confirmed = api.post(url, json={"decision": "confirmed", "candidate_id": cands[0]["id"], "verified_by": "rev2"})
    assert confirmed.status_code == 201 and confirmed.json()["zebra_id"] == str(zebra.id)
    unknown = api.post(url, json={"decision": "unknown", "verified_by": "rev3", "notes": "second look"})
    assert unknown.status_code == 201

    history = api.get(url).json()
    assert [v["decision"] for v in history] == ["rejected", "confirmed", "unknown"]


def test_review_rules(api, db, completed_run, make_image):
    run, _, query = completed_run
    cands = api.get(f"{R}/{run.id}/candidates").json()
    url = f"{R}/{run.id}/verifications"
    unmapped = api.post(url, json={"decision": "confirmed", "candidate_id": cands[1]["id"], "verified_by": "r"})
    assert unmapped.status_code == 422 and unmapped.json()["error"]["code"] == "domain_rule_violation"
    assert api.post(url, json={"decision": "confirmed", "verified_by": "r"}).status_code == 422
    assert api.post(url, json={"decision": "unknown", "candidate_id": cands[0]["id"], "verified_by": "r"}).status_code == 422
    assert api.post(url, json={"decision": "rejected", "candidate_id": cands[0]["id"], "verified_by": ""}).status_code == 422
    missing = api.post(url, json={"decision": "rejected", "candidate_id": str(uuid.uuid4()), "verified_by": "r"})
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "invalid_reference"

    pending = run_repo.create_run(db, IdentificationRunCreate(query_image_id=query.id, model_name="test-fixture"))
    not_done = api.post(f"{R}/{pending.id}/verifications", json={"decision": "unknown", "verified_by": "r"})
    assert not_done.status_code == 422 and "completed" in not_done.json()["error"]["message"]
    other_run = api.post(f"{R}/{pending.id}/verifications",
                         json={"decision": "rejected", "candidate_id": cands[0]["id"], "verified_by": "r"})
    assert other_run.status_code == 422
    assert api.post(f"{R}/{uuid.uuid4()}/verifications", json={"decision": "unknown", "verified_by": "r"}).status_code == 404
