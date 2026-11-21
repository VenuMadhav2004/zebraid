"""MegaDescriptor-L-384 v1 CPU recognition adapter & persistent gallery cache."""
from app.integrations.recognition.megadescriptor import (
    CHECKPOINT_SHA256,
    MODEL_ID,
    MODEL_REVISION,
    RankedCandidate,
    RecognitionNotConfiguredError,
    RecognitionResult,
    RecognitionRuntimeError,
    clear_recognition_cache,
    get_recognition_status,
    identify_with_cached_gallery,
    model_load_state,
    preload_model_in_background,
)

__all__ = [
    "CHECKPOINT_SHA256",
    "MODEL_ID",
    "MODEL_REVISION",
    "RankedCandidate",
    "RecognitionNotConfiguredError",
    "RecognitionResult",
    "RecognitionRuntimeError",
    "clear_recognition_cache",
    "get_recognition_status",
    "identify_with_cached_gallery",
    "model_load_state",
    "preload_model_in_background",
]
