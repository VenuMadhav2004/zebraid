"""
Partial-Hide Morphology Stability Evaluator for STRIPECODE AI (Member 1).

Investigates descriptor stability and measurement uncertainty across:
- Full selected region
- Left partial crop (50% horizontal width)
- Right partial crop (50% horizontal width)
- Central partial crop (50% area)
- Occluded region (simulated 30% vegetation / obstruction patch)

Measures descriptor changes (delta and percent shift) in width, spacing,
orientation, curvature, and density to quantify real-world robustness.
"""

from dataclasses import dataclass, field
import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from research.member1.models.segmentation import StripeSegmenter
from research.member1.models.morphology import StripeMorphologyAnalyzer, MorphologyResult


@dataclass
class PartialCropResult:
    variant: str
    valid_area_px: int
    stripe_coverage: float
    mean_width: float
    median_width: float
    mean_spacing: float
    median_spacing: float
    dominant_orientation_deg: float
    orientation_coherence: float
    mean_curvature: float
    junction_density: float
    delta_vs_full: Dict[str, float]
    warnings: List[str]


class PartialHideEvaluator:
    """Evaluates stripe descriptor stability under partial visibility and occlusion."""

    def __init__(
        self,
        segmenter: Optional[StripeSegmenter] = None,
        analyzer: Optional[StripeMorphologyAnalyzer] = None
    ):
        self.segmenter = segmenter or StripeSegmenter()
        self.analyzer = analyzer or StripeMorphologyAnalyzer()

    def generate_variants(
        self,
        image_rgb: np.ndarray,
        base_roi: Optional[np.ndarray] = None
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """
        Generates 5 region visibility variants:
        1. full: original full region
        2. left_50: left half crop
        3. right_50: right half crop
        4. center_50: central 50% area crop
        5. occluded_30: synthetic 30% diagonal occlusion bar simulating vegetation
        """
        H, W = image_rgb.shape[:2]
        if base_roi is None:
            base_roi = np.ones((H, W), dtype=np.uint8) * 255

        variants = {}

        # 1. Full
        variants["full"] = (image_rgb.copy(), base_roi.copy())

        # 2. Left 50%
        roi_left = base_roi.copy()
        roi_left[:, W // 2:] = 0
        img_left = image_rgb.copy()
        img_left[:, W // 2:] = 0
        variants["left_50"] = (img_left, roi_left)

        # 3. Right 50%
        roi_right = base_roi.copy()
        roi_right[:, :W // 2] = 0
        img_right = image_rgb.copy()
        img_right[:, :W // 2] = 0
        variants["right_50"] = (img_right, roi_right)

        # 4. Center 50% area
        # Box centered with 1/sqrt(2) = 0.707 dimensions (area = 0.50)
        margin_y = int(round(H * (1.0 - 0.707) / 2.0))
        margin_x = int(round(W * (1.0 - 0.707) / 2.0))
        roi_center = np.zeros_like(base_roi)
        roi_center[margin_y:H - margin_y, margin_x:W - margin_x] = base_roi[margin_y:H - margin_y, margin_x:W - margin_x]
        img_center = image_rgb.copy()
        img_center[roi_center == 0] = 0
        variants["center_50"] = (img_center, roi_center)

        # 5. Occluded 30% (diagonal simulated branch/leaf occlusion)
        img_occ = image_rgb.copy()
        roi_occ = base_roi.copy()
        occ_mask = np.zeros((H, W), dtype=np.uint8)
        # Draw thick diagonal bar across middle third
        pt1 = (int(W * 0.1), int(H * 0.2))
        pt2 = (int(W * 0.9), int(H * 0.8))
        thickness = int(round(min(H, W) * 0.35))
        cv2.line(occ_mask, pt1, pt2, 255, thickness)
        
        # Apply occlusion (darken pixels and mask out of ROI)
        img_occ[occ_mask > 0] = (img_occ[occ_mask > 0] * 0.15).astype(np.uint8)
        roi_occ[occ_mask > 0] = 0
        variants["occluded_30"] = (img_occ, roi_occ)

        return variants

    def evaluate(
        self,
        image_rgb: np.ndarray,
        base_roi: Optional[np.ndarray] = None
    ) -> Dict[str, PartialCropResult]:
        """Runs segmentation and morphology on all 5 variants and computes relative shifts."""
        variants = self.generate_variants(image_rgb, base_roi)
        results: Dict[str, PartialCropResult] = {}
        raw_morph: Dict[str, MorphologyResult] = {}

        # First run full baseline
        img_full, roi_full = variants["full"]
        seg_full = self.segmenter.segment(img_full, roi_full)
        gray_full = cv2.cvtColor(img_full, cv2.COLOR_RGB2GRAY)
        morph_full = self.analyzer.analyze(gray_full, seg_full.stripe_mask, seg_full.roi_mask)
        raw_morph["full"] = morph_full

        full_valid_px = int((seg_full.roi_mask > 0).sum())
        base_vals = {
            "mean_width": morph_full.width_stats["mean_width"],
            "median_width": morph_full.width_stats["median_width"],
            "mean_spacing": morph_full.spacing_stats["mean_spacing"],
            "median_spacing": morph_full.spacing_stats["median_spacing"],
            "dominant_orientation_deg": morph_full.orientation_stats["dominant_orientation_deg"],
            "orientation_coherence": morph_full.orientation_stats["mean_coherence"],
            "mean_curvature": morph_full.curvature_stats["mean_curvature"],
            "junction_density": morph_full.branching_stats["junction_density_per_kpx"],
            "stripe_coverage": morph_full.pattern_stats["black_stripe_area_fraction"]
        }

        results["full"] = PartialCropResult(
            variant="full",
            valid_area_px=full_valid_px,
            stripe_coverage=base_vals["stripe_coverage"],
            mean_width=base_vals["mean_width"],
            median_width=base_vals["median_width"],
            mean_spacing=base_vals["mean_spacing"],
            median_spacing=base_vals["median_spacing"],
            dominant_orientation_deg=base_vals["dominant_orientation_deg"],
            orientation_coherence=base_vals["orientation_coherence"],
            mean_curvature=base_vals["mean_curvature"],
            junction_density=base_vals["junction_density"],
            delta_vs_full={k: 0.0 for k in base_vals},
            warnings=seg_full.warnings + morph_full.warnings
        )

        # Run remaining variants
        for vname in ["left_50", "right_50", "center_50", "occluded_30"]:
            img_v, roi_v = variants[vname]
            seg_v = self.segmenter.segment(img_v, roi_v)
            gray_v = cv2.cvtColor(img_v, cv2.COLOR_RGB2GRAY)
            morph_v = self.analyzer.analyze(gray_v, seg_v.stripe_mask, seg_v.roi_mask)
            raw_morph[vname] = morph_v

            v_valid_px = int((seg_v.roi_mask > 0).sum())
            curr_vals = {
                "mean_width": morph_v.width_stats["mean_width"],
                "median_width": morph_v.width_stats["median_width"],
                "mean_spacing": morph_v.spacing_stats["mean_spacing"],
                "median_spacing": morph_v.spacing_stats["median_spacing"],
                "dominant_orientation_deg": morph_v.orientation_stats["dominant_orientation_deg"],
                "orientation_coherence": morph_v.orientation_stats["mean_coherence"],
                "mean_curvature": morph_v.curvature_stats["mean_curvature"],
                "junction_density": morph_v.branching_stats["junction_density_per_kpx"],
                "stripe_coverage": morph_v.pattern_stats["black_stripe_area_fraction"]
            }

            # Calculate relative shift: (curr - base) / base
            deltas = {}
            for k, val in curr_vals.items():
                ref = base_vals[k]
                if k == "dominant_orientation_deg":
                    # Circular angular difference wrapped to [-90, 90]
                    diff = (val - ref + 90.0) % 180.0 - 90.0
                    deltas[k] = float(diff)
                else:
                    rel = (val - ref) / max(abs(ref), 1e-4)
                    deltas[k] = float(rel)

            results[vname] = PartialCropResult(
                variant=vname,
                valid_area_px=v_valid_px,
                stripe_coverage=curr_vals["stripe_coverage"],
                mean_width=curr_vals["mean_width"],
                median_width=curr_vals["median_width"],
                mean_spacing=curr_vals["mean_spacing"],
                median_spacing=curr_vals["median_spacing"],
                dominant_orientation_deg=curr_vals["dominant_orientation_deg"],
                orientation_coherence=curr_vals["orientation_coherence"],
                mean_curvature=curr_vals["mean_curvature"],
                junction_density=curr_vals["junction_density"],
                delta_vs_full=deltas,
                warnings=seg_v.warnings + morph_v.warnings
            )

        return results
