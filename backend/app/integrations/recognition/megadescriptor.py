"""MegaDescriptor-L-384 v1 CPU recognition engine with cached gallery embeddings.

Uses the exact pinned research modules (preserving original import paths):
  - `member1_dhanushya.recognition.load_recognition_model` (SHA-256 verified, CPU-only)
  - `research.member2.deployment.gallery.CpuGalleryIndex` (non-pickle atomic NPZ cache)

Scientific integrity guarantees:
  - Scores are cosine similarities, never calibrated identity probabilities.
  - `predicted_unknown` is always `None` (no uncalibrated threshold claim).
  - Never fabricates embeddings, rankings, or accuracy metrics.
  - Never auto-confirms identities; human verification is always required.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import resource
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.core.config import Settings
from app.integrations.science.decode import decode_canonical_rgb
from app.integrations.science.worker import default_vendor_dir

logger = logging.getLogger(__name__)

MODEL_ID = "BVRA/MegaDescriptor-L-384"
MODEL_REVISION = "33b3c6f4ee0c386a4126cc3dcd23843920613fa1"
CHECKPOINT_SHA256 = "ccfe757f50f7984a115ffe00921cd4c09e260e645215463b23814586040227a3"
VALID_PREPROCESSING = ("model_card", "checkpoint_config")


class RecognitionNotConfiguredError(RuntimeError):
    """Raised when MegaDescriptor checkpoint or runtime dependencies are unavailable."""


class RecognitionRuntimeError(RuntimeError):
    """Raised when MegaDescriptor inference or gallery caching fails."""


@dataclass(frozen=True)
class RankedCandidate:
    rank: int
    zebra_id: str
    matched_reference_image_id: str
    similarity_score: float


@dataclass(frozen=True)
class RecognitionResult:
    model_name: str
    model_version: str
    candidates: list[RankedCandidate]
    margin: float | None
    inference_seconds: float
    model_load_seconds: float
    total_seconds: float
    rss_mb: float | None
    gallery_reference_count: int
    gallery_identity_count: int
    gallery_cache_hits: int
    gallery_cache_misses: int
    gallery_cache_removals: int
    device: str = "cpu"
    preprocessing: str = "model_card"
    score_type: str = "cosine similarity, not probability"


_model_lock = threading.Lock()
_gallery_lock = threading.Lock()
_cached_model_key: tuple[str, str, str] | None = None
_cached_model: Any | None = None
# Load state reported by the capabilities endpoint: idle | loading | loaded | failed
_load_state: dict[str, Any] = {"state": "idle", "seconds": None, "error": None}


def model_load_state() -> dict[str, Any]:
    return dict(_load_state)


def preload_model_in_background(settings: Settings) -> threading.Thread | None:
    """Start loading the checkpoint in a daemon thread (no-op if unavailable or already loaded/loading)."""
    if not get_recognition_status(settings).get("available") or _load_state["state"] in ("loading", "loaded"):
        return None

    def _run() -> None:
        try:
            _load_or_get_model(settings)
        except Exception as exc:  # reported via model_load_state(); requests retry the load
            logger.error("MegaDescriptor preload failed: %s", exc)

    thread = threading.Thread(target=_run, name="megadescriptor-preload", daemon=True)
    thread.start()
    return thread


def clear_recognition_cache() -> None:
    global _cached_model_key, _cached_model
    with _model_lock:
        _cached_model_key = None
        _cached_model = None
        _load_state.update(state="idle", seconds=None, error=None)


def _ensure_vendor_on_path(vendor_dir: Path) -> None:
    s = str(vendor_dir)
    if s not in sys.path:
        sys.path.insert(0, s)


def _resolve_model_path(settings: Settings) -> Path | None:
    raw = (settings.recognition_model_path or os.environ.get("STRIPECODE_MODEL_PATH", "")).strip()
    return Path(raw).expanduser() if raw else None


def _resolve_gallery_cache_path(settings: Settings) -> Path:
    raw = (settings.recognition_gallery_cache_path or os.environ.get("STRIPECODE_GALLERY_PATH", "")).strip()
    if raw:
        return Path(raw).expanduser()
    cache_dir = Path.home() / ".cache" / "stripecode"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(cache_dir, 0o700)
    except OSError:
        pass
    return cache_dir / "gallery_cache.npz"


def _current_rss_mb() -> float | None:
    """Measure current process RSS in MiB (Linux /proc/self/status, fallback ru_maxrss)."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                kb = int(line.split()[1])
                return round(kb / 1024.0, 2)
    except Exception:
        pass
    try:
        kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(kb / 1024.0, 2)
    except Exception:
        return None


