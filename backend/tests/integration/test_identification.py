"""Run persistence, candidate ranking, unknown identities and verification.

Candidate payloads are hand-written test fixtures shaped like the documented
identify_zebra() output ({identity, similarity}); they are not model outputs.
"""
import pytest

from app.models import IdentificationCandidate, ImageKind, RunStatus, VerificationDecision
from app.repositories import identifications as run_repo
from app.repositories import verifications as ver_repo
from app.repositories import zebras as zebra_repo
from app.repositories.base import DomainRuleError
from app.schemas import (
    CandidateCreate,
    IdentificationRunCreate,
    RunCompletion,
    RunFailure,
    VerificationCreate,
)
from tests.conftest import expect_integrity_error

MODEL = "test-encoder"


@pytest.fixture
def new_run(db, make_image):
    def _make(kind=ImageKind.QUERY):
        return run_repo.create_run(
            db,
            IdentificationRunCreate(
                query_image_id=make_image(kind).id, model_name=MODEL, model_version="v-test", parameters={"top_k": 3}
            ),
        )

    return _make


@pytest.fixture
def completed_run(db, new_run, make_gallery_zebra):
    """Run with 2 registered candidates + 1 unmapped label."""
    (z1, (e1,)), (z2, _) = make_gallery_zebra(), make_gallery_zebra()
    run = new_run()
    run_repo.mark_running(db, run.id)
    run_repo.complete_run(
        db,
        run.id,
        RunCompletion(
            candidates=[
                CandidateCreate(rank=2, zebra_id=z2.id, similarity_score=0.61, score_type="cosine"),
                CandidateCreate(rank=1, zebra_id=z1.id, similarity_score=0.83, score_type="cosine",
                                matched_reference_image_id=e1.image_asset_id, evidence={"margin": 0.22}),
                CandidateCreate(rank=3, external_label="GZCD-unmapped-17", similarity_score=0.40),
            ],
            processing_metadata={"raw": {"margin": 0.22, "unknown": None}},
            predicted_unknown=None,
        ),
    )
    return run, z1, z2


def test_run_lifecycle(db, new_run):
    run = new_run()
    assert run.status == RunStatus.PENDING and run.started_at is None
    run_repo.mark_running(db, run.id)
    assert run.status == RunStatus.RUNNING and run.started_at is not None
    run_repo.complete_run(db, run.id, RunCompletion(model_version="sha-abc"))
    assert run.status == RunStatus.COMPLETED and run.completed_at >= run.started_at
    assert run.model_version == "sha-abc" and run.candidates == []
    with pytest.raises(DomainRuleError):
        run_repo.mark_running(db, run.id)
    with pytest.raises(DomainRuleError):
        run_repo.fail_run(db, run.id, RunFailure(error_message="late"))


def test_run_on_crop_allowed_on_reference_refused(db, new_run):
    assert new_run(ImageKind.CROP).status == RunStatus.PENDING
    with pytest.raises(DomainRuleError):
        new_run(ImageKind.REFERENCE)


def test_failed_run_persists_error(db, new_run):
    run = new_run()
    run_repo.fail_run(db, run.id, RunFailure(error_message="region is outside image", error_code="ValueError"))
    db.expire_all()
    stored = run_repo.get_run(db, run.id)
    assert stored.status == RunStatus.FAILED and stored.error_code == "ValueError" and stored.completed_at


def test_db_requires_error_for_failed(db, new_run):
    run = new_run()
    with expect_integrity_error(db, "ck_identification_runs_failed_has_error"):
        run.status = RunStatus.FAILED


def test_candidates_ranked(db, completed_run):
    run, z1, z2 = completed_run
    ranked = run_repo.list_candidates(db, run.id)
    assert [c.rank for c in ranked] == [1, 2, 3]
    assert [c.zebra_id for c in ranked[:2]] == [z1.id, z2.id]
    assert run_repo.top_candidate(db, run.id).similarity_score == pytest.approx(0.83)
    assert ranked[0].evidence == {"margin": 0.22}
    db.expire_all()
    assert [c.rank for c in run_repo.get_run(db, run.id, with_candidates=True).candidates] == [1, 2, 3]
    assert run_repo.list_candidate_runs_for_zebra(db, z2.id)[0].run_id == run.id


def test_duplicate_rank_rejected_by_db(db, completed_run):
    run, z1, _ = completed_run
    with expect_integrity_error(db, "uq_identification_candidates_run_rank"):
        db.add(IdentificationCandidate(run_id=run.id, rank=1, zebra_id=z1.id, similarity_score=0.1))


def test_unknown_identity_stored_without_zebra(db, completed_run):
    run, *_ = completed_run
    unknown = run_repo.list_candidates(db, run.id)[2]
    assert unknown.zebra_id is None and unknown.external_label == "GZCD-unmapped-17"
    assert zebra_repo.get_zebra_by_code(db, "GZCD-unmapped-17") is None  # no zebra invented


