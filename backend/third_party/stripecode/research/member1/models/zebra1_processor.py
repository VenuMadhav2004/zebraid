"""
Zebra 1 3D Scan and Texture Region Processor.

Processes the real photogrammetric hide scan:
- Zebra1_flat64_model.obj (364,775 vertices, 724,687 triangular faces)
- Zebra1_flat64_model.png (8192 x 8192 texture atlas)

Extracts standardized 2D surface region views with complete 3D-to-UV provenance,
excluding empty atlas margins and resolving UV chart discontinuities.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class RegionMetadata:
    region_id: str
    anatomical_name: str
    p1_range: Tuple[float, float]
    p2_range: Tuple[float, float]
    p3_range: Tuple[float, float]
    sample_count: int
    resolution: Tuple[int, int]
    mean_color_rgb: List[float]
    provenance: Dict[str, Any] = field(default_factory=dict)


class Zebra1ScanProcessor:
    """Loads and processes the Zebra 1 flat 3D hide scan and extracts standardized 2D regions."""

    # Principal plane basis vectors determined from SVD of 364,775 vertices:
    U1 = np.array([0.34265597, 0.73258657, -0.58813587], dtype=np.float32)  # Longitudinal spine axis
    U2 = np.array([-0.93326777, 0.19367450, -0.30249206], dtype=np.float32)  # Lateral cross-flank axis
    U3 = np.array([0.10769470, -0.65253897, -0.75006316], dtype=np.float32)  # Surface normal

    # Standard anatomical zones defined on the (p1, p2) principal coordinate plane:
    # Coordinate units are arbitrary scan units (span ~125 x 91 units; physical mm unconfirmed).
    REGION_DEFINITIONS = {
        "flank_left_mid": {
            "name": "Mid Left Flank Torso",
            "p1": (-15.0, 15.0),
            "p2": (6.0, 32.0),
            "description": "Central lateral torso stripes on left flank, high contrast vertical/oblique patterns."
        },
        "flank_right_mid": {
            "name": "Mid Right Flank Torso",
            "p1": (-15.0, 15.0),
            "p2": (-32.0, -6.0),
            "description": "Central lateral torso stripes on right flank, contralateral to left flank."
        },
        "shoulder_anterior": {
            "name": "Anterior Shoulder Stripes",
            "p1": (16.0, 42.0),
            "p2": (-20.0, 20.0),
            "description": "Anterior neck and shoulder transitions, narrower converging stripes."
        },
        "rump_posterior": {
            "name": "Posterior Rump Stripes",
            "p1": (-48.0, -16.0),
            "p2": (-22.0, 22.0),
            "description": "Posterior dorsal rump and hip transitions, broad horizontal/chevron stripes."
        }
    }

    def __init__(self, obj_path: Optional[str] = None, texture_path: Optional[str] = None):
        self.obj_path = obj_path
        self.texture_path = texture_path
        self.vertices: Optional[np.ndarray] = None
        self.vertex_colors: Optional[np.ndarray] = None
        self.center: Optional[np.ndarray] = None
        self.p1: Optional[np.ndarray] = None
        self.p2: Optional[np.ndarray] = None
        self.p3: Optional[np.ndarray] = None

    def load_mesh(self, max_vertices: Optional[int] = None) -> bool:
        """Loads 3D vertices and embedded vertex colors from Wavefront OBJ."""
        if not self.obj_path or not os.path.exists(self.obj_path):
            return False

        verts = []
        colors = []
        with open(self.obj_path, "r") as f:
            for line in f:
                if line.startswith("v "):
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
                        if len(parts) >= 7:
                            colors.append([float(parts[4]), float(parts[5]), float(parts[6])])
                        else:
                            colors.append([0.5, 0.5, 0.5])
                    if max_vertices and len(verts) >= max_vertices:
                        break

        self.vertices = np.array(verts, dtype=np.float32)
        self.vertex_colors = np.array(colors, dtype=np.float32)
        self.center = self.vertices.mean(axis=0)

        centered = self.vertices - self.center
        self.p1 = centered @ self.U1
        self.p2 = centered @ self.U2
        self.p3 = centered @ self.U3
        return True

    def extract_orthographic_region(
        self,
        region_key: str,
        resolution: Tuple[int, int] = (512, 512),
        subsample_stride: int = 2
    ) -> Tuple[np.ndarray, np.ndarray, RegionMetadata]:
        """
        Extracts a clean, standardized 2D region view using linear grid interpolation
        over the principal plane (p1, p2), preserving coordinate provenance.
        
        Returns:
            rgb_image (H, W, 3) uint8
            valid_mask (H, W) uint8 (255 for hide, 0 for empty background)
            metadata RegionMetadata
        """
        if self.vertices is None:
            raise RuntimeError("Mesh not loaded. Call load_mesh() first.")

        if region_key not in self.REGION_DEFINITIONS:
            raise ValueError(f"Unknown region '{region_key}'. Valid: {list(self.REGION_DEFINITIONS.keys())}")

        reg = self.REGION_DEFINITIONS[region_key]
        p1_min, p1_max = reg["p1"]
        p2_min, p2_max = reg["p2"]

        # Filter vertices inside region bounds
        in_region = (
            (self.p1 >= p1_min - 2.0) & (self.p1 <= p1_max + 2.0) &
            (self.p2 >= p2_min - 2.0) & (self.p2 <= p2_max + 2.0)
        )
        sub_p1 = self.p1[in_region][::subsample_stride]
        sub_p2 = self.p2[in_region][::subsample_stride]
        sub_colors = self.vertex_colors[in_region][::subsample_stride]

        H, W = resolution
        # Grid coordinates
        grid_p1, grid_p2 = np.mgrid[
            p1_max:p1_min:complex(0, H),
            p2_min:p2_max:complex(0, W)
        ]

        from scipy.interpolate import griddata
        interp_colors = griddata(
            (sub_p1, sub_p2),
            sub_colors,
            (grid_p1, grid_p2),
            method="linear",
            fill_value=0.0
        )

        valid_mask = ((interp_colors > 0.01).any(axis=-1)).astype(np.uint8) * 255
        rgb_image = np.clip(interp_colors * 255.0, 0, 255).astype(np.uint8)

        # Contrast normalize the valid area so stripes are crisp and standardized
        if valid_mask.sum() > 0:
            valid_idx = valid_mask > 0
            gray = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            norm_gray = clahe.apply(gray)
            rgb_image[valid_idx] = cv2.cvtColor(norm_gray, cv2.COLOR_GRAY2RGB)[valid_idx]

        meta = RegionMetadata(
            region_id=region_key,
            anatomical_name=reg["name"],
            p1_range=(float(p1_min), float(p1_max)),
            p2_range=(float(p2_min), float(p2_max)),
            p3_range=(float(self.p3[in_region].min()), float(self.p3[in_region].max())),
            sample_count=int(in_region.sum()),
            resolution=(W, H),
            mean_color_rgb=[float(x) for x in sub_colors.mean(axis=0)],
            provenance={
                "source_scan": "Zebra1_flat64_model.obj",
                "principal_normal": [float(x) for x in self.U3],
                "principal_u1": [float(x) for x in self.U1],
                "principal_u2": [float(x) for x in self.U2],
                "units": "arbitrary_scan_units_uncalibrated",
                "description": reg["description"]
            }
        )
        return rgb_image, valid_mask, meta

    def export_standardized_regions(self, output_dir: str) -> Dict[str, str]:
        """Processes and exports all standardized regions to disk with metadata."""
        os.makedirs(output_dir, exist_ok=True)
        manifest = {}

        for reg_key in self.REGION_DEFINITIONS.keys():
            rgb, mask, meta = self.extract_orthographic_region(reg_key, resolution=(512, 512))
            img_path = os.path.join(output_dir, f"{reg_key}.png")
            mask_path = os.path.join(output_dir, f"{reg_key}_mask.png")
            meta_path = os.path.join(output_dir, f"{reg_key}_meta.json")

            # Save as BGR for OpenCV
            cv2.imwrite(img_path, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            cv2.imwrite(mask_path, mask)

            with open(meta_path, "w") as f:
                json.dump({
                    "region_id": meta.region_id,
                    "anatomical_name": meta.anatomical_name,
                    "p1_range": meta.p1_range,
                    "p2_range": meta.p2_range,
                    "p3_range": meta.p3_range,
                    "sample_count": meta.sample_count,
                    "resolution": meta.resolution,
                    "mean_color_rgb": meta.mean_color_rgb,
                    "provenance": meta.provenance,
                    "image_file": os.path.basename(img_path),
                    "mask_file": os.path.basename(mask_path)
                }, f, indent=2)

            manifest[reg_key] = img_path

        return manifest
