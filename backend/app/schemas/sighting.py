import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Timestamped, reject_nulls


class SightingCreate(BaseModel):
    observed_at: datetime
    zebra_id: uuid.UUID | None = None
    image_asset_id: uuid.UUID | None = None
    identification_run_id: uuid.UUID | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_name: str | None = Field(default=None, max_length=200)
    observer: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def coords_paired(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be given together")
        return self


class SightingUpdate(BaseModel):
    """PATCH semantics: omitted fields are unchanged. zebra_id=null marks the
    sighting unidentified. latitude/longitude must be sent together (both null clears)."""

    zebra_id: uuid.UUID | None = None
    observed_at: datetime | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_name: str | None = Field(default=None, max_length=200)
    observer: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    metadata: dict | None = None

    @model_validator(mode="after")
    def check(self):
        reject_nulls(self, "observed_at", "metadata")
        sent = {"latitude", "longitude"} & self.model_fields_set
        if sent and (len(sent) == 1 or (self.latitude is None) != (self.longitude is None)):
            raise ValueError("latitude and longitude must be given together")
        return self


class SightingRead(Timestamped):
    zebra_id: uuid.UUID | None
    image_asset_id: uuid.UUID | None
    identification_run_id: uuid.UUID | None
    observed_at: datetime
    latitude: float | None
    longitude: float | None
    location_name: str | None
    observer: str | None
    notes: str | None
    metadata: dict = Field(validation_alias="metadata_")
