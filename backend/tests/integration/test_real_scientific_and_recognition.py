"""Real (non-mocked) scientific pipeline, FastAPI, Supabase Storage, and MegaDescriptor-L-384 tests.

Uses:
  - tests/fixtures/zebra1/flank_left_mid.png (from Member 1 commit 871e2956)
  - Vendored research.member1.models.api.analyze_stripes & research.member2.science.safe_analyze
  - Real isolated spawned worker, real private Supabase Storage + signed URLs (cleaned up in teardown)
  - Real MegaDescriptor-L-384 v1 CPU inference + CpuGalleryIndex cached gallery + verification + sightings
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.api import deps
from app.core.config import Settings
from app.integrations.science.constants import MEMBER1_COMMIT, MEMBER2_COMMIT
from app.integrations.science.worker import default_vendor_dir
from app.integrations.supabase_storage import StorageNotFoundError, SupabaseStorage
from app.models import RunStatus, StripeAnalysis
from app.repositories import stripe_analyses as analysis_repo
from app.services import stripe_analyses as analysis_service

FIXTURE_IMG = Path(__file__).resolve().parents[1] / "fixtures" / "zebra1" / "flank_left_mid.png"
DEFAULT_CHECKPOINT = Path.home() / ".cache" / "stripecode" / "megadescriptor-l-384-33b3c6f4.bin"
SHARED_ROI = {"x": 64, "y": 64, "width": 384, "height": 384}


@pytest.fixture
def analyses_table(db):
    if not analysis_repo.table_exists(db):
        StripeAnalysis.__table__.create(bind=db.connection())
    yield


@pytest.fixture
def live_api_with_storage(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database.session import get_db
    from app.main import create_app

    storage = SupabaseStorage.from_settings()
    uploaded: list[str] = []
    real_upload = storage.upload

    def tracking_upload(path, content, content_type):
        uploaded.append(path)
        return real_upload(path, content, content_type)

    monkeypatch.setattr(storage, "upload", tracking_upload)
    monkeypatch.setattr(deps, "_storage", storage)
    app = create_app()

    def _test_db():
        yield db

    app.dependency_overrides[get_db] = _test_db
    yield TestClient(app, raise_server_exceptions=False), storage, uploaded
    if uploaded:
        storage.delete(uploaded)
    leftover = []
    for path in uploaded:
        try:
            storage.download(path)
            leftover.append(path)
        except StorageNotFoundError:
            pass
    assert leftover == [], f"Failed to clean up live Supabase objects: {leftover}"


def test_real_member1_and_member2_direct_on_same_image_and_roi(tmp_path: Path):
    """Run real analyze_stripes and safe_analyze on tests/fixtures/zebra1/flank_left_mid.png with same ROI."""
    import jsonschema
    import numpy as np

    vendor = default_vendor_dir()
    assert vendor.is_dir(), f"Missing vendored research tree at {vendor}"
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))

    from research.member1.models.api import analyze_stripes
    from research.member2.science import safe_analyze

    assert FIXTURE_IMG.is_file(), f"Missing fixture {FIXTURE_IMG}"
    rgb = np.ascontiguousarray(np.asarray(Image.open(FIXTURE_IMG).convert("RGB"), dtype=np.uint8))
    assert rgb.shape == (512, 512, 3)

    # Member 1: explicit mask matching SHARED_ROI
    mask = np.zeros((512, 512), dtype=np.uint8)
    mask[64 : 64 + 384, 64 : 64 + 384] = 255
    m1_dir = tmp_path / "m1"
    m1_dir.mkdir()
    m1_out = analyze_stripes(rgb, roi=mask, save_artifacts=True, artifacts_dir=str(m1_dir))

    assert m1_out["schema_version"] == "1.0.0"
    assert m1_out["segmentation_status"] in ("SUCCESS", "WARNING")
    assert m1_out["width_statistics"]["mean_px"] > 0
    assert m1_out["spacing_statistics"]["mean_px"] > 0
    for key in ("stripe_mask_reference", "orientation_map_reference", "width_map_reference", "visualization_reference"):
        p = m1_dir / m1_out[key]
        assert p.is_file() and p.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    # Member 2: exact same ROI box [64, 64, 384, 384]
    m2_dir = tmp_path / "m2_out"
    m2_env = safe_analyze(
        rgb,
        str(m2_dir),
        roi=[64, 64, 384, 384],
        filter_type="gaussian",
        cutoff_cpp=0.06,
        source_reference="zebra1/flank_left_mid.png",
    )
    assert m2_env["ok"] is True
    m2_res = m2_env["result"]
    assert m2_res["schema_version"] == "stripecode.science.v1"
    assert m2_res["frequency"]["cycles_per_pixel"] > 0
    assert m2_res["frequency"]["period_pixels"] > 0

    schema = json.loads((vendor / "research" / "member2" / "science" / "schema_v1.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=m2_env, schema=schema)

    for name in ("original_roi", "filtered", "intensity_mask", "orientation", "spectrum"):
        p = Path(m2_res["files"][name])
        assert p.is_file() and p.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.storage
def test_real_fastapi_combined_analyses_with_live_supabase_storage(live_api_with_storage, db, analyses_table):
    """Real upload -> POST /analyses/combined -> real spawned workers -> private PNG artifacts -> signed URLs."""
    api, storage, uploaded = live_api_with_storage

    caps = api.get("/api/v1/analyses/capabilities", params={"refresh": True}).json()
    assert caps["stripe_morphology"]["available"] is True
    assert caps["stripe_morphology"]["source_commit"] == MEMBER1_COMMIT
    assert caps["spatial_frequency"]["available"] is True
    assert caps["spatial_frequency"]["source_commit"] == MEMBER2_COMMIT

    fixture_bytes = FIXTURE_IMG.read_bytes()
    img = api.post(
        "/api/v1/images",
        data={"kind": "query"},
        files={"file": ("flank_left_mid.png", fixture_bytes, "image/png")},
    )
    assert img.status_code == 201, img.text
    img_id = img.json()["id"]

    comb = api.post(
        "/api/v1/analyses/combined",
        json={
            "image_id": img_id,
            "roi": SHARED_ROI,
            "morphology_config": {"clahe_clip_limit": 3.0},
            "frequency_options": {"filter_type": "gaussian", "cutoff_cpp": 0.06},
        },
    )
    assert comb.status_code == 202, comb.text
    m1_job_id = comb.json()["stripe_morphology"]["id"]
    m2_job_id = comb.json()["spatial_frequency"]["id"]

    settings = Settings()
    m1_done = analysis_service.execute_analysis_job(db, storage, settings, uuid.UUID(m1_job_id))
    m2_done = analysis_service.execute_analysis_job(db, storage, settings, uuid.UUID(m2_job_id))

    assert m1_done.status == RunStatus.COMPLETED, m1_done
    assert m1_done.artifacts == ["mask", "orientation", "width", "overlay"]
    assert m1_done.result["width_statistics"]["mean_px"] > 0

    assert m2_done.status == RunStatus.COMPLETED, m2_done
    assert m2_done.artifacts == ["original_roi", "filtered", "intensity_mask", "orientation", "spectrum"]
    assert m2_done.result["frequency"]["cycles_per_pixel"] > 0

    # Verify private artifact retrieval via short-lived signed URLs for both Member 1 and Member 2
    for job_id, artifact in ((m1_job_id, "overlay"), (m2_job_id, "spectrum")):
        signed = api.get(f"/api/v1/analyses/{job_id}/artifacts/{artifact}/url", params={"expires_in": 60})
        assert signed.status_code == 200, signed.text
        fetched = httpx.get(signed.json()["url"], timeout=30)
        assert fetched.status_code == 200
        assert fetched.content.startswith(b"\x89PNG\r\n\x1a\n")

    # Verify 1 source image + 4 M1 PNGs + 5 M2 PNGs = 10 private storage objects uploaded
    assert len(uploaded) == 10


@pytest.mark.storage
def test_real_megadescriptor_cpu_cached_gallery_verification_and_sighting(
    live_api_with_storage, monkeypatch, tmp_path: Path
):
    """Real MegaDescriptor-L-384 v1 CPU inference, cached gallery hit, human confirmation, and sighting history."""
    checkpoint = Path(os.environ.get("RECOGNITION_MODEL_PATH") or os.environ.get("STRIPECODE_MODEL_PATH") or DEFAULT_CHECKPOINT)
    if not checkpoint.is_file():
        pytest.skip(f"MegaDescriptor checkpoint not available at {checkpoint}")

    api, _, _ = live_api_with_storage
    cache_file = tmp_path / "gallery_cache.npz"
    cfg = Settings(
        recognition_model_path=str(checkpoint),
        recognition_gallery_cache_path=str(cache_file),
        recognition_preprocessing="model_card",
    )
    monkeypatch.setattr("app.api.v1.endpoints.identifications.get_settings", lambda: cfg)

    caps = api.get("/api/v1/identifications/capabilities").json()
    assert caps["available"] is True
    assert caps["model_name"] == "BVRA/MegaDescriptor-L-384"
    assert caps["device"] == "cpu"

    # Build 3 distinct real RGB PNGs derived from flank_left_mid.png (two distinct regions + one query crop)
    base = Image.open(FIXTURE_IMG).convert("RGB")
    import io

    def _crop_png(box):
        buf = io.BytesIO()
        base.crop(box).save(buf, format="PNG")
        return buf.getvalue()

    ref1_bytes = _crop_png((0, 0, 384, 384))
    ref2_bytes = _crop_png((128, 128, 512, 512))
    query_bytes = _crop_png((16, 16, 400, 400))

    z1 = api.post("/api/v1/zebras", json={"code": f"MD-A-{uuid.uuid4().hex[:6]}", "name": "Alpha"}).json()
    z2 = api.post("/api/v1/zebras", json={"code": f"MD-B-{uuid.uuid4().hex[:6]}", "name": "Beta"}).json()

    r_img1 = api.post("/api/v1/images", data={"kind": "reference"}, files={"file": ("ref1.png", ref1_bytes, "image/png")}).json()
    r_img2 = api.post("/api/v1/images", data={"kind": "reference"}, files={"file": ("ref2.png", ref2_bytes, "image/png")}).json()
    q_img = api.post("/api/v1/images", data={"kind": "query"}, files={"file": ("query.png", query_bytes, "image/png")}).json()

    assert api.post(f"/api/v1/zebras/{z1['id']}/gallery", json={"image_asset_id": r_img1["id"]}).status_code == 201
    assert api.post(f"/api/v1/zebras/{z2['id']}/gallery", json={"image_asset_id": r_img2["id"]}).status_code == 201

    # Run 1 (cold gallery cache -> 2 cache misses, writes NPZ cache)
    run1_resp = api.post(
        "/api/v1/identifications",
        json={"query_image_id": q_img["id"], "top_k": 5, "requested_by": "agent1-test"},
    )
    assert run1_resp.status_code == 201, run1_resp.text
    run1 = run1_resp.json()
    assert run1["status"] == "completed"
    assert run1["predicted_unknown"] is None
    assert len(run1["candidates"]) == 2
    assert run1["processing_metadata"]["gallery_cache_misses"] == 2
    assert run1["processing_metadata"]["gallery_cache_hits"] == 0
    assert run1["processing_metadata"]["inference_seconds"] > 0
    assert run1["processing_metadata"]["rss_mb"] is not None
    assert cache_file.is_file()

    # Run 2 (warm gallery cache -> 2 cache hits, 0 misses)
    run2_resp = api.post(
        "/api/v1/identifications",
        json={"query_image_id": q_img["id"], "top_k": 5, "requested_by": "agent1-test"},
    )
    assert run2_resp.status_code == 201, run2_resp.text
    run2 = run2_resp.json()
    assert run2["processing_metadata"]["gallery_cache_hits"] == 2
    assert run2["processing_metadata"]["gallery_cache_misses"] == 0
    assert run2["candidates"][0]["similarity_score"] == pytest.approx(run1["candidates"][0]["similarity_score"], abs=1e-5)

    # Human confirmation on top candidate
    top_cand = run2["candidates"][0]
    ver = api.post(
        f"/api/v1/identifications/{run2['id']}/verifications",
        json={
            "decision": "confirmed",
            "candidate_id": top_cand["id"],
            "verified_by": "researcher-1",
            "notes": "Confirmed during Agent 1 end-to-end verification",
        },
    )
    assert ver.status_code == 201, ver.text
    assert ver.json()["decision"] == "confirmed"
    assert ver.json()["zebra_id"] == top_cand["zebra_id"]

    # Create sighting linked to confirmed zebra + query image + run, then verify sighting history
    sighting = api.post(
        "/api/v1/sightings",
        json={
            "zebra_id": top_cand["zebra_id"],
            "image_asset_id": q_img["id"],
            "identification_run_id": run2["id"],
            "observed_at": "2026-11-21T14:30:00Z",
            "location_name": "Verification Transect A",
            "observer": "researcher-1",
            "notes": "Verified left-flank sighting",
        },
    )
    assert sighting.status_code == 201, sighting.text
    s_id = sighting.json()["id"]

    history = api.get("/api/v1/sightings", params={"zebra_id": top_cand["zebra_id"]})
    assert history.status_code == 200
    assert any(item["id"] == s_id for item in history.json()["items"])
