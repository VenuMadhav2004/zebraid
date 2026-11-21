import uuid

from pydantic import BaseModel, Field, model_validator

from app.models.enums import FlankSide
from app.schemas.common import Timestamped, reject_nulls
from app.schemas.image_asset import ImageAssetResponse, SignedUrlResponse


class GalleryEntryCreate(BaseModel):
    zebra_id: uuid.UUID
    image_asset_id: uuid.UUID
    side: FlankSide = FlankSide.UNKNOWN
    quality_notes: str | None = None
    registered_by: str | None = Field(default=None, max_length=120)
    metadata: dict = Field(default_factory=dict)


class GalleryEntryRegister(BaseModel):
    """Body of POST /zebras/{zebra_id}/gallery (zebra comes from the path)."""

    image_asset_id: uuid.UUID
    side: FlankSide = FlankSide.UNKNOWN
    quality_notes: str | None = None
    registered_by: str | None = Field(default=None, max_length=120)
    metadata: dict = Field(default_factory=dict)


class GalleryEntryUpdate(BaseModel):
    side: FlankSide | None = None
    is_active: bool | None = None
    quality_notes: str | None = None
    metadata: dict | None = None

    @model_validator(mode="after")
    def no_null_required(self):
        reject_nulls(self, "side", "is_active", "metadata")
        return self


class GalleryEntryRead(Timestamped):
    zebra_id: uuid.UUID
    image_asset_id: uuid.UUID
    side: FlankSide
    is_active: bool
    quality_notes: str | None
    registered_by: str | None
    metadata: dict = Field(validation_alias="metadata_")


class GalleryEntryWithImage(GalleryEntryRead):
    """Gallery entry plus its image metadata and, on request, a short-lived signed URL."""

    image: ImageAssetResponse = Field(validation_alias="image_asset")
    image_url: SignedUrlResponse | None = None
