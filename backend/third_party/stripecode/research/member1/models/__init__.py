"""
STRIPECODE AI - Member 1 Models and Morphology Package.
"""

from typing import Any

# Core CPU-portable stripe morphology and 3D region processing (Zero GPU / Torch dependency)
from research.member1.models.zebra1_processor import Zebra1ScanProcessor, RegionMetadata
from research.member1.models.segmentation import StripeSegmenter, SegmentationResult
from research.member1.models.morphology import StripeMorphologyAnalyzer, MorphologyResult
from research.member1.models.partial_hide import PartialHideEvaluator, PartialCropResult
from research.member1.models.api import analyze_stripes, SCHEMA_VERSION

# Heavy recognition and deep learning models are lazily loaded on demand so that
# importing `analyze_stripes` or `research.member1.models` does not eagerly load
# PyTorch, torchvision, or CUDA runtimes.
_LAZY_IMPORTS = {
    "MegaDescriptorDINOv2": ("research.member1.models.megadescriptor_dinov2", "MegaDescriptorDINOv2"),
    "GlobalLocalFusionMatcher": ("research.member1.models.fusion", "GlobalLocalFusionMatcher"),
    "fuse_scores": ("research.member1.models.fusion", "fuse_scores"),
    "compute_orb_scores": ("research.member1.models.fusion", "compute_orb_scores"),
    "flank_crop": ("research.member1.models.enhancements", "flank_crop"),
    "multi_reference_pool": ("research.member1.models.enhancements", "multi_reference_pool"),
    "multi_patch_stripe_similarity": ("research.member1.models.enhancements", "multi_patch_stripe_similarity"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_IMPORTS:
        module_name, attr_name = _LAZY_IMPORTS[name]
        try:
            import importlib
            mod = importlib.import_module(module_name)
            val = getattr(mod, attr_name)
            globals()[name] = val
            return val
        except ImportError as e:
            if name == "MegaDescriptorDINOv2":
                return None
            raise e
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "MegaDescriptorDINOv2",
    "GlobalLocalFusionMatcher",
    "fuse_scores",
    "compute_orb_scores",
    "flank_crop",
    "multi_reference_pool",
    "multi_patch_stripe_similarity",
    "Zebra1ScanProcessor",
    "RegionMetadata",
    "StripeSegmenter",
    "SegmentationResult",
    "StripeMorphologyAnalyzer",
    "MorphologyResult",
    "PartialHideEvaluator",
    "PartialCropResult",
    "analyze_stripes",
    "SCHEMA_VERSION",
]

