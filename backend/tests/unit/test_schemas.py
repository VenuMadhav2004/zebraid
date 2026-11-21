"""Pure Pydantic validation (no database)."""
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import (
    CandidateCreate,
    CropBox,
    ImageAssetCreate,
    RunCompletion,
    SightingCreate,
    VerificationCreate,
    ZebraCreate,
)

BASE_IMG = {"storage_bucket": "zebra_images", "storage_path": "a/b.jpg", "content_type": "image/jpeg"}


def test_storage_path_must_not_be_url():
    with pytest.raises(ValidationError):
        ImageAssetCreate(kind="query", storage_bucket="zebra_images", storage_path="https://x/y.jpg", content_type="image/jpeg")


def test_crop_lineage_required():
    with pytest.raises(ValidationError):
        ImageAssetCreate(kind="crop", **BASE_IMG)
    with pytest.raises(ValidationError):
        ImageAssetCreate(kind="query", source_image_id=uuid.uuid4(), crop_bbox=CropBox(x=0, y=0, width=2, height=2), **BASE_IMG)
    ImageAssetCreate(kind="crop", source_image_id=uuid.uuid4(), crop_bbox=CropBox(x=0, y=0, width=2, height=2), **BASE_IMG)


def test_candidate_rules():
    with pytest.raises(ValidationError):
        CandidateCreate(rank=1, similarity_score=0.5)  # no identity reference
    with pytest.raises(ValidationError):
        CandidateCreate(rank=0, similarity_score=0.5, external_label="x")
    with pytest.raises(ValidationError):
        CandidateCreate(rank=1, similarity_score=float("nan"), external_label="x")


def test_completion_rank_unique():
    c = {"similarity_score": 0.1, "external_label": "x"}
    with pytest.raises(ValidationError):
        RunCompletion(candidates=[CandidateCreate(rank=1, **c), CandidateCreate(rank=1, **c)])


def test_verification_shapes():
    run = uuid.uuid4()
    with pytest.raises(ValidationError):
        VerificationCreate(run_id=run, decision="confirmed", verified_by="x")
    with pytest.raises(ValidationError):
        VerificationCreate(run_id=run, decision="unknown", candidate_id=uuid.uuid4(), verified_by="x")
    VerificationCreate(run_id=run, decision="unknown", verified_by="x")


def test_sighting_coords_paired():
    with pytest.raises(ValidationError):
        SightingCreate(observed_at=datetime.now(timezone.utc), latitude=1.0)


def test_zebra_code_pattern():
    with pytest.raises(ValidationError):
        ZebraCreate(code="bad code!")


@pytest.mark.parametrize("path", ["a/../b.jpg", "..", "a/..", "a\\b.jpg", "a\x00b.jpg", "a\nb.jpg"])
def test_unsafe_storage_paths_rejected(path):
    with pytest.raises(ValidationError):
        ImageAssetCreate(kind="query", **{**BASE_IMG, "storage_path": path})


@pytest.mark.parametrize("ctype", [None, "image/gif", "text/plain", "application/octet-stream"])
def test_content_type_required_and_allowed(ctype):
    with pytest.raises(ValidationError):
        ImageAssetCreate(kind="query", **{**BASE_IMG, "content_type": ctype})


@pytest.mark.parametrize("score", [float("inf"), float("-inf")])
def test_infinite_score_rejected(score):
    with pytest.raises(ValidationError):
        CandidateCreate(rank=1, similarity_score=score, external_label="x")


def test_negative_and_large_scores_allowed():
    """Similarities are not probabilities: no [0, 1] range is imposed."""
    CandidateCreate(rank=1, similarity_score=-0.3, external_label="x")
    CandidateCreate(rank=1, similarity_score=4.2, external_label="x")
