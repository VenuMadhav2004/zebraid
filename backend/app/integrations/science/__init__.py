"""Isolated scientific analysis integration (Member 1 morphology + Member 2 frequency).

The web process never imports `research`, `member1_dhanushya`, or `member2_nisan`.
All scientific code executes inside a spawned worker process with bounded concurrency.
"""
from app.integrations.science.constants import (
    MEMBER1_ARTIFACTS,
    MEMBER1_COMMIT,
    MEMBER1_CONFIG_DEFAULTS,
    MEMBER1_FUNCTION,
    MEMBER1_SCHEMA_VERSION,
    MEMBER2_ARTIFACTS,
    MEMBER2_COMMIT,
    MEMBER2_FUNCTION,
    MEMBER2_SCHEMA_VERSION,
)
from app.integrations.science.decode import (
    AnalysisLimitError,
    AnalysisValidationError,
    decode_canonical_rgb,
    validate_and_resolve_roi,
)
from app.integrations.science.sanitize import (
    sanitize_error_message,
    sanitize_member1_result,
    sanitize_member2_result,
)
from app.integrations.science.worker import (
    WorkerOutcome,
    default_vendor_dir,
    probe_capabilities,
    run_analysis_in_subprocess,
)

__all__ = [
    "AnalysisLimitError",
    "AnalysisValidationError",
    "MEMBER1_ARTIFACTS",
    "MEMBER1_COMMIT",
    "MEMBER1_CONFIG_DEFAULTS",
    "MEMBER1_FUNCTION",
    "MEMBER1_SCHEMA_VERSION",
    "MEMBER2_ARTIFACTS",
    "MEMBER2_COMMIT",
    "MEMBER2_FUNCTION",
    "MEMBER2_SCHEMA_VERSION",
    "WorkerOutcome",
    "decode_canonical_rgb",
    "default_vendor_dir",
    "probe_capabilities",
    "run_analysis_in_subprocess",
    "sanitize_error_message",
    "sanitize_member1_result",
    "sanitize_member2_result",
    "validate_and_resolve_roi",
]
