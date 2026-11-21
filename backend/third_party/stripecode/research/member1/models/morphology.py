"""
Stripe Morphology Analysis Engine for STRIPECODE AI (Member 1).

Computes comprehensive, scientifically grounded stripe descriptors:
- Stripe width (medial axis distance transform)
- Stripe spacing (inter-stripe valley distance transform)
- Stripe orientation (structure tensor, axial [0, 180 deg), anisotropy coherence)
- Stripe curvature (continuous differential arc-length curvature along skeleton branches)
- Branching and junction analysis (skeleton degree graph analysis and junction clustering)
- Pattern statistics (stripe density, area fraction, contrast)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter, convolve
from skimage.morphology import skeletonize


@dataclass
class MorphologyResult:
    """Structured container for all stripe morphology descriptors."""
    width_stats: Dict[str, float]
    spacing_stats: Dict[str, float]
    orientation_stats: Dict[str, float]
    curvature_stats: Dict[str, float]
    branching_stats: Dict[str, Any]
    pattern_stats: Dict[str, float]
    
    # Spatial feature maps (as numpy arrays for visualization/further downstream analysis)
    width_map: np.ndarray          # Float32 map of local width in pixels (0 outside stripes)
    orientation_map: np.ndarray    # Float32 map of local orientation in degrees [0, 180)
    coherence_map: np.ndarray      # Float32 map of local anisotropy coherence [0, 1]
    skeleton_mask: np.ndarray      # Binary uint8 skeleton
    junction_map: np.ndarray       # Binary uint8 map of bifurcation nodes
    
    warnings: List[str] = field(default_factory=list)


class StripeMorphologyAnalyzer:
    """Analyzes geometric morphology of segmented zebra stripes."""

    def __init__(
        self,
        orientation_sigma: float = 3.0,
        min_branch_length: int = 15,
        junction_cluster_radius: int = 3
    ):
        self.orientation_sigma = orientation_sigma
        self.min_branch_length = min_branch_length
        self.junction_cluster_radius = junction_cluster_radius

    def compute_stripe_width(
        self,
        stripe_mask: np.ndarray,
        skeleton: np.ndarray,
        roi_mask: np.ndarray
    ) -> Tuple[Dict[str, float], np.ndarray]:
        """
        Calculates local stripe width via distance transform along skeleton pixels.
        Width is defined as twice the distance from the medial axis to the nearest edge: W = 2 * dist.
        """
        # Distance transform inside dark stripes
        dist = cv2.distanceTransform((stripe_mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
        
        # Sample distance along skeleton inside valid ROI
        valid_skel = (skeleton > 0) & (roi_mask > 0)
        
        if valid_skel.sum() < 5:
            return {
                "mean_width": 0.0,
                "median_width": 0.0,
                "std_width": 0.0,
                "min_width": 0.0,
                "max_width": 0.0,
                "p10_width": 0.0,
                "p90_width": 0.0,
                "sample_count": 0
            }, np.zeros_like(dist, dtype=np.float32)

        raw_radii = dist[valid_skel]
        local_widths = raw_radii * 2.0  # Diameter of inscribed circle = stripe width

        # Create spatial width map
        width_map = np.zeros_like(dist, dtype=np.float32)
        width_map[valid_skel] = local_widths

        stats = {
            "mean_width": float(np.mean(local_widths)),
            "median_width": float(np.median(local_widths)),
            "std_width": float(np.std(local_widths)),
            "min_width": float(np.min(local_widths)),
            "max_width": float(np.max(local_widths)),
            "p10_width": float(np.percentile(local_widths, 10)),
            "p90_width": float(np.percentile(local_widths, 90)),
            "sample_count": int(len(local_widths))
        }
        return stats, width_map

    def compute_stripe_spacing(
        self,
        stripe_mask: np.ndarray,
        roi_mask: np.ndarray
    ) -> Tuple[Dict[str, float], np.ndarray]:
        """
        Calculates local inter-stripe spacing across white valleys between black stripes.
        Computed as twice the distance transform of white valleys along the valley medial axis.
        """
        white_valleys = ((stripe_mask == 0) & (roi_mask > 0)).astype(np.uint8)
        if white_valleys.sum() < 50:
            return {
                "mean_spacing": 0.0,
                "median_spacing": 0.0,
                "std_spacing": 0.0,
                "min_spacing": 0.0,
                "max_spacing": 0.0,
                "p10_spacing": 0.0,
                "p90_spacing": 0.0,
                "sample_count": 0
            }, np.zeros_like(stripe_mask, dtype=np.float32)

        # Distance transform inside white valleys
        dist_valleys = cv2.distanceTransform(white_valleys, cv2.DIST_L2, 5)
        valley_skel = skeletonize(white_valleys > 0) & (roi_mask > 0)

        if valley_skel.sum() < 5:
            return {
                "mean_spacing": 0.0,
                "median_spacing": 0.0,
                "std_spacing": 0.0,
                "min_spacing": 0.0,
                "max_spacing": 0.0,
                "p10_spacing": 0.0,
                "p90_spacing": 0.0,
                "sample_count": 0
            }, np.zeros_like(stripe_mask, dtype=np.float32)

        raw_spacings = dist_valleys[valley_skel] * 2.0
        spacing_map = np.zeros_like(dist_valleys, dtype=np.float32)
        spacing_map[valley_skel] = raw_spacings

        stats = {
            "mean_spacing": float(np.mean(raw_spacings)),
            "median_spacing": float(np.median(raw_spacings)),
            "std_spacing": float(np.std(raw_spacings)),
            "min_spacing": float(np.min(raw_spacings)),
            "max_spacing": float(np.max(raw_spacings)),
            "p10_spacing": float(np.percentile(raw_spacings, 10)),
            "p90_spacing": float(np.percentile(raw_spacings, 90)),
            "sample_count": int(len(raw_spacings))
        }
        return stats, spacing_map

    def compute_orientation(
        self,
        image_gray: np.ndarray,
        roi_mask: np.ndarray
    ) -> Tuple[Dict[str, float], np.ndarray, np.ndarray]:
        """
        Calculates local stripe orientation field using structure tensor:
        J = [ [ <Ix^2>, <Ix Iy> ], [ <Ix Iy>, <Iy^2> ] ]
        Stripe direction is orthogonal to the dominant intensity gradient:
        theta = 0.5 * atan2(2 * Jxy, Jxx - Jyy) + 90 deg.
        Wrapped to axial range [0, 180) degrees.
        """
        img_f = image_gray.astype(np.float32) / 255.0
        
        # Spatial gradients
        sobel_x = cv2.Sobel(img_f, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(img_f, cv2.CV_32F, 0, 1, ksize=3)

        # Tensor components
        jxx = sobel_x**2
        jyy = sobel_y**2
        jxy = sobel_x * sobel_y

        # Gaussian smoothing over local neighborhood
        jxx_smooth = gaussian_filter(jxx, sigma=self.orientation_sigma)
        jyy_smooth = gaussian_filter(jyy, sigma=self.orientation_sigma)
        jxy_smooth = gaussian_filter(jxy, sigma=self.orientation_sigma)

        # Orientation angle in radians (parallel to stripe ridge)
        # Gradient angle is 0.5 * atan2(2 * jxy, jxx - jyy). Stripe is perpendicular (+ pi/2)
        angle_rad = 0.5 * np.arctan2(2.0 * jxy_smooth, jxx_smooth - jyy_smooth) + (np.pi / 2.0)
        angle_deg = np.rad2deg(angle_rad) % 180.0  # Axial wrapping into [0, 180)

        # Coherence / Anisotropy: measure of stripe directionality
        # C = sqrt((Jxx - Jyy)^2 + 4 * Jxy^2) / (Jxx + Jyy + eps)
        numerator = np.sqrt((jxx_smooth - jyy_smooth)**2 + 4.0 * (jxy_smooth**2))
        denominator = jxx_smooth + jyy_smooth + 1e-6
        coherence = np.clip(numerator / denominator, 0.0, 1.0)

        valid_pixels = (roi_mask > 0) & (coherence > 0.15)
        if valid_pixels.sum() < 10:
            return {
                "dominant_orientation_deg": 0.0,
                "mean_orientation_deg": 0.0,
                "circular_variance": 1.0,
                "mean_coherence": 0.0,
                "orientation_entropy": 0.0
            }, angle_deg, coherence

        valid_angles = angle_deg[valid_pixels]
        valid_coherences = coherence[valid_pixels]

        # Circular mean for axial data (angles in [0, 180) mapped to 2*theta on unit circle)
        angles_2theta = np.deg2rad(valid_angles * 2.0)
        c_mean = np.mean(np.cos(angles_2theta))
        s_mean = np.mean(np.sin(angles_2theta))
        mean_2theta = np.arctan2(s_mean, c_mean)
        dominant_deg = float((np.rad2deg(mean_2theta) / 2.0) % 180.0)

        r_vector_length = float(np.sqrt(c_mean**2 + s_mean**2))
        circular_variance = float(1.0 - r_vector_length)

        # Orientation histogram (18 bins of 10 degrees)
        hist, _ = np.histogram(valid_angles, bins=18, range=(0.0, 180.0), density=True)
        hist_nonzero = hist[hist > 0]
        entropy = float(-np.sum(hist_nonzero * np.log2(hist_nonzero)))

        stats = {
            "dominant_orientation_deg": dominant_deg,
            "mean_orientation_deg": float(np.mean(valid_angles)),
            "circular_variance": circular_variance,
            "mean_coherence": float(np.mean(valid_coherences)),
            "orientation_entropy": entropy
        }
        return stats, angle_deg, coherence

    def compute_curvature_and_junctions(
        self,
        skeleton: np.ndarray,
        roi_mask: np.ndarray
    ) -> Tuple[Dict[str, float], Dict[str, Any], np.ndarray]:
        """
        Analyzes skeleton topology:
        - Junctions: pixels with 8-connectivity degree >= 3 (bifurcations / crossings).
        - Endpoints: pixels with 8-connectivity degree == 1.
        - Curvature: continuous differential curvature kappa = |x' y'' - y' x''| / (x'^2 + y'^2)^(3/2)
          along continuous branches of length >= min_branch_length.
        """
        valid_skel = (skeleton > 0) & (roi_mask > 0)
        if valid_skel.sum() < 10:
            return (
                {"mean_curvature": 0.0, "median_curvature": 0.0, "std_curvature": 0.0, "p90_curvature": 0.0},
                {"junction_count": 0, "endpoint_count": 0, "branch_count": 0, "junction_density_per_kpx": 0.0},
                np.zeros_like(skeleton, dtype=np.uint8)
            )

        # 3x3 convolution to count 8-neighbors on skeleton
        kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)
        neighbor_count = convolve(valid_skel.astype(np.uint8), kernel, mode='constant', cval=0)

        # Degree >= 3 indicates candidate branching node
        raw_junctions = valid_skel & (neighbor_count >= 3)
        raw_endpoints = valid_skel & (neighbor_count == 1)

        # Cluster neighboring junction pixels so a single Y-bifurcation is counted as one junction
        num_junc, _, stats_junc, centroids_junc = cv2.connectedComponentsWithStats(
            raw_junctions.astype(np.uint8), connectivity=8
        )
        junction_count = num_junc - 1  # Exclude background label 0

        # Create clean junction map with markers
        junction_map = np.zeros_like(skeleton, dtype=np.uint8)
        if junction_count > 0:
            for c in centroids_junc[1:]:
                cx, cy = int(round(c[0])), int(round(c[1]))
                if 0 <= cy < junction_map.shape[0] and 0 <= cx < junction_map.shape[1]:
                    junction_map[cy, cx] = 255

        endpoint_count = int(raw_endpoints.sum())
        roi_area_kpx = max(float(roi_mask.sum() / 255.0) / 1000.0, 0.01)
        junction_density = float(junction_count / roi_area_kpx)

        # Branch extraction: remove junctions to isolate continuous branch segments
        branch_skel = valid_skel & (~raw_junctions)
        num_branches, branch_labels, stats_br, _ = cv2.connectedComponentsWithStats(
            branch_skel.astype(np.uint8), connectivity=8
        )

        curvatures = []
        valid_branch_count = 0

        # Pre-group coordinates by branch label in a single vectorized pass
        ys_all, xs_all = np.where(branch_labels > 0)
        if len(ys_all) > 0:
            labels_all = branch_labels[ys_all, xs_all]
            sort_order = np.argsort(labels_all)
            sorted_labels = labels_all[sort_order]
            sorted_ys = ys_all[sort_order]
            sorted_xs = xs_all[sort_order]

            split_indices = np.where(np.diff(sorted_labels) != 0)[0] + 1
            grouped_ys = np.split(sorted_ys, split_indices)
            grouped_xs = np.split(sorted_xs, split_indices)
            unique_labels = sorted_labels[np.concatenate(([0], split_indices))]

            for lbl, ys, xs in zip(unique_labels, grouped_ys, grouped_xs):
                if len(xs) >= self.min_branch_length:
                    valid_branch_count += 1
                    coords = np.column_stack([xs, ys])
                    order = np.argsort(xs if np.ptp(xs) >= np.ptp(ys) else ys)
                    sorted_coords = coords[order].astype(np.float32)

                    w = 5
                    if len(sorted_coords) > w:
                        kernel_smooth = np.ones(w) / w
                        sx = np.convolve(sorted_coords[:, 0], kernel_smooth, mode='valid')
                        sy = np.convolve(sorted_coords[:, 1], kernel_smooth, mode='valid')

                        dx = np.gradient(sx)
                        dy = np.gradient(sy)
                        ddx = np.gradient(dx)
                        ddy = np.gradient(dy)

                        denom = (dx**2 + dy**2)**1.5 + 1e-5
                        kappa = np.abs(dx * ddy - dy * ddx) / denom
                        valid_k = kappa[(kappa >= 0.0) & (kappa <= 1.0)]
                        if len(valid_k) > 0:
                            curvatures.extend(valid_k.tolist())

        if len(curvatures) > 0:
            curv_stats = {
                "mean_curvature": float(np.mean(curvatures)),
                "median_curvature": float(np.median(curvatures)),
                "std_curvature": float(np.std(curvatures)),
                "p90_curvature": float(np.percentile(curvatures, 90))
            }
        else:
            curv_stats = {
                "mean_curvature": 0.0,
                "median_curvature": 0.0,
                "std_curvature": 0.0,
                "p90_curvature": 0.0
            }

        branch_stats = {
            "junction_count": int(junction_count),
            "endpoint_count": int(endpoint_count),
            "branch_count": int(valid_branch_count),
            "junction_density_per_kpx": float(junction_density),
            "measured_branch_segments": int(len(curvatures))
        }

        return curv_stats, branch_stats, junction_map

    def analyze(
        self,
        image_gray: np.ndarray,
        stripe_mask: np.ndarray,
        roi_mask: np.ndarray
    ) -> MorphologyResult:
        """
        Executes complete stripe morphology pipeline.
        
        Args:
            image_gray: Grayscale image (H, W) uint8
            stripe_mask: Binary stripe mask (H, W) uint8 (255 for black stripes)
            roi_mask: Valid analysis region mask (H, W) uint8
        
        Returns:
            MorphologyResult dataclass with all statistics and spatial maps
        """
        warnings = []
        valid_roi = (roi_mask > 0).astype(np.uint8) * 255

        # 1. Medial axis skeletonization
        skeleton = skeletonize(stripe_mask > 0).astype(np.uint8) * 255
        skeleton = cv2.bitwise_and(skeleton, valid_roi)

        # 2. Stripe Width
        width_stats, width_map = self.compute_stripe_width(stripe_mask, skeleton, valid_roi)
        if width_stats["sample_count"] < 20:
            warnings.append("SPARSE_WIDTH_MEASUREMENTS: Insufficient skeleton pixels for stable width estimation")

        # 3. Stripe Spacing
        spacing_stats, spacing_map = self.compute_stripe_spacing(stripe_mask, valid_roi)

        # 4. Stripe Orientation
        orientation_stats, orientation_map, coherence_map = self.compute_orientation(image_gray, valid_roi)

        # 5. Curvature and Branching
        curv_stats, branch_stats, junction_map = self.compute_curvature_and_junctions(skeleton, valid_roi)

        # 6. Overall Pattern Statistics
        roi_pixel_count = max(int((valid_roi > 0).sum()), 1)
        stripe_pixel_count = int(((stripe_mask > 0) & (valid_roi > 0)).sum())
        black_stripe_fraction = float(stripe_pixel_count / roi_pixel_count)

        pattern_stats = {
            "black_stripe_area_fraction": black_stripe_fraction,
            "stripe_density": black_stripe_fraction,
            "width_to_spacing_ratio": float(width_stats["median_width"] / max(spacing_stats["median_spacing"], 0.1)),
            "orientation_coherence": orientation_stats["mean_coherence"],
            "total_analyzed_pixels": roi_pixel_count
        }

        return MorphologyResult(
            width_stats=width_stats,
            spacing_stats=spacing_stats,
            orientation_stats=orientation_stats,
            curvature_stats=curv_stats,
            branching_stats=branch_stats,
            pattern_stats=pattern_stats,
            width_map=width_map,
            orientation_map=orientation_map,
            coherence_map=coherence_map,
            skeleton_mask=skeleton,
            junction_map=junction_map,
            warnings=warnings
        )
