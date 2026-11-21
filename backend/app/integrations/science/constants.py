"""Pinned provenance constants and artifact specs for Member 1 and Member 2 modules."""
from __future__ import annotations

MEMBER1_COMMIT = "871e2956a3cda8d3fb08433a8450a3718e9e312f"
MEMBER1_FUNCTION = "research.member1.models.api.analyze_stripes"
MEMBER1_SCHEMA_VERSION = "1.0.0"
MEMBER1_ARTIFACTS: tuple[str, ...] = ("mask", "orientation", "width", "overlay")
MEMBER1_REF_FIELDS: dict[str, str] = {
    "stripe_mask_reference": "mask",
    "orientation_map_reference": "orientation",
    "width_map_reference": "width",
    "visualization_reference": "overlay",
}
MEMBER1_CONFIG_DEFAULTS: dict[str, int | float] = {
    "clahe_clip_limit": 3.0,
    "adaptive_block_size": 51,
    "min_stripe_area": 40,
    "orientation_sigma": 3.0,
    "min_branch_length": 15,
}

MEMBER2_COMMIT = "ff827ba826f4fa8e34acf3ba41528f91a0252c1e"
MEMBER2_FUNCTION = "research.member2.science.safe_analyze"
MEMBER2_SCHEMA_VERSION = "stripecode.science.v1"
MEMBER2_ARTIFACTS: tuple[str, ...] = ("original_roi", "filtered", "intensity_mask", "orientation", "spectrum")
MEMBER2_SAFE_ERROR_TYPES: frozenset[str] = frozenset({"ValueError", "TypeError"})

MIN_ROI_SIDE = 16
