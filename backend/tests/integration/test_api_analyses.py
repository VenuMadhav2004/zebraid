"""Integration tests for scientific stripe analysis API, persistence, and private artifact storage.

Uses the rolled-back PostgreSQL fixture transaction (`db`). If the `stripe_analyses`
migration has not been applied to live Supabase yet, the fixture creates the table
inside the rolled-back outer transaction (PostgreSQL transactional DDL) so live
Supabase stays 100% untouched.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings
from app.integrations.science import MEMBER1_COMMIT, MEMBER2_COMMIT, WorkerOutcome
from app.models import AnalysisKind, RunStatus, StripeAnalysis
from app.repositories import stripe_analyses as analysis_repo
from app.services import stripe_analyses as analysis_service
from tests.conftest import image_bytes, unique_color, upload

ANALYSES = "/api/v1/analyses"


@pytest.fixture
def analyses_table(db):
    if not analysis_repo.table_exists(db):
        StripeAnalysis.__table__.create(bind=db.connection())
    yield


@pytest.fixture
def mock_available_capabilities(monkeypatch):
    def _fake_caps(settings=None, *, refresh=False):
        s = settings or Settings(_env_file=None)
        from app.schemas import AnalysisCapabilitiesResponse, AnalysisCapabilityItem, AnalysisLimitsRead

        return AnalysisCapabilitiesResponse(
            stripe_morphology=AnalysisCapabilityItem(
                available=True, reason=None, source_commit=MEMBER1_COMMIT, schema_version="1.0.0"
            ),
            spatial_frequency=AnalysisCapabilityItem(
                available=True, reason=None, source_commit=MEMBER2_COMMIT, schema_version="stripecode.science.v1"
            ),
            limits=AnalysisLimitsRead(
                max_pixels=s.analysis_max_pixels,
                max_source_pixels=s.analysis_max_source_pixels,
                max_dimension=s.analysis_max_dimension,
                queue_limit=s.analysis_queue_limit,
                timeout_seconds=s.analysis_timeout_seconds,
            ),
        )

    monkeypatch.setattr(analysis_service, "get_capabilities", _fake_caps)


def test_capabilities_endpoint_returns_limits_and_commits(api):
    resp = api.get(f"{ANALYSES}/capabilities")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stripe_morphology"]["source_commit"] == MEMBER1_COMMIT
    assert body["spatial_frequency"]["source_commit"] == MEMBER2_COMMIT
    assert body["limits"]["max_pixels"] == 4_000_000
    assert body["limits"]["queue_limit"] == 3
    assert body["limits"]["timeout_seconds"] == 120


def test_submit_returns_503_when_runtime_unavailable(api, analyses_table, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.api.v1.endpoints.analyses.get_settings",
        lambda: Settings(_env_file=None, science_vendor_dir=str(tmp_path / "missing_vendor")),
    )
    img = upload(api, image_bytes(size=(128, 96), color=unique_color())).json()
    resp = api.post(f"{ANALYSES}/stripe-morphology", json={"image_id": img["id"]})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "analysis_unavailable"


def test_combined_analysis_submits_both_jobs_and_respects_queue_limit(
    api, analyses_table, mock_available_capabilities
):
    img = upload(api, image_bytes(size=(160, 120), color=unique_color())).json()
    resp = api.post(
        f"{ANALYSES}/combined",
        json={
            "image_id": img["id"],
            "roi": {"x": 16, "y": 16, "width": 96, "height": 80},
            "morphology_config": {"clahe_clip_limit": 2.5},
            "frequency_options": {"filter_type": "gaussian", "cutoff_cpp": 0.08},
        },
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["stripe_morphology"]["kind"] == "stripe_morphology"
    assert body["stripe_morphology"]["roi_mode"] == "mask"
    assert body["spatial_frequency"]["kind"] == "spatial_frequency"
    assert body["spatial_frequency"]["roi_mode"] == "box"
    assert body["stripe_morphology"]["roi"] == body["spatial_frequency"]["roi"] == {
        "x": 16,
        "y": 16,
        "width": 96,
        "height": 80,
    }
    assert "mask" in body["roi_semantics_note"].lower()

    # Queue limit is 3 and 2 jobs are already pending -> a second combined pair (needs 2) returns 503 analysis_busy
    second = api.post(f"{ANALYSES}/combined", json={"image_id": img["id"]})
    assert second.status_code == 503
    assert second.json()["error"]["code"] == "analysis_busy"


def test_morphology_and_frequency_lifecycle_artifacts_and_image_delete_guard(
    api, db, fake_storage, analyses_table, mock_available_capabilities
):
    img = upload(api, image_bytes(size=(160, 120), color=unique_color())).json()

    # 1. Submit Member 1 morphology job (explicit ROI -> mask mode)
    r1 = api.post(
        f"{ANALYSES}/stripe-morphology",
        json={
            "image_id": img["id"],
            "roi": {"x": 10, "y": 10, "width": 100, "height": 80},
            "config": {"clahe_clip_limit": 2.5},
        },
    )
    assert r1.status_code == 202, r1.text
    job1 = r1.json()
    assert job1["status"] == "pending"
    assert job1["kind"] == "stripe_morphology"
    assert job1["roi_mode"] == "mask"
    assert job1["provider"]["source_commit"] == MEMBER1_COMMIT
    assert job1["artifacts"] == []

    # 2. Execute job via service with fake worker outcome (real PNG bytes uploaded to private storage)
    png_mask = image_bytes("PNG", size=(160, 120), color=(255, 255, 255))
    png_overlay = image_bytes("PNG", size=(160, 120), color=(0, 180, 220))

    def _fake_m1_runner(**kw):
        assert kw["kind"] == "stripe_morphology"
        assert kw["roi_mode"] == "mask"
        return WorkerOutcome(
            ok=True,
            result={
                "schema_version": "1.0.0",
                "segmentation_status": "SUCCESS",
                "quality_metrics": {"contrast_ratio": 0.45, "edge_sharpness": 120.0, "confidence_score": 0.82},
                "stripe_mask_reference": "mask",
                "visualization_reference": "overlay",
                "width_statistics": {
                    "mean_px": 11.4,
                    "median_px": 11.0,
                    "std_px": 2.1,
                    "min_px": 6.0,
                    "max_px": 18.0,
                    "p10_px": 8.0,
                    "p90_px": 15.0,
                    "sample_count": 40,
                },
                "warnings": [],
                "processing_time_seconds": 0.42,
            },
            artifact_bytes={"mask": png_mask, "overlay": png_overlay},
        )

    done1 = analysis_service.execute_analysis_job(db, fake_storage, Settings(_env_file=None), uuid.UUID(job1["id"]), runner=_fake_m1_runner)
    assert done1.status == RunStatus.COMPLETED
    assert done1.artifacts == ["mask", "overlay"]

    # 3. Fetch job via GET — never exposes storage paths or /tmp
    fetched = api.get(f"{ANALYSES}/{job1['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["artifacts"] == ["mask", "overlay"]
    assert "analysis/" not in fetched.text and "/tmp" not in fetched.text

    # 4. Signed URL for stored artifact PNG; unknown artifact -> 404
    url_resp = api.get(f"{ANALYSES}/{job1['id']}/artifacts/overlay/url", params={"expires_in": 300})
    assert url_resp.status_code == 200
    assert url_resp.json()["expires_in"] == 300 and "token=" in url_resp.json()["url"]
    assert api.get(f"{ANALYSES}/{job1['id']}/artifacts/not_real/url").status_code == 404

    # 5. Image cannot be deleted while referenced by stripe_analyses
    del_img = api.delete(f"/api/v1/images/{img['id']}")
    assert del_img.status_code == 409
    assert del_img.json()["error"]["code"] == "image_in_use"
    assert del_img.json()["error"]["details"]["stripe_analyses"] == 1

    # 6. Submit Member 2 spatial-frequency job
    r2 = api.post(
        f"{ANALYSES}/spatial-frequency",
        json={
            "image_id": img["id"],
            "roi": {"x": 0, "y": 0, "width": 64, "height": 64},
            "options": {"filter_type": "bandpass", "cutoff_cpp": 0.12, "band_low_cpp": 0.03},
        },
    )
    assert r2.status_code == 202, r2.text
    job2 = r2.json()
    assert job2["kind"] == "spatial_frequency"
    assert job2["roi_mode"] == "box"
    assert job2["provider"]["source_commit"] == MEMBER2_COMMIT

    # 7. List analyses filtered by image_id and kind
    listed = api.get(ANALYSES, params={"image_id": img["id"], "kind": "stripe_morphology"}).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == job1["id"]

    # 8. Delete running job -> 409; delete completed job -> 204 & removes artifact objects
    analysis_repo.mark_running(db, uuid.UUID(job2["id"]))
    db.commit()
    assert api.delete(f"{ANALYSES}/{job2['id']}").status_code == 409

    # Recover stale running job on restart -> failed/interrupted
    recovered = analysis_repo.recover_interrupted_running(db)
    db.commit()
    assert recovered == 1
    assert api.get(f"{ANALYSES}/{job2['id']}").json()["error_code"] == "interrupted"

    stored_before = len(fake_storage.objects)
    assert api.delete(f"{ANALYSES}/{job1['id']}").status_code == 204
    assert len(fake_storage.objects) == stored_before - 2  # mask + overlay removed
    assert api.delete(f"{ANALYSES}/{job2['id']}").status_code == 204
    # Now image can be deleted cleanly
    assert api.delete(f"/api/v1/images/{img['id']}").status_code == 204


def test_queue_limit_returns_503_analysis_busy(api, analyses_table, mock_available_capabilities):
    img = upload(api, image_bytes(size=(128, 128), color=unique_color())).json()
    for _ in range(3):
        r = api.post(f"{ANALYSES}/spatial-frequency", json={"image_id": img["id"]})
        assert r.status_code == 202
    fourth = api.post(f"{ANALYSES}/spatial-frequency", json={"image_id": img["id"]})
    assert fourth.status_code == 503
    assert fourth.json()["error"]["code"] == "analysis_busy"


def test_analysis_limit_exceeded_returns_422(api, db, analyses_table, mock_available_capabilities, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.analyses.get_settings",
        lambda: Settings(_env_file=None, analysis_max_pixels=5000),
    )
    img = upload(api, image_bytes(size=(100, 100), color=unique_color())).json()
    resp = api.post(f"{ANALYSES}/stripe-morphology", json={"image_id": img["id"]})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "analysis_limit_exceeded"
    assert "crop" in resp.json()["error"]["message"].lower()

    # Member 2 on a small 40x40 = 1600 px ROI still succeeds under the 5000 px limit!
    ok = api.post(
        f"{ANALYSES}/spatial-frequency",
        json={"image_id": img["id"], "roi": {"x": 0, "y": 0, "width": 40, "height": 40}},
    )
    assert ok.status_code == 202
    assert ok.json()["kind"] == AnalysisKind.SPATIAL_FREQUENCY.value


def test_capabilities_report_unavailable_without_results_table(api, db):
    if analysis_repo.table_exists(db):
        pytest.skip("stripe_analyses exists in this database; the missing-table path is not reachable")
    body = api.get(f"{ANALYSES}/capabilities").json()
    for kind in ("stripe_morphology", "spatial_frequency"):
        assert body[kind]["available"] is False
        assert "a8d3f2c91b40" in body[kind]["reason"]


def test_capabilities_available_once_results_table_exists(api, analyses_table):
    body = api.get(f"{ANALYSES}/capabilities").json()
    for kind in ("stripe_morphology", "spatial_frequency"):
        assert body[kind]["available"] is True, body[kind]
