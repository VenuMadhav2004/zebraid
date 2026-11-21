"""
Public Stripe Morphology API for STRIPECODE AI (Member 1).

Delivers the standardized entry point:
    analyze_stripes(image, roi=None, config=None) -> Dict[str, Any]

Compliant with Member 2 (surface processing) and Member 3 / Venu (React/FastAPI)
handoff requirements.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np

from research.member1.models.segmentation import StripeSegmenter, SegmentationResult
from research.member1.models.morphology import StripeMorphologyAnalyzer, MorphologyResult


SCHEMA_VERSION = "1.0.0"
DEFAULT_OUTPUT_DIR = os.environ.get("STRIPECODE_ARTIFACTS_DIR", "research/member1/results/api_artifacts")


def analyze_stripes(
    image: Union[np.ndarray, str],
    roi: Optional[Union[np.ndarray, str]] = None,
    config: Optional[Dict[str, Any]] = None,
    save_artifacts: bool = True,
    artifacts_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Standardized, production-ready Python entry point for zebra stripe morphology analysis.

    Args:
        image: RGB numpy array (H, W, 3) uint8 or file path to an image.
        roi: Optional binary ROI mask (H, W) uint8 or file path to a mask image.
        config: Optional configuration dictionary overrides.
        save_artifacts: Whether to save generated masks/maps as external PNG files.
        artifacts_dir: Directory where image artifact files should be saved.

    Returns:
        Structured JSON-serializable dictionary adhering to STRIPECODE AI schema v1.0.0.
    """
    t0 = time.perf_counter()
    warnings: List[str] = []

    # 1. Image loading and validation
    try:
        if isinstance(image, str):
            if not os.path.exists(image):
                return {
                    "schema_version": SCHEMA_VERSION,
                    "status": "FAILED",
                    "segmentation_status": "FAILED",
                    "error_message": f"Input image path does not exist: {image}",
                    "processing_time_seconds": round(time.perf_counter() - t0, 4)
                }
            img_bgr = cv2.imread(image)
            if img_bgr is None:
                return {
                    "schema_version": SCHEMA_VERSION,
                    "status": "FAILED",
                    "segmentation_status": "FAILED",
                    "error_message": f"Failed to decode image from path: {image}",
                    "processing_time_seconds": round(time.perf_counter() - t0, 4)
                }
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            input_source = os.path.basename(image)
        elif isinstance(image, np.ndarray):
            if image.size == 0 or len(image.shape) < 2:
                return {
                    "schema_version": SCHEMA_VERSION,
                    "status": "FAILED",
                    "segmentation_status": "FAILED",
                    "error_message": "Input image array is empty or has invalid shape",
                    "processing_time_seconds": round(time.perf_counter() - t0, 4)
                }
            if len(image.shape) == 2:
                img_rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            else:
                img_rgb = image.copy()
            input_source = "numpy_array"
        else:
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "FAILED",
                "segmentation_status": "FAILED",
                "error_message": f"Unsupported image input type: {type(image)}. Expected np.ndarray or str path.",
                "processing_time_seconds": round(time.perf_counter() - t0, 4)
            }
    except Exception as e:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "FAILED",
            "segmentation_status": "FAILED",
            "error_message": f"Invalid image input: {str(e)}",
            "processing_time_seconds": round(time.perf_counter() - t0, 4)
        }

    H, W = img_rgb.shape[:2]

    # Compute fast hash of input image content for tracking
    img_hash = hashlib.sha256(img_rgb.tobytes()[:65536]).hexdigest()[:16]

    # 2. ROI loading and validation
    roi_mask: Optional[np.ndarray] = None
    if roi is not None:
        if isinstance(roi, str):
            if os.path.exists(roi):
                r_img = cv2.imread(roi, cv2.IMREAD_GRAYSCALE)
                if r_img is not None:
                    roi_mask = cv2.resize(r_img, (W, H), interpolation=cv2.INTER_NEAREST)
        elif isinstance(roi, np.ndarray):
            if roi.shape[:2] != (H, W):
                roi_mask = cv2.resize(roi.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST)
            else:
                roi_mask = (roi > 0).astype(np.uint8) * 255
        elif isinstance(roi, dict):
            # Support frontend bounding box in pixel coordinates:
            # {"x": ..., "y": ..., "width": ..., "height": ...}
            # or {"xmin": ..., "ymin": ..., "xmax": ..., "ymax": ...}
            mask = np.zeros((H, W), dtype=np.uint8)
            if "x" in roi and "y" in roi and "width" in roi and "height" in roi:
                rx, ry, rw, rh = int(roi["x"]), int(roi["y"]), int(roi["width"]), int(roi["height"])
                mask[max(0, ry):min(H, ry + rh), max(0, rx):min(W, rx + rw)] = 255
                roi_mask = mask
            elif "xmin" in roi and "ymin" in roi and "xmax" in roi and "ymax" in roi:
                rx0, ry0, rx1, ry1 = int(roi["xmin"]), int(roi["ymin"]), int(roi["xmax"]), int(roi["ymax"])
                mask[max(0, ry0):min(H, ry1), max(0, rx0):min(W, rx1)] = 255
                roi_mask = mask
        elif isinstance(roi, (list, tuple)) and len(roi) == 4:
            # [x, y, width, height] format
            rx, ry, rw, rh = int(roi[0]), int(roi[1]), int(roi[2]), int(roi[3])
            mask = np.zeros((H, W), dtype=np.uint8)
            mask[max(0, ry):min(H, ry + rh), max(0, rx):min(W, rx + rw)] = 255
            roi_mask = mask

    # 3. Apply configurations
    cfg = config or {}
    clahe_clip = cfg.get("clahe_clip_limit", 3.0)
    adaptive_block = cfg.get("adaptive_block_size", 51)
    min_stripe_area = cfg.get("min_stripe_area", 40)
    orientation_sigma = cfg.get("orientation_sigma", 3.0)
    min_branch_len = cfg.get("min_branch_length", 15)

    segmenter = StripeSegmenter(
        clahe_clip_limit=clahe_clip,
        adaptive_block_size=adaptive_block,
        min_stripe_area=min_stripe_area
    )
    analyzer = StripeMorphologyAnalyzer(
        orientation_sigma=orientation_sigma,
        min_branch_length=min_branch_len
    )

    # 4. Execute Segmentation
    try:
        seg_res: SegmentationResult = segmenter.segment(img_rgb, roi_mask)
        warnings.extend(seg_res.warnings)
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "FAILED",
            "error_message": f"Segmentation pipeline failed: {str(e)}",
            "processing_time_seconds": round(elapsed, 4)
        }

    # 5. Execute Morphology Analysis
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    try:
        morph_res: MorphologyResult = analyzer.analyze(gray, seg_res.stripe_mask, seg_res.roi_mask)
        warnings.extend(morph_res.warnings)
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "FAILED",
            "error_message": f"Morphology analysis pipeline failed: {str(e)}",
            "processing_time_seconds": round(elapsed, 4)
        }

    # 6. Save external image artifacts (to avoid embedding large binary buffers in JSON)
    out_dir = artifacts_dir or DEFAULT_OUTPUT_DIR
    mask_ref = None
    orientation_ref = None
    width_ref = None
    vis_ref = None

    if save_artifacts:
        os.makedirs(out_dir, exist_ok=True)
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        prefix = f"stripe_{img_hash}_{timestamp_str}"

        mask_path = os.path.join(out_dir, f"{prefix}_mask.png")
        cv2.imwrite(mask_path, seg_res.stripe_mask)
        mask_ref = os.path.basename(mask_path)

        # Colorized orientation map (HSV color wheel: Hue = angle 0..180, Sat = Coherence, Val = 255)
        hsv_map = np.zeros((H, W, 3), dtype=np.uint8)
        hsv_map[..., 0] = np.clip(morph_res.orientation_map, 0, 179).astype(np.uint8)
        hsv_map[..., 1] = np.clip(morph_res.coherence_map * 255.0, 0, 255).astype(np.uint8)
        hsv_map[..., 2] = np.where(seg_res.roi_mask > 0, 255, 0).astype(np.uint8)
        bgr_orient = cv2.cvtColor(hsv_map, cv2.COLOR_HSV2BGR)
        orient_path = os.path.join(out_dir, f"{prefix}_orientation.png")
        cv2.imwrite(orient_path, bgr_orient)
        orientation_ref = os.path.basename(orient_path)

        # Colorized width map (normalized to 0..255 colormap)
        max_w = max(morph_res.width_stats["max_width"], 1.0)
        norm_w = np.clip(morph_res.width_map / max_w * 255.0, 0, 255).astype(np.uint8)
        color_w = cv2.applyColorMap(norm_w, cv2.COLORMAP_TURBO)
        color_w[morph_res.width_map == 0] = 0
        width_path = os.path.join(out_dir, f"{prefix}_width.png")
        cv2.imwrite(width_path, color_w)
        width_ref = os.path.basename(width_path)

        vis_path = os.path.join(out_dir, f"{prefix}_overlay.png")
        cv2.imwrite(vis_path, cv2.cvtColor(seg_res.visualization, cv2.COLOR_RGB2BGR))
        vis_ref = os.path.basename(vis_path)

    # Determine status
    if len(warnings) > 0:
        status = "WARNING"
    else:
        status = "SUCCESS"

    elapsed = time.perf_counter() - t0

    response = {
        "schema_version": SCHEMA_VERSION,
        "input_and_region_metadata": {
            "source_id": input_source,
            "content_hash": img_hash,
            "image_dimensions": {"width": W, "height": H},
            "valid_roi_pixels": morph_res.pattern_stats["total_analyzed_pixels"],
            "roi_coverage_ratio": round(morph_res.pattern_stats["total_analyzed_pixels"] / (W * H), 4)
        },
        "segmentation_status": status,
        "quality_metrics": {
            "contrast_ratio": round(seg_res.quality_metrics["contrast_ratio"], 4),
            "edge_sharpness": round(seg_res.quality_metrics["edge_sharpness"], 2),
            "confidence_score": round(seg_res.quality_metrics["confidence_score"], 4)
        },
        "stripe_mask_reference": mask_ref,
        "orientation_map_reference": orientation_ref,
        "width_map_reference": width_ref,
        "visualization_reference": vis_ref,
        "width_statistics": {
            "mean_px": round(morph_res.width_stats["mean_width"], 2),
            "median_px": round(morph_res.width_stats["median_width"], 2),
            "std_px": round(morph_res.width_stats["std_width"], 2),
            "min_px": round(morph_res.width_stats["min_width"], 2),
            "max_px": round(morph_res.width_stats["max_width"], 2),
            "p10_px": round(morph_res.width_stats["p10_width"], 2),
            "p90_px": round(morph_res.width_stats["p90_width"], 2),
            "sample_count": morph_res.width_stats["sample_count"]
        },
        "spacing_statistics": {
            "mean_px": round(morph_res.spacing_stats["mean_spacing"], 2),
            "median_px": round(morph_res.spacing_stats["median_spacing"], 2),
            "std_px": round(morph_res.spacing_stats["std_spacing"], 2),
            "min_px": round(morph_res.spacing_stats["min_spacing"], 2),
            "max_px": round(morph_res.spacing_stats["max_spacing"], 2),
            "p10_px": round(morph_res.spacing_stats["p10_spacing"], 2),
            "p90_px": round(morph_res.spacing_stats["p90_spacing"], 2),
            "sample_count": morph_res.spacing_stats["sample_count"]
        },
        "orientation_statistics": {
            "dominant_angle_deg": round(morph_res.orientation_stats["dominant_orientation_deg"], 2),
            "mean_angle_deg": round(morph_res.orientation_stats["mean_orientation_deg"], 2),
            "circular_variance": round(morph_res.orientation_stats["circular_variance"], 4),
            "mean_coherence": round(morph_res.orientation_stats["mean_coherence"], 4),
            "orientation_entropy": round(morph_res.orientation_stats["orientation_entropy"], 4),
            "angular_convention": "axial_0_to_180_deg"
        },
        "curvature_statistics": {
            "mean_curvature": round(morph_res.curvature_stats["mean_curvature"], 4),
            "median_curvature": round(morph_res.curvature_stats["median_curvature"], 4),
            "std_curvature": round(morph_res.curvature_stats["std_curvature"], 4),
            "p90_curvature": round(morph_res.curvature_stats["p90_curvature"], 4),
            "curvature_unit": "inverse_pixels"
        },
        "branching_statistics": {
            "junction_count": morph_res.branching_stats["junction_count"],
            "endpoint_count": morph_res.branching_stats["endpoint_count"],
            "branch_count": morph_res.branching_stats["branch_count"],
            "junction_density_per_kpx": round(morph_res.branching_stats["junction_density_per_kpx"], 4)
        },
        "stripe_density": {
            "black_stripe_fraction": round(morph_res.pattern_stats["black_stripe_area_fraction"], 4),
            "width_to_spacing_ratio": round(morph_res.pattern_stats["width_to_spacing_ratio"], 4)
        },
        "measurement_units": {
            "spatial": "pixels (calibrated physical dimensions pending scale confirmation)",
            "angular": "degrees in [0, 180) axial convention",
            "curvature": "1 / pixels",
            "density": "dimensionless ratio in [0, 1]"
        },
        "warnings": warnings,
        "processing_time_seconds": round(elapsed, 4)
    }

    return response
