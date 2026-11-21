import math
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import RunStatus
from app.schemas.common import Timestamped


class RecognitionCapabilityResponse(BaseModel):
    available: bool
    model_name: str
    model_revision: str
    checkpoint_sha256: str
    preprocessing: str
    device: str = "cpu"
    gallery_cache_enabled: bool
    reason: str | None = None
    # Weights in memory of this API process: idle (not loaded yet) | loading | loaded | failed
    model_state: str = "idle"
    model_load_seconds: float | None = None


class IdentificationSubmitRequest(BaseModel):
    """Submit a stored query or crop image for MegaDescriptor-L-384 v1 candidate retrieval."""

    model_config = ConfigDict(extra="forbid")

    query_image_id: uuid.UUID
    top_k: int = Field(default=5, ge=1, le=20)
    requested_by: str | None = Field(default=None, min_length=1, max_length=120)


class IdentificationRunCreate(BaseModel):
    query_image_id: uuid.UUID
    model_name: str = Field(min_length=1, max_length=200)
    model_version: str | None = Field(default=None, max_length=300)
    parameters: dict = Field(default_factory=dict)
    requested_by: str | None = Field(default=None, max_length=120)


class IdentificationRunRead(Timestamped):
    query_image_id: uuid.UUID
    status: RunStatus
    model_name: str
    model_version: str | None
    parameters: dict
    processing_metadata: dict
    predicted_unknown: bool | None
    error_code: str | None
    error_message: str | None
    requested_by: str | None
    started_at: datetime | None
    completed_at: datetime | None


class CandidateCreate(BaseModel):
    """One ranked suggestion. Provide zebra_id when the ML label maps to a registered
    Zebra; otherwise external_label keeps the raw label (unknown identity)."""

    rank: int = Field(ge=1)
    similarity_score: float
    zebra_id: uuid.UUID | None = None
    external_label: str | None = Field(default=None, max_length=200)
    score_type: str | None = Field(default=None, max_length=80)
    matched_reference_image_id: uuid.UUID | None = None
    evidence: dict = Field(default_factory=dict)

    @field_validator("similarity_score")
    @classmethod
    def finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("similarity_score must be finite")
        return v

    @model_validator(mode="after")
    def has_identity(self):
        if self.zebra_id is None and not self.external_label:
            raise ValueError("candidate needs zebra_id or external_label")
        return self


class CandidateRead(Timestamped):
    run_id: uuid.UUID
    rank: int
    zebra_id: uuid.UUID | None
    external_label: str | None
    similarity_score: float
    score_type: str | None
    matched_reference_image_id: uuid.UUID | None
    evidence: dict


class RunCompletion(BaseModel):
    candidates: list[CandidateCreate] = Field(default_factory=list)
    processing_metadata: dict = Field(default_factory=dict)
    predicted_unknown: bool | None = None
    model_version: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def ranks_unique(self):
        ranks = [c.rank for c in self.candidates]
        if len(ranks) != len(set(ranks)):
            raise ValueError("candidate ranks must be unique within a run")
        return self


class RunFailure(BaseModel):
    error_message: str = Field(min_length=1)
    error_code: str | None = Field(default=None, max_length=80)
    processing_metadata: dict = Field(default_factory=dict)


class IdentificationRunDetail(IdentificationRunRead):
    candidates: list[CandidateRead]
