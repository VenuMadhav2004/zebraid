"""Unit tests for scientific analysis contracts, ROI conversion, sanitization, and vendoring guards."""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import ExifTags, Image
from pydantic import ValidationError

from app.integrations.science import (
    MEMBER1_COMMIT,
    MEMBER2_COMMIT,
    AnalysisLimitError,
    AnalysisValidationError,
    decode_canonical_rgb,
    probe_capabilities,
    sanitize_error_message,
    sanitize_member1_result,
    sanitize_member2_result,
    validate_and_resolve_roi,
)
from app.integrations.science.decode import roi_to_member1_mask, roi_to_member2_box
from app.schemas import FrequencyOptions, MorphologyConfig


def test_morphology_config_validation():
    cfg = MorphologyConfig(clahe_clip_limit=2.5, adaptive_block_size=41, min_stripe_area=30, orientation_sigma=2.0, min_branch_length=10)
    assert cfg.model_dump(exclude_none=True)["clahe_clip_limit"] == 2.5

    with pytest.raises(ValidationError):
        MorphologyConfig(unknown_key=1)
    with pytest.raises(ValidationError):
        MorphologyConfig(clahe_clip_limit=float("nan"))
    with pytest.raises(ValidationError):
        MorphologyConfig(clahe_clip_limit=-1.0)
    with pytest.raises(ValidationError):
        MorphologyConfig(adaptive_block_size=2)


def test_frequency_options_validation_and_bandpass_order():
    default = FrequencyOptions()
    assert default.filter_type == "gaussian" and default.cutoff_cpp == 0.06

    bp = FrequencyOptions(filter_type="bandpass", cutoff_cpp=0.12, band_low_cpp=0.03)
    assert bp.band_low_cpp < bp.cutoff_cpp

    with pytest.raises(ValidationError):
        FrequencyOptions(filter_type="bandpass", cutoff_cpp=0.05, band_low_cpp=0.05)
    with pytest.raises(ValidationError):
        FrequencyOptions(filter_type="bandpass", cutoff_cpp=0.05, band_low_cpp=0.08)
    with pytest.raises(ValidationError):
        FrequencyOptions(cutoff_cpp=0.6)
    with pytest.raises(ValidationError):
        FrequencyOptions(extra_field=1)


def test_roi_resolution_modes_and_pixel_limits():
    # Member 1 with roi=None -> auto mode, full-image box
    roi, mode = validate_and_resolve_roi(None, 800, 600, kind="stripe_morphology")
    assert roi == {"x": 0, "y": 0, "width": 800, "height": 600}
    assert mode == "auto"

    # Member 1 with explicit roi -> mask mode
    roi, mode = validate_and_resolve_roi({"x": 10, "y": 20, "width": 200, "height": 100}, 800, 600, kind="stripe_morphology")
    assert roi == {"x": 10, "y": 20, "width": 200, "height": 100}
    assert mode == "mask"

    # Member 2 always box mode
    roi, mode = validate_and_resolve_roi({"x": 5, "y": 5, "width": 64, "height": 64}, 800, 600, kind="spatial_frequency")
    assert mode == "box"
    assert roi_to_member2_box(roi) == [5, 5, 64, 64]

    # Too small (<16x16)
    with pytest.raises(AnalysisValidationError):
        validate_and_resolve_roi({"x": 0, "y": 0, "width": 15, "height": 64}, 800, 600, kind="spatial_frequency")

    # Outside bounds
    with pytest.raises(AnalysisValidationError):
        validate_and_resolve_roi({"x": 750, "y": 0, "width": 100, "height": 64}, 800, 600, kind="stripe_morphology")

    # 3000x2000 = 6 MP: Member 1 rejects (analyses whole image > 4 MP), Member 2 accepts a 500x500 ROI!
    with pytest.raises(AnalysisLimitError):
        validate_and_resolve_roi({"x": 0, "y": 0, "width": 500, "height": 500}, 3000, 2000, kind="stripe_morphology")
    roi_m2, mode_m2 = validate_and_resolve_roi({"x": 0, "y": 0, "width": 500, "height": 500}, 3000, 2000, kind="spatial_frequency")
    assert roi_m2["width"] == 500 and mode_m2 == "box"

    # > 8192 px side rejected as source limit
    with pytest.raises(AnalysisLimitError):
        validate_and_resolve_roi({"x": 0, "y": 0, "width": 64, "height": 64}, 9000, 500, kind="spatial_frequency")


