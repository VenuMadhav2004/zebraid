"""
Stripe Segmentation Pipeline for STRIPECODE AI (Member 1).

Extracts clean, binary black-and-white stripe masks from RGB zebra images
with illumination normalization, adaptive thresholding, morphological cleanup,
and automated quality assessment.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class SegmentationResult:
    """Structured output of stripe segmentation."""
    stripe_mask: np.ndarray       # Binary uint8: 255 for black stripes, 0 for white background
    roi_mask: np.ndarray          # Binary uint8: 255 for valid analysis region, 0 for excluded background
    visualization: np.ndarray     # RGB visualization overlay
    quality_metrics: Dict[str, float]
    warnings: List[str]
    parameters: Dict[str, Any] = field(default_factory=dict)


class StripeSegmenter:
    """Robust, documented pipeline for black-and-white zebra stripe segmentation."""

    def __init__(
        self,
        clahe_clip_limit: float = 3.0,
        clahe_tile_grid_size: Tuple[int, int] = (8, 8),
        bg_blur_sigma: float = 25.0,
        adaptive_block_size: int = 51,
        adaptive_c: int = 4,
        min_stripe_area: int = 40,
        min_inter_stripe_area: int = 30,
        density_bounds: Tuple[float, float] = (0.15, 0.80),
        min_contrast_ratio: float = 0.30
    ):
        self.clahe_clip_limit = clahe_clip_limit
        self.clahe_tile_grid_size = clahe_tile_grid_size
        self.bg_blur_sigma = bg_blur_sigma
        self.adaptive_block_size = adaptive_block_size if adaptive_block_size % 2 == 1 else adaptive_block_size + 1
        self.adaptive_c = adaptive_c
        self.min_stripe_area = min_stripe_area
        self.min_inter_stripe_area = min_inter_stripe_area
        self.density_bounds = density_bounds
        self.min_contrast_ratio = min_contrast_ratio

    def preprocess(self, image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Converts RGB to grayscale, applies illumination correction, and enhances contrast.
        Returns:
            enhanced_gray: uint8
            raw_gray: uint8
        """
        if image is None or image.size == 0:
            raise ValueError("Input image is empty or None")

        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            gray = image.copy()

        # 1. Illumination correction via background division/subtraction
        # Zebra hides have low-frequency shading variations across curves
        ksize = int(self.bg_blur_sigma * 4) | 1
        bg = cv2.GaussianBlur(gray, (ksize, ksize), self.bg_blur_sigma)
        
        # High-pass shading removal: (gray / (bg + 1e-3)) normalized
        norm = np.clip(128.0 + (gray.astype(np.float32) - bg.astype(np.float32)), 0, 255).astype(np.uint8)

        # 2. Local contrast enhancement with CLAHE
        clahe = cv2.createCLAHE(clipLimit=self.clahe_clip_limit, tileGridSize=self.clahe_tile_grid_size)
        enhanced = clahe.apply(norm)

        return enhanced, gray

    def compute_quality_metrics(
        self,
        gray: np.ndarray,
        stripe_mask: np.ndarray,
        roi_mask: np.ndarray
    ) -> Tuple[Dict[str, float], List[str]]:
        """Calculates quantitative quality metrics and diagnoses potential failure modes."""
        warnings = []
        metrics = {}

        roi_pixels = roi_mask > 0
        roi_count = int(roi_pixels.sum())

        if roi_count < 100:
            warnings.append("ROI_TOO_SMALL: Valid analysis region contains fewer than 100 pixels")
            return {
                "stripe_density": 0.0,
                "contrast_ratio": 0.0,
                "edge_sharpness": 0.0,
                "confidence_score": 0.0
            }, warnings

        roi_gray = gray[roi_pixels]
        min_val = float(roi_gray.min())
        max_val = float(roi_gray.max())
        mean_val = float(roi_gray.mean())
        std_val = float(roi_gray.std())

        # Michelson / Weber contrast
        contrast_ratio = (max_val - min_val) / (mean_val + 1e-4) if mean_val > 0 else 0.0
        metrics["contrast_ratio"] = float(np.clip(contrast_ratio, 0.0, 5.0))

        if contrast_ratio < self.min_contrast_ratio:
            warnings.append("LOW_CONTRAST: Image contrast ratio is below reliable detection threshold")

        # Edge sharpness via Tenengrad gradient energy
        sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        grad_mag_sq = sobel_x**2 + sobel_y**2
        sharpness = float(grad_mag_sq[roi_pixels].mean())
        metrics["edge_sharpness"] = float(sharpness)

        if sharpness < 150.0:
            warnings.append("BLUR_DETECTED: High spatial blur detected in region")

        # Stripe density: fraction of ROI covered by dark stripes
        stripe_in_roi = (stripe_mask > 0) & roi_pixels
        stripe_density = float(stripe_in_roi.sum() / roi_count)
        metrics["stripe_density"] = float(stripe_density)

        if stripe_density < self.density_bounds[0]:
            warnings.append(f"ABNORMAL_STRIPE_DENSITY: Density ({stripe_density:.2f}) is abnormally sparse (< {self.density_bounds[0]})")
        elif stripe_density > self.density_bounds[1]:
            warnings.append(f"ABNORMAL_STRIPE_DENSITY: Density ({stripe_density:.2f}) is abnormally dense (> {self.density_bounds[1]})")

        # Check for potential border/texture seams
        border_mask = np.zeros_like(roi_mask)
        border_mask[:5, :] = 255
        border_mask[-5:, :] = 255
        border_mask[:, :5] = 255
        border_mask[:, -5:] = 255
        stripe_on_border = (stripe_mask > 0) & (border_mask > 0)
        border_ratio = float(stripe_on_border.sum() / (border_mask > 0).sum())
        if border_ratio > 0.85:
            warnings.append("TEXTURE_SEAM_SUSPECTED: Excessive dark boundary artifact along image perimeter")

        # Overall confidence score in [0.0, 1.0]
        # Zebra stripes typically occupy 35% to 65% area, with high contrast and sharp edges
        density_penalty = abs(stripe_density - 0.48) / 0.48
        contrast_score = min(contrast_ratio / 1.5, 1.0)
        sharpness_score = min(sharpness / 2000.0, 1.0)
        confidence = float(np.clip((1.0 - 0.5 * density_penalty) * (0.6 * contrast_score + 0.4 * sharpness_score), 0.0, 1.0))
        metrics["confidence_score"] = float(confidence)

        return metrics, warnings

    def segment(
        self,
        image: np.ndarray,
        roi_mask: Optional[np.ndarray] = None
    ) -> SegmentationResult:
        """
        Segments dark stripes from the given RGB zebra image.
        
        Args:
            image: RGB image (H, W, 3) uint8 or Grayscale (H, W) uint8
            roi_mask: Optional valid region mask (H, W) uint8 (255 for valid zebra hide)
        
        Returns:
            SegmentationResult with stripe_mask, roi_mask, visualization, metrics, warnings
        """
        if image is None or image.size == 0:
            raise ValueError("Input image is empty or None")

        H, W = image.shape[:2]

        # Determine effective ROI mask (exclude background / extreme border padding)
        if roi_mask is None:
            # Automatic ROI estimation: exclude black empty backgrounds (e.g., texture borders)
            if len(image.shape) == 3:
                gray_raw = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            else:
                gray_raw = image
            effective_roi = (gray_raw > 12).astype(np.uint8) * 255
            # Clean up holes in ROI
            kernel_roi = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
            effective_roi = cv2.morphologyEx(effective_roi, cv2.MORPH_CLOSE, kernel_roi)
        else:
            effective_roi = (roi_mask > 0).astype(np.uint8) * 255

        # Preprocess
        enhanced_gray, raw_gray = self.preprocess(image)

        # Adaptive Thresholding:
        # Note: in black-and-white zebra hides, stripes are darker than white fur
        # CV2_THRESH_BINARY_INV turns dark stripes into 255 (foreground)
        adaptive_mask = cv2.adaptiveThreshold(
            enhanced_gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            self.adaptive_block_size,
            self.adaptive_c
        )

        # Global Otsu on enhanced image for contrast consensus
        _, otsu_mask = cv2.threshold(
            enhanced_gray,
            0,
            255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        # Fuse adaptive and Otsu: require agreement or strong local ridge response
        combined = cv2.bitwise_and(adaptive_mask, otsu_mask)

        # Morphological cleanup
        # Opening removes salt noise (isolated single-pixel white or black noise)
        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel_open)

        # Closing connects broken stripe ridges
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel_close)

        # Restrict strictly to effective ROI
        cleaned = cv2.bitwise_and(cleaned, effective_roi)

        # Connected component filtering: remove tiny spurious blobs
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
        stripe_mask = np.zeros_like(cleaned)
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area >= self.min_stripe_area:
                stripe_mask[labels == i] = 255

        # Quality metrics & diagnostics
        metrics, warnings = self.compute_quality_metrics(raw_gray, stripe_mask, effective_roi)

        # Build overlay visualization
        if len(image.shape) == 2:
            rgb_base = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        else:
            rgb_base = image.copy()

        overlay = rgb_base.copy()
        # Tint segmented dark stripes in vibrant green/cyan for inspection
        stripe_bool = stripe_mask > 0
        overlay[stripe_bool, 0] = np.clip(overlay[stripe_bool, 0] * 0.4 + 20, 0, 255)
        overlay[stripe_bool, 1] = np.clip(overlay[stripe_bool, 1] * 0.4 + 220, 0, 255)
        overlay[stripe_bool, 2] = np.clip(overlay[stripe_bool, 2] * 0.4 + 180, 0, 255)

        # Draw red contours around stripes
        contours, _ = cv2.findContours(stripe_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, (255, 60, 40), 1)

        # Blend overlay (70% overlay, 30% original)
        vis = cv2.addWeighted(overlay, 0.75, rgb_base, 0.25, 0)

        # Dim excluded ROI background
        non_roi = effective_roi == 0
        vis[non_roi] = (vis[non_roi] * 0.35).astype(np.uint8)

        return SegmentationResult(
            stripe_mask=stripe_mask,
            roi_mask=effective_roi,
            visualization=vis,
            quality_metrics=metrics,
            warnings=warnings,
            parameters={
                "clahe_clip_limit": self.clahe_clip_limit,
                "adaptive_block_size": self.adaptive_block_size,
                "adaptive_c": self.adaptive_c,
                "min_stripe_area": self.min_stripe_area
            }
        )