def get_recognition_status(settings: Settings) -> dict[str, Any]:
    """Check whether MegaDescriptor-L-384 v1 can run on CPU without loading weights."""
    vendor_dir = Path(settings.science_vendor_dir) if settings.science_vendor_dir else default_vendor_dir()
    preprocessing = settings.recognition_preprocessing.strip() or "model_card"
    base = {
        "model_name": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "preprocessing": preprocessing,
        "device": "cpu",
        "gallery_cache_enabled": True,
    }

    if preprocessing not in VALID_PREPROCESSING:
        return {**base, "available": False, "reason": f"Invalid RECOGNITION_PREPROCESSING: {preprocessing!r}."}

    if not (vendor_dir / "member1_dhanushya" / "recognition" / "engine.py").is_file():
        return {**base, "available": False, "reason": "Vendored recognition module is not present."}

    if not (vendor_dir / "research" / "member2" / "deployment" / "gallery.py").is_file():
        return {**base, "available": False, "reason": "Vendored CpuGalleryIndex module is not present."}

    model_path = _resolve_model_path(settings)
    if model_path is None:
        return {
            **base,
            "available": False,
            "reason": "RECOGNITION_MODEL_PATH (or STRIPECODE_MODEL_PATH) is not configured on the backend.",
        }
    if not model_path.is_file():
        return {
            **base,
            "available": False,
            "reason": "Configured MegaDescriptor checkpoint file was not found on the server.",
        }

    for mod_name in ("torch", "torchvision", "timm", "numpy", "cv2"):
        if importlib.util.find_spec(mod_name) is None:
            return {
                **base,
                "available": False,
                "reason": f"Required ML dependency '{mod_name}' is not installed.",
            }

    return {**base, "available": True, "reason": None}


def _load_or_get_model(settings: Settings) -> tuple[Any, float]:
    global _cached_model_key, _cached_model

    vendor_dir = Path(settings.science_vendor_dir) if settings.science_vendor_dir else default_vendor_dir()
    model_path = _resolve_model_path(settings)
    if model_path is None or not model_path.is_file():
        raise RecognitionNotConfiguredError("MegaDescriptor checkpoint is not configured or missing.")

    preprocessing = settings.recognition_preprocessing.strip() or "model_card"
    key = (str(vendor_dir.resolve()), str(model_path.resolve()), preprocessing)

    with _model_lock:
        if _cached_model is not None and _cached_model_key == key:
            return _cached_model, 0.0

        _ensure_vendor_on_path(vendor_dir)
        from member1_dhanushya.recognition import load_recognition_model

        _load_state.update(state="loading", seconds=None, error=None)
        t0 = time.perf_counter()
        try:
            model = load_recognition_model(model_path, device="cpu", preprocessing=preprocessing)
        except Exception as exc:
            _load_state.update(state="failed", error=type(exc).__name__)
            raise
        load_sec = time.perf_counter() - t0
        _load_state.update(state="loaded", seconds=round(load_sec, 1), error=None)
        _cached_model = model
        _cached_model_key = key
        logger.info("Loaded MegaDescriptor-L-384 v1 on CPU in %.2fs (%s)", load_sec, model.model_id)
        return model, load_sec


