"""Isolated multiprocessing ('spawn') worker for Member 1 & Member 2 analyses.

Design guarantees (STRIPEFORGE_UNIFIED_ARCHITECTURE.md §3 & §6):
- The FastAPI web process never imports research modules or scientific libraries.
- Each job runs in a fresh spawned subprocess so native memory is returned to the OS
  on exit, timeouts hard-terminate the worker, and native crashes cannot kill the API.
- Temporary directories are private (0o700) and always deleted in `finally`.
- Member 2 always receives a newly created non-existent child directory inside the temp dir.
"""
from __future__ import annotations

import importlib.util
import logging
import multiprocessing
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty
from typing import Any

from app.integrations.science.constants import (
    MEMBER1_COMMIT,
    MEMBER1_FUNCTION,
    MEMBER1_SCHEMA_VERSION,
    MEMBER2_COMMIT,
    MEMBER2_FUNCTION,
    MEMBER2_SCHEMA_VERSION,
)
from app.integrations.science.decode import (
    AnalysisLimitError,
    AnalysisValidationError,
    decode_canonical_rgb,
    roi_to_member1_mask,
    roi_to_member2_box,
)
from app.integrations.science.sanitize import (
    sanitize_error_message,
    sanitize_member1_result,
    sanitize_member2_result,
)

logger = logging.getLogger(__name__)


def default_vendor_dir() -> Path:
    """Default location for the vendored combined research tree: backend/third_party/stripecode."""
    return Path(__file__).resolve().parents[3] / "third_party" / "stripecode"


@dataclass(frozen=True)
class WorkerOutcome:
    ok: bool
    result: dict[str, Any] | None = None
    artifact_bytes: dict[str, bytes] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


def _configure_worker_env(vendor_dir: str) -> None:
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["MPLBACKEND"] = "Agg"
    if vendor_dir and vendor_dir not in sys.path:
        sys.path.insert(0, vendor_dir)


_REQUIRED_SCIENCE_MODULES: tuple[str, ...] = ("numpy", "scipy", "cv2", "skimage", "matplotlib")


def probe_capabilities(vendor_dir: str | Path | None = None, *, timeout: float = 20.0) -> dict[str, dict[str, Any]]:
    """Check whether Member 1 & Member 2 modules + scientific packages are installed without importing them.

    Uses file presence + `importlib.util.find_spec` (<2 ms) so the FastAPI web process never
    imports research modules or scientific libraries and never blocks requests waiting on a cold
    subprocess spawn over network filesystems.
    """
    del timeout  # kept for signature compatibility
    resolved = Path(vendor_dir) if vendor_dir else default_vendor_dir()
    if not resolved.is_dir() or not (resolved / "research").is_dir():
        reason = "Research modules are not vendored yet (awaiting team approval)."
        return {
            "stripe_morphology": {
                "available": False,
                "reason": reason,
                "source_commit": MEMBER1_COMMIT,
                "schema_version": MEMBER1_SCHEMA_VERSION,
            },
            "spatial_frequency": {
                "available": False,
                "reason": reason,
                "source_commit": MEMBER2_COMMIT,
                "schema_version": MEMBER2_SCHEMA_VERSION,
            },
        }

    missing_deps = [m for m in _REQUIRED_SCIENCE_MODULES if importlib.util.find_spec(m) is None]
    out: dict[str, dict[str, Any]] = {}
    specs = (
        (
            "stripe_morphology",
            resolved / "research" / "member1" / "models" / "api.py",
            MEMBER1_COMMIT,
            MEMBER1_SCHEMA_VERSION,
        ),
        (
            "spatial_frequency",
            resolved / "research" / "member2" / "science" / "interface_v1.py",
            MEMBER2_COMMIT,
            MEMBER2_SCHEMA_VERSION,
        ),
    )
    for kind, entry_file, commit, schema in specs:
        if not entry_file.is_file():
            out[kind] = {
                "available": False,
                "reason": "Vendored research entrypoint is missing.",
                "source_commit": commit,
                "schema_version": schema,
            }
        elif missing_deps:
            out[kind] = {
                "available": False,
                "reason": f"Scientific runtime dependency unavailable ({', '.join(missing_deps)}).",
                "source_commit": commit,
                "schema_version": schema,
            }
        else:
            out[kind] = {
                "available": True,
                "reason": None,
                "source_commit": commit,
                "schema_version": schema,
            }
    return out


