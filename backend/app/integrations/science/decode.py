"""Canonical image decoding (EXIF-transposed RGB uint8, zero downscaling) and ROI rules."""
from __future__ import annotations

import io
import warnings
from typing import Any

from PIL import Image, ImageOps

from app.integrations.science.constants import MIN_ROI_SIDE


class AnalysisValidationError(ValueError):
    """Client-fixable validation error on ROI or parameters."""


class AnalysisLimitError(ValueError):
    """Image or ROI exceeds configured resource limits (maps to 422 analysis_limit_exceeded)."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


def decode_canonical_rgb(
    content: bytes,
    *,
    max_source_pixels: int = 12_000_000,
    max_dimension: int = 8192,
):
    """Decode stored image bytes to canonical C-contiguous (H, W, 3) uint8 RGB NumPy array.

    - Applies EXIF orientation BEFORE returning pixel grid (matches browser display & ImageAsset).
    - Converts grayscale / palette / RGBA -> RGB without resizing or downscaling.
    - Enforces decode guards before full pixel allocation.
    """
    import numpy as np

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as opened:
                oriented = ImageOps.exif_transpose(opened)
                width, height = oriented.size
                if max(width, height) > max_dimension or width * height > max_source_pixels:
                    raise AnalysisLimitError(
                        f"Image ({width}x{height}) exceeds analysis source limit "
                        f"({max_source_pixels:,} px, max side {max_dimension} px).",
                        details={
                            "width": width,
                            "height": height,
                            "pixels": width * height,
                            "max_source_pixels": max_source_pixels,
                            "max_dimension": max_dimension,
                        },
                    )
                rgb = oriented.convert("RGB")
                arr = np.ascontiguousarray(np.asarray(rgb, dtype=np.uint8))
    except AnalysisLimitError:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise AnalysisLimitError("Image pixel dimensions exceed safe decode limits.") from None
    except Exception as exc:
        raise AnalysisValidationError(f"Could not decode stored image: {type(exc).__name__}") from None

    if arr.ndim != 3 or arr.shape[2] != 3 or arr.dtype != np.uint8:
        raise AnalysisValidationError("Decoded image is not canonical RGB uint8")
    return arr


def validate_and_resolve_roi(
    roi: dict[str, int] | None,
    width: int,
    height: int,
    *,
    kind: str,
    max_pixels: int = 4_000_000,
    max_source_pixels: int = 12_000_000,
    max_dimension: int = 8192,
) -> tuple[dict[str, int], str]:
    """Validate ROI against EXIF-oriented image bounds and configured pixel limits.

    Returns (canonical_roi_dict, roi_mode):
      - stripe_morphology: roi=None -> ("auto"), roi!=None -> ("mask")
      - spatial_frequency: always ("box")
    """
    if width <= 0 or height <= 0:
        raise AnalysisValidationError("Image dimensions are not available")

    if max(width, height) > max_dimension or width * height > max_source_pixels:
        raise AnalysisLimitError(
            f"Image ({width}x{height}) exceeds maximum source size "
            f"({max_source_pixels:,} px, max side {max_dimension} px). Save a cropped region first.",
            details={
                "width": width,
                "height": height,
                "pixels": width * height,
                "max_source_pixels": max_source_pixels,
                "max_dimension": max_dimension,
            },
        )

    if roi is None:
        resolved = {"x": 0, "y": 0, "width": int(width), "height": int(height)}
        roi_mode = "auto" if kind == "stripe_morphology" else "box"
    else:
        x = int(roi["x"])
        y = int(roi["y"])
        rw = int(roi["width"])
        rh = int(roi["height"])
        if x < 0 or y < 0 or rw < MIN_ROI_SIDE or rh < MIN_ROI_SIDE:
            raise AnalysisValidationError(
                f"ROI must have non-negative x/y and width/height of at least {MIN_ROI_SIDE} px"
            )
        if x + rw > width or y + rh > height:
            raise AnalysisValidationError(f"ROI ({x},{y},{rw},{rh}) lies outside the {width}x{height} image")
        resolved = {"x": x, "y": y, "width": rw, "height": rh}
        roi_mode = "mask" if kind == "stripe_morphology" else "box"

    if resolved["width"] < MIN_ROI_SIDE or resolved["height"] < MIN_ROI_SIDE:
        raise AnalysisValidationError(f"Analysed region must be at least {MIN_ROI_SIDE}x{MIN_ROI_SIDE} px")

    # Data Contract §1: Member 1 analyses whole image; Member 2 analyses ROI crop only.
    analysed_pixels = width * height if kind == "stripe_morphology" else resolved["width"] * resolved["height"]
    if analysed_pixels > max_pixels:
        raise AnalysisLimitError(
            f"Analysed area ({analysed_pixels:,} px) exceeds the {max_pixels:,} px limit. "
            "Select a smaller region or save a crop via POST /api/v1/images (kind=crop).",
            details={
                "analysed_pixels": analysed_pixels,
                "max_pixels": max_pixels,
                "hint": "Save a crop of the region and analyse the crop image.",
            },
        )

    return resolved, roi_mode


def roi_to_member1_mask(roi: dict[str, int], roi_mode: str, height: int, width: int):
    """Convert canonical ROI to Member 1 binary mask (H, W) uint8, or None for roi_mode='auto'."""
    if roi_mode == "auto":
        return None
    import numpy as np

    mask = np.zeros((height, width), dtype=np.uint8)
    x, y, rw, rh = roi["x"], roi["y"], roi["width"], roi["height"]
    mask[y : y + rh, x : x + rw] = 255
    return mask


def roi_to_member2_box(roi: dict[str, int]) -> list[int]:
    """Convert canonical ROI dict to Member 2 [x, y, width, height] plain Python ints."""
    return [int(roi["x"]), int(roi["y"]), int(roi["width"]), int(roi["height"])]
