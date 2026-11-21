"""Regression tests for EXIF orientation dimension handling."""
import io

import pytest
from PIL import ExifTags, Image, ImageOps

from app.services.images import inspect_image

ORIENTATION_TAG = int(ExifTags.Base.Orientation)


def _jpeg_with_exif_orientation(size: tuple[int, int], orientation: int | None) -> bytes:
    im = Image.new("RGB", size, (30, 120, 210))
    buf = io.BytesIO()
    save_kw: dict = {"format": "JPEG"}
    if orientation is not None:
        exif = Image.Exif()
        exif[ORIENTATION_TAG] = orientation
        save_kw["exif"] = exif.tobytes()
    im.save(buf, **save_kw)
    return buf.getvalue()


@pytest.mark.parametrize("orientation", [None, 1, 2, 3, 4, 5, 6, 7, 8])
def test_inspect_image_matches_exif_transpose_dimensions(orientation):
    raw = _jpeg_with_exif_orientation((120, 80), orientation)
    with Image.open(io.BytesIO(raw)) as opened:
        expected = ImageOps.exif_transpose(opened).size
    assert inspect_image(raw) == expected


def test_inspect_image_swaps_axes_for_90_degree_rotation():
    raw = _jpeg_with_exif_orientation((160, 90), orientation=6)
    # Raw stored grid is 160x90, browser displays 90x160 after EXIF orientation 6.
    assert inspect_image(raw) == (90, 160)


@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
def test_inspect_image_handles_png_and_webp_with_and_without_exif(fmt):
    im = Image.new("RGB", (110, 70), (50, 90, 140))
    buf = io.BytesIO()
    im.save(buf, format=fmt)
    assert inspect_image(buf.getvalue()) == (110, 70)

    exif = Image.Exif()
    exif[ORIENTATION_TAG] = 6
    buf_rot = io.BytesIO()
    im.save(buf_rot, format=fmt, exif=exif.tobytes())
    raw_rot = buf_rot.getvalue()
    with Image.open(io.BytesIO(raw_rot)) as opened:
        expected = ImageOps.exif_transpose(opened).size
    assert inspect_image(raw_rot) == expected
