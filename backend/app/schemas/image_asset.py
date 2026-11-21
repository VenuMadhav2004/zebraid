import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import ImageKind
from app.schemas.common import Timestamped, reject_nulls

AllowedImageType = Literal["image/jpeg", "image/png", "image/webp"]
_UNSAFE_PATH = re.compile(r"(^|/)\.\.(/|$)|[\\\x00-\x1f\x7f]")


class CropBox(BaseModel):
    """Region in source-image pixels, same (x, y, width, height) order as analyze_zebra(region=...)."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=2)
    height: int = Field(ge=2)


class ImageAssetCreate(BaseModel):
    kind: ImageKind
    storage_bucket: str = Field(min_length=3, max_length=63)
    storage_path: str = Field(min_length=1, max_length=512)
    content_type: AllowedImageType
    size_bytes: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    captured_at: datetime | None = None
    uploaded_by: str | None = Field(default=None, max_length=120)
    source_image_id: uuid.UUID | None = None
    crop_bbox: CropBox | None = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("storage_path")
    @classmethod
    def path_not_url(cls, v: str) -> str:
        if "://" in v or v.startswith("/"):
            raise ValueError("storage_path must be a bucket-relative object path, not a URL")
        if _UNSAFE_PATH.search(v):
            raise ValueError("storage_path must not contain '..' segments, backslashes or control characters")
        return v

    @model_validator(mode="after")
    def crop_lineage(self):
        is_crop = self.kind == ImageKind.CROP
        has_lineage = self.source_image_id is not None and self.crop_bbox is not None
        if is_crop != has_lineage:
            raise ValueError("crop images need source_image_id and crop_bbox; other kinds must not set them")
        return self


class ImageAssetUpdate(BaseModel):
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    captured_at: datetime | None = None
    metadata: dict | None = None

    @model_validator(mode="after")
    def no_null_required(self):
        reject_nulls(self, "metadata")
        return self


class ImageAssetRead(Timestamped):
    kind: ImageKind
    storage_bucket: str
    storage_path: str
    content_type: str
    size_bytes: int | None
    width: int | None
    height: int | None
    sha256: str | None
    captured_at: datetime | None
    uploaded_by: str | None
    source_image_id: uuid.UUID | None
    crop_bbox: dict | None
    metadata: dict = Field(validation_alias="metadata_")


class ImageAssetResponse(Timestamped):
    """API view of an ImageAsset. Bucket and object path are internal and omitted;
    use GET /images/{id}/url for a short-lived signed URL."""

    kind: ImageKind
    content_type: str
    size_bytes: int | None
    width: int | None
    height: int | None
    sha256: str | None
    captured_at: datetime | None
    uploaded_by: str | None
    source_image_id: uuid.UUID | None
    crop_bbox: dict | None
    metadata: dict = Field(validation_alias="metadata_")


class SignedUrlResponse(BaseModel):
    """Temporary read URL for a private object. Never store it: access ends at expires_at."""

    url: str
    expires_in: int = Field(description="Seconds the URL stays valid")
    expires_at: datetime