def _analysis_child(payload: dict[str, Any], queue: Any) -> None:
    """Entry point executed inside the isolated spawned worker process."""
    vendor_dir: str = payload["vendor_dir"]
    _configure_worker_env(vendor_dir)

    try:
        import cv2

        cv2.setNumThreads(2)
    except Exception:
        pass

    kind: str = payload["kind"]
    tmp_dir = Path(payload["tmp_dir"])
    try:
        arr = decode_canonical_rgb(
            payload["image_bytes"],
            max_source_pixels=payload["max_source_pixels"],
            max_dimension=payload["max_dimension"],
        )
        h, w = int(arr.shape[0]), int(arr.shape[1])

        if kind == "stripe_morphology":
            from research.member1.models.api import analyze_stripes

            mask = roi_to_member1_mask(payload["roi"], payload["roi_mode"], h, w)
            config = payload["parameters"].get("config") or None
            raw = analyze_stripes(
                arr,
                roi=mask,
                config=config,
                save_artifacts=True,
                artifacts_dir=str(tmp_dir),
            )
            if not isinstance(raw, dict) or raw.get("status") == "FAILED":
                raw_msg = raw.get("error_message") if isinstance(raw, dict) else None
                queue.put(
                    {
                        "ok": False,
                        "error_code": "analysis_failed",
                        "error_message": sanitize_error_message("analysis_failed", raw_msg),
                        "raw_error": raw_msg,
                    }
                )
                return
            sanitized, files = sanitize_member1_result(raw, tmp_dir)
            queue.put(
                {
                    "ok": True,
                    "result": sanitized,
                    "artifact_paths": {k: str(v) for k, v in files.items()},
                }
            )
            return

        if kind == "spatial_frequency":
            from research.member2.science import safe_analyze

            opts = payload["parameters"].get("options") or {}
            box = roi_to_member2_box(payload["roi"])
            # Member 2 requires a newly created, non-existent output directory.
            m2_out = tmp_dir / "m2_out"
            envelope = safe_analyze(
                arr,
                str(m2_out),
                roi=box,
                filter_type=opts.get("filter_type", "gaussian"),
                cutoff_cpp=opts.get("cutoff_cpp", 0.06),
                band_low_cpp=opts.get("band_low_cpp", 0.03),
                source_reference=payload["image_id"],
            )
            if not isinstance(envelope, dict) or not envelope.get("ok"):
                err = envelope.get("error") if isinstance(envelope, dict) else {}
                err_type = str((err or {}).get("type") or "worker_error")
                raw_msg = (err or {}).get("message")
                queue.put(
                    {
                        "ok": False,
                        "error_code": err_type,
                        "error_message": sanitize_error_message(err_type, raw_msg),
                        "raw_error": raw_msg,
                    }
                )
                return
            sanitized, files = sanitize_member2_result(envelope["result"], m2_out)
            queue.put(
                {
                    "ok": True,
                    "result": sanitized,
                    "artifact_paths": {k: str(v) for k, v in files.items()},
                }
            )
            return

        queue.put(
            {
                "ok": False,
                "error_code": "worker_error",
                "error_message": f"Unsupported analysis kind: {kind}",
            }
        )
    except (AnalysisLimitError, AnalysisValidationError) as exc:
        queue.put(
            {
                "ok": False,
                "error_code": "ValueError",
                "error_message": sanitize_error_message("ValueError", str(exc)),
                "raw_error": str(exc),
            }
        )
    except Exception as exc:
        queue.put(
            {
                "ok": False,
                "error_code": "worker_error",
                "error_message": sanitize_error_message("worker_error", str(exc)),
                "raw_error": f"{type(exc).__name__}: {exc}",
            }
        )


def provider_metadata(kind: str) -> dict[str, str]:
    if kind == "stripe_morphology":
        return {
            "function": MEMBER1_FUNCTION,
            "library_schema_version": MEMBER1_SCHEMA_VERSION,
            "source_commit": MEMBER1_COMMIT,
        }
    return {
        "function": MEMBER2_FUNCTION,
        "library_schema_version": MEMBER2_SCHEMA_VERSION,
        "source_commit": MEMBER2_COMMIT,
    }


def run_analysis_in_subprocess(
    *,
    kind: str,
    image_id: str,
    image_bytes: bytes,
    roi: dict[str, int],
    roi_mode: str,
    parameters: dict[str, Any],
    vendor_dir: str | Path | None = None,
    tmp_root: str | Path | None = None,
    timeout_seconds: int = 120,
    max_source_pixels: int = 12_000_000,
    max_dimension: int = 8192,
) -> WorkerOutcome:
    """Execute one scientific analysis in an isolated process, returning sanitized results + PNG bytes."""
    resolved_vendor = str(Path(vendor_dir) if vendor_dir else default_vendor_dir())
    base_tmp = str(tmp_root) if tmp_root else None
    tmp_dir = Path(tempfile.mkdtemp(prefix="sf-", dir=base_tmp))
    try:
        os.chmod(tmp_dir, 0o700)
        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        payload = {
            "vendor_dir": resolved_vendor,
            "kind": kind,
            "image_id": image_id,
            "image_bytes": image_bytes,
            "roi": roi,
            "roi_mode": roi_mode,
            "parameters": parameters,
            "tmp_dir": str(tmp_dir),
            "max_source_pixels": max_source_pixels,
            "max_dimension": max_dimension,
        }
        proc = ctx.Process(target=_analysis_child, args=(payload, queue))
        proc.start()
        proc.join(timeout_seconds)

        if proc.is_alive():
            logger.warning("Analysis worker timed out after %ss (kind=%s image=%s)", timeout_seconds, kind, image_id)
            proc.terminate()
            proc.join(5)
            if proc.is_alive():
                proc.kill()
                proc.join(2)
            return WorkerOutcome(
                ok=False,
                error_code="timeout",
                error_message=sanitize_error_message("timeout", None),
            )

        # Queue.empty() is not reliable across processes; wait briefly for the message instead.
        try:
            msg = queue.get(timeout=5)
        except Empty:
            logger.error("Analysis worker exited with code %s without output", proc.exitcode)
            return WorkerOutcome(
                ok=False,
                error_code="worker_error",
                error_message=sanitize_error_message("worker_error", None),
            )
        if not msg.get("ok"):
            if msg.get("raw_error"):
                logger.warning("Analysis failed (kind=%s code=%s): %s", kind, msg.get("error_code"), msg["raw_error"])
            return WorkerOutcome(
                ok=False,
                error_code=msg.get("error_code") or "worker_error",
                error_message=msg.get("error_message") or sanitize_error_message("worker_error", None),
            )

        artifact_bytes: dict[str, bytes] = {}
        for name, raw_path in (msg.get("artifact_paths") or {}).items():
            p = Path(raw_path).resolve()
            # Ensure we only ever read files inside our private tmp_dir.
            p.relative_to(tmp_dir.resolve())
            artifact_bytes[name] = p.read_bytes()

        return WorkerOutcome(
            ok=True,
            result=msg["result"],
            artifact_bytes=artifact_bytes,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
