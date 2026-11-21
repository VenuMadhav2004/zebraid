"""ORM models. Importing this package registers every table on Base.metadata."""
from app.models.enums import (
    AnalysisKind,
    FlankSide,
    ImageKind,
    RoiMode,
    RunStatus,
    VerificationDecision,
    ZebraStatus,
)
from app.models.gallery import GalleryEntry
from app.models.identification import IdentificationCandidate, IdentificationRun
from app.models.image_asset import ImageAsset
from app.models.sighting import Sighting
from app.models.stripe_analysis import StripeAnalysis
from app.models.verification import Verification
from app.models.zebra import Zebra

__all__ = [
    "AnalysisKind",
    "FlankSide",
    "GalleryEntry",
    "IdentificationCandidate",
    "IdentificationRun",
    "ImageAsset",
    "ImageKind",
    "RoiMode",
    "RunStatus",
    "Sighting",
    "StripeAnalysis",
    "Verification",
    "VerificationDecision",
    "Zebra",
    "ZebraStatus",
]
