"""Image-space low-pass models; no claim of a measured zebra CSF."""
from __future__ import annotations
import math
import warnings
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter


def normalize_image(image: np.ndarray) -> np.ndarray:
    """Convert RGB or grayscale uint8/uint16 or [0,1] float into float32 [0,1]."""
    a = np.asarray(image)
    if a.ndim not in (2, 3) or (a.ndim == 3 and a.shape[2] != 3) or min(a.shape[:2]) < 2:
        raise ValueError('Expected grayscale or RGB image with height and width >= 2')
    if a.dtype == np.uint8: a = a.astype(np.float32) / 255
    elif a.dtype == np.uint16: a = a.astype(np.float32) / 65535
    elif np.issubdtype(a.dtype, np.floating): a = a.astype(np.float32)
    else: raise ValueError('Only uint8, uint16 and floats in [0,1] are supported')
    if not np.all(np.isfinite(a)) or np.min(a) < 0 or np.max(a) > 1:
        raise ValueError('Image values must be finite and in [0,1]')
    return a


def visual_angle_deg(scene_width_m: float, distance_m: float) -> float:
    if not all(math.isfinite(x) and x > 0 for x in (scene_width_m, distance_m)):
        raise ValueError('scene width and distance must be positive and finite')
    return math.degrees(2 * math.atan(scene_width_m / (2 * distance_m)))


def simulate_vision(image: np.ndarray, distance_m: float | None = None, acuity_cpd: float | None = None,
                    scene_width_m: float | None = None, *, mode: str = 'calibrated',
                    detail_cutoff_cpp: float | None = None, filter_type: str = 'gaussian',
                    contrast: float = 1.0, lighting: str = 'unspecified',
                    sample: bool = False, butterworth_order: int = 2) -> dict:
    """Return image and assumptions. Gaussian H(cutoff)=0.5; Butterworth H=1/(1+(f/fc)^(2n))."""
    a = normalize_image(image); h, w = a.shape[:2]
    notes = []
    if mode == 'calibrated':
        if distance_m is None or scene_width_m is None or acuity_cpd is None:
            raise ValueError('calibrated mode requires distance, scene width and acuity')
        if not math.isfinite(acuity_cpd) or acuity_cpd <= 0: raise ValueError('acuity must be positive')
        angle = visual_angle_deg(scene_width_m, distance_m)
        degrees_per_pixel = angle / w
        cutoff = acuity_cpd * degrees_per_pixel
        if angle > 30: notes.append('Wide field: uniform angular pixel scale is an approximation.')
        if cutoff >= .5: notes.append('Requested cutoff exceeds image Nyquist; missing detail cannot be recovered.')
    elif mode == 'exploratory':
        if detail_cutoff_cpp is None or not math.isfinite(detail_cutoff_cpp) or not 0 < detail_cutoff_cpp <= .5:
            raise ValueError('exploratory mode requires detail_cutoff_cpp in (0, 0.5]')
        cutoff = detail_cutoff_cpp; degrees_per_pixel = None; angle = None
        notes.append('Physical scale is unknown; result is not calibrated to a viewing distance.')
    else: raise ValueError('mode must be calibrated or exploratory')
    if not math.isfinite(cutoff) or cutoff < 1e-5:
        raise ValueError('cutoff is too small for a stable finite-image simulation')
    if not math.isfinite(contrast) or not 0 <= contrast <= 1: raise ValueError('contrast must be in [0,1]')
    if lighting not in ('unspecified', 'photopic', 'mesopic'): raise ValueError('unknown lighting')
    if lighting != 'unspecified': notes.append('Lighting is a label only; no measured lighting-specific CSF is applied.')
    if filter_type == 'gaussian':
        sigma = math.sqrt(math.log(2) / (2 * math.pi ** 2)) / cutoff
        out = gaussian_filter(a, sigma=(sigma, sigma) if a.ndim == 2 else (sigma, sigma, 0), mode='reflect')
        params = {'sigma_pixels': sigma, 'transfer': 'exp(-2*pi^2*sigma^2*f^2)'}
    elif filter_type == 'butterworth':
        if not isinstance(butterworth_order, int) or butterworth_order < 1 or butterworth_order > 10: raise ValueError('order must be an integer from 1 to 10')
        fy = np.fft.fftfreq(h)[:, None]; fx = np.fft.fftfreq(w)[None, :]
        ratio = np.hypot(fx, fy) / cutoff
        transfer = 1 / (1 + ratio ** (2 * butterworth_order))
        freq = np.fft.fft2(a, axes=(0, 1)); out = np.fft.ifft2(freq * (transfer[..., None] if a.ndim == 3 else transfer), axes=(0, 1)).real
        params = {'order': butterworth_order, 'transfer': '1/(1+(f/fc)^(2n))', 'boundary': 'periodic'}
    else: raise ValueError('unknown filter type')
    if sample:
        step = max(1, int(math.floor(1 / (2 * cutoff))))
        if step > 1:
            size = (max(1, w // step), max(1, h // step))
            out = cv2.resize(cv2.resize(out.astype(np.float32), size, interpolation=cv2.INTER_AREA), (w, h), interpolation=cv2.INTER_NEAREST)
    else: step = 1
    out = np.clip(.5 + contrast * (out - .5), 0, 1).astype(np.float32)
    for note in notes: warnings.warn(note, UserWarning, stacklevel=2)
    return {'image': out, 'metadata': {'mode': mode, 'angle_deg': angle, 'degrees_per_pixel': degrees_per_pixel,
            'cutoff_cycles_per_pixel': cutoff, 'acuity_cpd': acuity_cpd, 'distance_m': distance_m,
            'scene_width_m': scene_width_m, 'filter': filter_type, 'filter_parameters': params,
            'contrast': contrast, 'lighting': lighting, 'sampling_step': step, 'warnings': notes}}


def image_pyramid(image: np.ndarray, levels: int = 3) -> list[np.ndarray]:
    a = normalize_image(image)
    if not isinstance(levels, int) or levels < 1: raise ValueError('levels must be positive')
    output = [a]
    for _ in range(levels - 1):
        if min(output[-1].shape[:2]) < 4: break
        output.append(cv2.pyrDown(output[-1]))
    return output


def compare_images(original: np.ndarray, transformed: np.ndarray) -> np.ndarray:
    a, b = normalize_image(original), normalize_image(transformed)
    if a.shape != b.shape: raise ValueError('images must have the same shape')
    return np.concatenate((a, b), axis=1)