def test_candidate_needs_some_identity_ref(db, completed_run):
    run, *_ = completed_run
    with expect_integrity_error(db, "ck_identification_candidates_has_identity_ref"):
        db.add(IdentificationCandidate(run_id=run.id, rank=9, similarity_score=0.1))


def test_predicted_unknown_tristate(db, new_run):
    run = new_run()
    run_repo.complete_run(db, run.id, RunCompletion(predicted_unknown=True))
    assert run.predicted_unknown is True and run.candidates == []


def test_matched_reference_must_be_candidates_gallery(db, new_run, make_gallery_zebra):
    (z1, _), (_, (other_entry,)) = make_gallery_zebra(), make_gallery_zebra()
    run = new_run()
    with pytest.raises(DomainRuleError):
        run_repo.complete_run(
            db, run.id,
            RunCompletion(candidates=[CandidateCreate(rank=1, zebra_id=z1.id, similarity_score=0.9,
                                                      matched_reference_image_id=other_entry.image_asset_id)]),
        )


def test_resolve_labels(db, make_zebra):
    z1, z2 = make_zebra(), make_zebra()
    out = zebra_repo.resolve_labels(db, [str(z1.id), z2.code, "nobody", "00000000-0000-0000-0000-000000000000"])
    assert out == {str(z1.id): z1.id, z2.code: z2.id, "nobody": None, "00000000-0000-0000-0000-000000000000": None}


def test_verification_confirm_reject_unknown(db, completed_run):
    run, z1, z2 = completed_run
    top, second, unmapped = run_repo.list_candidates(db, run.id)

    rej = ver_repo.create_verification(db, VerificationCreate(
        run_id=run.id, decision="rejected", candidate_id=second.id, verified_by="ranger-a"))
    assert rej.zebra_id is None

    conf = ver_repo.create_verification(db, VerificationCreate(
        run_id=run.id, decision="confirmed", candidate_id=top.id, verified_by="ranger-a"))
    assert conf.zebra_id == z1.id and conf.candidate is top
    assert ver_repo.latest_verification(db, run.id).id == conf.id

    unk = ver_repo.create_verification(db, VerificationCreate(
        run_id=run.id, decision="unknown", verified_by="ranger-b", notes="new individual?"))
    assert unk.zebra_id is None and unk.candidate_id is None
    assert ver_repo.latest_verification(db, run.id).decision == VerificationDecision.UNKNOWN
    assert [v.id for v in ver_repo.list_verifications(db, run.id)] == [rej.id, conf.id, unk.id]
    assert [v.id for v in ver_repo.list_confirmed_for_zebra(db, z1.id)] == [conf.id]

    with pytest.raises(DomainRuleError):  # unmapped label cannot be confirmed
        ver_repo.create_verification(db, VerificationCreate(
            run_id=run.id, decision="confirmed", candidate_id=unmapped.id, verified_by="ranger-a"))


def test_verification_needs_completed_run(db, new_run):
    run = new_run()
    with pytest.raises(DomainRuleError):
        ver_repo.create_verification(db, VerificationCreate(run_id=run.id, decision="unknown", verified_by="x"))


def test_verification_candidate_from_other_run(db, completed_run, new_run):
    run, *_ = completed_run
    other = new_run()
    run_repo.complete_run(db, other.id, RunCompletion())
    cand = run_repo.top_candidate(db, run.id)
    with pytest.raises(DomainRuleError):
        ver_repo.create_verification(db, VerificationCreate(
            run_id=other.id, decision="rejected", candidate_id=cand.id, verified_by="x"))
    # and the composite FK enforces it in the DB as well
    from app.models import Verification

    with expect_integrity_error(db, "fk_verifications_candidate_run"):
        db.add(Verification(run_id=other.id, candidate_id=cand.id, decision="rejected", verified_by="x"))


def test_db_decision_shape(db, completed_run):
    from app.models import Verification

    run, z1, _ = completed_run
    with expect_integrity_error(db, "ck_verifications_decision_shape"):
        db.add(Verification(run_id=run.id, decision="unknown", zebra_id=z1.id, verified_by="x"))


def test_verified_run_cannot_be_deleted(db, completed_run):
    run, *_ = completed_run
    ver_repo.create_verification(db, VerificationCreate(run_id=run.id, decision="unknown", verified_by="x"))
    with expect_integrity_error(db, "fk_verifications_run_id_identification_runs"):
        run_repo.delete_run(db, run.id)


def test_unverified_run_delete_cascades_candidates(db, completed_run):
    run, *_ = completed_run
    run_id = run.id
    run_repo.delete_run(db, run_id)
    db.expire_all()
    assert run_repo.list_candidates(db, run_id) == []
