"""Result & error sanitization so local filesystem or bucket paths never leak to clients."""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from app.integrations.science.constants import (
    MEMBER1_ARTIFACTS,
    MEMBER1_REF_FIELDS,
    MEMBER2_ARTIFACTS,
    MEMBER2_SAFE_ERROR_TYPES,
)

_PATH_LIKE = re.compile(r"(/|\\|[A-Za-z]:\\)")

_GENERIC_ERRORS: dict[str, str] = {
    "analysis_failed": "The stripe analysis module reported a processing failure.",
    "timeout": "Analysis exceeded the maximum allowed execution time.",
    "worker_error": "The analysis worker exited unexpectedly.",
    "interrupted": "Analysis was interrupted by a server restart.",
    "storage_error": "Could not store analysis artifacts.",
    "FileNotFoundError": "Analysis could not access a required temporary file.",
    "FileExistsError": "Analysis output directory collision occurred.",
    "OSError": "Analysis encountered a temporary filesystem error.",
}


def _safe_child_png(base_dir: Path, raw_ref: Any) -> Path | None:
    if not isinstance(raw_ref, str) or not raw_ref.strip():
        return None
    name = Path(raw_ref).name
    if not name.lower().endswith(".png"):
        return None
    candidate = (base_dir / name).resolve()
    base_resolved = base_dir.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def sanitize_member1_result(raw: dict[str, Any], artifacts_dir: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    """Preserve Member 1 output verbatim except replacing *_reference filenames with artifact names."""
    sanitized = copy.deepcopy(raw)
    found: dict[str, Path] = {}
    for field, artifact_name in MEMBER1_REF_FIELDS.items():
        path = _safe_child_png(artifacts_dir, sanitized.get(field))
        if path is not None:
            found[artifact_name] = path
            sanitized[field] = artifact_name
        elif field in sanitized and sanitized[field] is not None:
            sanitized[field] = None
    # Keep deterministic artifact order.
    ordered = {name: found[name] for name in MEMBER1_ARTIFACTS if name in found}
    return sanitized, ordered


def sanitize_member2_result(raw_result: dict[str, Any], output_dir: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    """Preserve Member 2 `result` verbatim except replacing local paths in `files` with artifact names.

    `analysis.json` is never stored or returned.
    """
    sanitized = copy.deepcopy(raw_result)
    raw_files = sanitized.get("files") if isinstance(sanitized.get("files"), dict) else {}
    found: dict[str, Path] = {}
    clean_files: dict[str, str] = {}
    for name in MEMBER2_ARTIFACTS:
        path = _safe_child_png(output_dir, raw_files.get(name))
        if path is not None:
            found[name] = path
            clean_files[name] = name
    sanitized["files"] = clean_files
    return sanitized, found


def sanitize_error_message(error_code: str, raw_message: str | None) -> str:
    """Return a client-safe error message without filesystem paths or tracebacks."""
    if error_code in MEMBER2_SAFE_ERROR_TYPES and raw_message:
        cleaned = raw_message.strip().splitlines()[0][:240]
        if cleaned and not _PATH_LIKE.search(cleaned):
            return cleaned
    return _GENERIC_ERRORS.get(error_code, "Analysis failed.")
