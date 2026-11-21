"""Domain enums. Stored as VARCHAR + CHECK (not native PG enums) so new values
need only a CHECK change in a migration, not ALTER TYPE."""
import enum

from sqlalchemy import Enum as SAEnum


class ImageKind(str, enum.Enum):
    QUERY = "query"          # uploaded photo to identify
    REFERENCE = "reference"  # curated photo of a known zebra (gallery candidate)
    CROP = "crop"            # region cut from another ImageAsset


class FlankSide(str, enum.Enum):
    LEFT = "left"
    RIGHT = "right"
    UNKNOWN = "unknown"


class ZebraStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DECEASED = "deceased"


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class VerificationDecision(str, enum.Enum):
    CONFIRMED = "confirmed"  # reviewer accepts a candidate as the identity
    REJECTED = "rejected"    # reviewer rejects a specific candidate
    UNKNOWN = "unknown"      # reviewer judges the query to be no gallery zebra / undecidable


class AnalysisKind(str, enum.Enum):
    STRIPE_MORPHOLOGY = "stripe_morphology"  # Member 1: research.member1.models.api.analyze_stripes
    SPATIAL_FREQUENCY = "spatial_frequency"  # Member 2: research.member2.science.safe_analyze


class RoiMode(str, enum.Enum):
    MASK = "mask"  # Member 1 binary pixel mask on full image
    AUTO = "auto"  # Member 1 roi=None (library's own gray > 12 background mask)
    BOX = "box"    # Member 2 [x, y, width, height] crop box


def str_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        # Must stay 20: live columns are VARCHAR(20) (migration 7f6be5c92a8f); every value fits.
        length=20,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