def test_sanitize_member1_and_member2_strips_local_paths(tmp_path: Path):
    for fname in (
        "stripe_abc_mask.png",
        "stripe_abc_orientation.png",
        "stripe_abc_width.png",
        "stripe_abc_overlay.png",
    ):
        (tmp_path / fname).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    raw_m1 = {
        "schema_version": "1.0.0",
        "segmentation_status": "SUCCESS",
        "stripe_mask_reference": str(tmp_path / "stripe_abc_mask.png"),
        "orientation_map_reference": "stripe_abc_orientation.png",
        "width_map_reference": "stripe_abc_width.png",
        "visualization_reference": "stripe_abc_overlay.png",
        "width_statistics": {"mean_px": 14.2},
    }
    clean_m1, files_m1 = sanitize_member1_result(raw_m1, tmp_path)
    assert list(files_m1.keys()) == ["mask", "orientation", "width", "overlay"]
    assert clean_m1["stripe_mask_reference"] == "mask"
    assert clean_m1["visualization_reference"] == "overlay"
    assert str(tmp_path) not in json.dumps(clean_m1)

    m2_dir = tmp_path / "m2"
    m2_dir.mkdir()
    for fname in ("original_roi.png", "filtered.png", "intensity_mask.png", "orientation.png", "spectrum.png"):
        (m2_dir / fname).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    (m2_dir / "analysis.json").write_text("{}", encoding="utf-8")

    raw_m2 = {
        "schema_version": "stripecode.science.v1",
        "source_reference": "img-123",
        "files": {
            "original_roi": str(m2_dir / "original_roi.png"),
            "filtered": str(m2_dir / "filtered.png"),
            "intensity_mask": str(m2_dir / "intensity_mask.png"),
            "orientation": str(m2_dir / "orientation.png"),
            "spectrum": str(m2_dir / "spectrum.png"),
        },
        "frequency": {"cycles_per_pixel": 0.08},
    }
    clean_m2, files_m2 = sanitize_member2_result(raw_m2, m2_dir)
    assert list(files_m2.keys()) == ["original_roi", "filtered", "intensity_mask", "orientation", "spectrum"]
    assert clean_m2["files"] == {k: k for k in files_m2}
    assert "analysis.json" not in json.dumps(clean_m2)
    assert str(m2_dir) not in json.dumps(clean_m2)


def test_sanitize_error_message_never_leaks_paths():
    assert sanitize_error_message("ValueError", "ROI must fit image and be at least 16x16") == "ROI must fit image and be at least 16x16"
    assert "/tmp" not in sanitize_error_message("ValueError", "cannot read /tmp/secret/file.png")
    assert "/tmp" not in sanitize_error_message("OSError", "[Errno 17] File exists: '/tmp/sf-123/m2_out'")
    assert "/tmp" not in sanitize_error_message("analysis_failed", "Input image path does not exist: /tmp/x.png")


def _research_modules() -> set[str]:
    return {m for m in sys.modules if m == "research" or m.startswith(("research.", "member1_dhanushya", "member2_nisan"))}


def test_probe_capabilities_missing_vendor_dir(tmp_path: Path):
    # Other tests (real-pipeline integration) may import research modules into this pytest
    # process; what matters is that probing itself imports none.
    before = _research_modules()
    caps = probe_capabilities(tmp_path / "does_not_exist")
    assert caps["stripe_morphology"]["available"] is False
    assert caps["stripe_morphology"]["source_commit"] == MEMBER1_COMMIT
    assert caps["spatial_frequency"]["available"] is False
    assert caps["spatial_frequency"]["source_commit"] == MEMBER2_COMMIT
    assert _research_modules() == before


def test_probe_capabilities_with_vendored_tree_imports_no_research_modules():
    before = _research_modules()
    caps = probe_capabilities(None)  # default backend/third_party/stripecode
    assert set(caps) == {"stripe_morphology", "spatial_frequency"}
    assert _research_modules() == before


def test_vendor_script_refuses_without_approve():
    script = Path(__file__).resolve().parents[2] / "scripts" / "vendor_stripecode.py"
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=False)
    assert proc.returncode == 2
    assert "--approve" in proc.stderr


def test_decode_canonical_rgb_applies_exif_and_preserves_pixels():
    np = pytest.importorskip("numpy")

    im = Image.new("RGBA", (80, 40), (10, 200, 50, 128))
    exif = Image.Exif()
    exif[int(ExifTags.Base.Orientation)] = 6  # 90 deg rotation -> 40x80
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", exif=exif.tobytes())
    arr = decode_canonical_rgb(buf.getvalue())
    assert arr.shape == (80, 40, 3)  # (H=80, W=40, C=3)
    assert arr.dtype == np.uint8
    assert arr.flags["C_CONTIGUOUS"]

    # RGBA PNG discards alpha without resizing
    buf_rgba = io.BytesIO()
    im.save(buf_rgba, format="PNG")
    arr_rgba = decode_canonical_rgb(buf_rgba.getvalue())
    assert arr_rgba.shape == (40, 80, 3)

    # Member 1 ROI mask
    mask = roi_to_member1_mask({"x": 5, "y": 4, "width": 20, "height": 10}, "mask", 40, 80)
    assert mask.shape == (40, 80) and int((mask == 255).sum()) == 200
    assert roi_to_member1_mask({"x": 0, "y": 0, "width": 80, "height": 40}, "auto", 40, 80) is None