def identify_with_cached_gallery(
    *,
    settings: Settings,
    query_bytes: bytes,
    gallery_specs: list[tuple[str, str, str]],
    download_bytes: Callable[[str], bytes],
    top_k: int = 5,
    exclude_image_id: str | None = None,
) -> RecognitionResult:
    """Sync active gallery entries into CpuGalleryIndex and rank candidates for a query image.

    `gallery_specs` is a list of `(image_asset_id, zebra_id, storage_path)` tuples for active
    gallery entries. Cached embeddings in `CpuGalleryIndex` are reused across queries without
    re-downloading or re-encoding unchanged reference images.
    """
    t_total_start = time.perf_counter()

    active_specs = [
        (img_id, zebra_id, path)
        for img_id, zebra_id, path in gallery_specs
        if img_id != exclude_image_id
    ]
    if not active_specs:
        raise RecognitionRuntimeError("At least one active gallery reference image is required for identification.")

    vendor_dir = Path(settings.science_vendor_dir) if settings.science_vendor_dir else default_vendor_dir()
    _ensure_vendor_on_path(vendor_dir)
    model, model_load_seconds = _load_or_get_model(settings)

    from member1_dhanushya.recognition.engine import _unit
    from research.member2.deployment.gallery import CpuGalleryIndex

    query_rgb = decode_canonical_rgb(
        query_bytes,
        max_source_pixels=settings.analysis_max_source_pixels,
        max_dimension=settings.analysis_max_dimension,
    )

    cache_path = _resolve_gallery_cache_path(settings)
    cache_hits = 0
    cache_misses = 0
    cache_removals = 0

    with _gallery_lock:
        try:
            index = CpuGalleryIndex(model, cache_path)
        except ValueError:
            # Model/preprocessing changed or cache corrupt: reset cache cleanly.
            if cache_path.exists():
                cache_path.unlink()
            index = CpuGalleryIndex(model, cache_path)

        existing = {sample_id: identity for sample_id, identity, _, _ in index.entries}
        active_map = {img_id: (zebra_id, path) for img_id, zebra_id, path in active_specs}

        # Remove stale/deactivated references
        for sample_id in list(existing.keys()):
            if sample_id not in active_map:
                index.remove(sample_id)
                cache_removals += 1

        # Add new or reassigned references; reuse cached embeddings for unchanged ones
        for img_id, (zebra_id, storage_path) in active_map.items():
            if img_id in existing and existing[img_id] == zebra_id:
                cache_hits += 1
                continue
            ref_bytes = download_bytes(storage_path)
            ref_rgb = decode_canonical_rgb(
                ref_bytes,
                max_source_pixels=settings.analysis_max_source_pixels,
                max_dimension=settings.analysis_max_dimension,
            )
            index.register(img_id, zebra_id, ref_rgb, replace=(img_id in existing))
            cache_misses += 1

        gallery = index.gallery()

    # Run query encoding & per-identity scoring (tracking matched reference image per identity)
    t_inf_start = time.perf_counter()
    q_vec = _unit(model.encode([query_rgb], batch_size=1))[0]
    g_vecs = _unit(gallery.embeddings)
    scores = g_vecs @ q_vec

    best_by_zebra: dict[str, tuple[float, str]] = {}
    for zebra_id, ref_img_id, score in zip(gallery.identities, gallery.sample_ids, scores):
        val = float(score)
        prev = best_by_zebra.get(zebra_id)
        if prev is None or val > prev[0]:
            best_by_zebra[zebra_id] = (val, ref_img_id)

    ordered = sorted(best_by_zebra.items(), key=lambda item: (-item[1][0], item[0]))
    inference_seconds = time.perf_counter() - t_inf_start

    margin = (ordered[0][1][0] - ordered[1][1][0]) if len(ordered) > 1 else None
    candidates = [
        RankedCandidate(
            rank=idx,
            zebra_id=zebra_id,
            matched_reference_image_id=ref_img_id,
            similarity_score=sim,
        )
        for idx, (zebra_id, (sim, ref_img_id)) in enumerate(ordered[:top_k], start=1)
    ]

    return RecognitionResult(
        model_name=MODEL_ID,
        model_version=model.model_id,
        candidates=candidates,
        margin=margin,
        inference_seconds=round(inference_seconds, 4),
        model_load_seconds=round(model_load_seconds, 4),
        total_seconds=round(time.perf_counter() - t_total_start, 4),
        rss_mb=_current_rss_mb(),
        gallery_reference_count=len(gallery.sample_ids),
        gallery_identity_count=len(best_by_zebra),
        gallery_cache_hits=cache_hits,
        gallery_cache_misses=cache_misses,
        gallery_cache_removals=cache_removals,
        device="cpu",
        preprocessing=settings.recognition_preprocessing.strip() or "model_card",
    )
