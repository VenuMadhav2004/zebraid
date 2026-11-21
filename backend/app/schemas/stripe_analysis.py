"""Pydantic schemas for scientific stripe analyses (Member 1 + Member 2)."""
from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import AnalysisKind, RoiMode, RunStatus
from app.schemas.image_asset import CropBox


class MorphologyConfig(BaseModel):
    """Optional overrides accepted by research.member1.models.api.analyze_stripes."""

    model_config = ConfigDict(extra="forbid")

    clahe_clip_limit: float | None = Field(default=None, gt=0)
    adaptive_block_size: int | None = Field(default=None, ge=3)
    min_stripe_area: int | None = Field(default=None, ge=1)
    orientation_sigma: float | None = Field(default=None, gt=0)
    min_branch_length: int | None = Field(default=None, ge=1)

    @field_validator("clahe_clip_limit", "orientation_sigma")
    @classmethod
    def _finite(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("must be finite")
        return v


class FrequencyOptions(BaseModel):
    """Mirrors research/member2/science/request_schema_v1.json (minus roi & source_reference)."""

    model_config = ConfigDict(extra="forbid")

    filter_type: Literal["gaussian", "butterworth", "bandpass"] = "gaussian"
    cutoff_cpp: float = Field(default=0.06, ge=1e-5, le=0.5)
    band_low_cpp: float = Field(default=0.03, ge=1e-5, le=0.5)

    @field_validator("cutoff_cpp", "band_low_cpp")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("must be finite")
        return v

    @model_validator(mode="after")
    def _bandpass_order(self):
        if self.filter_type == "bandpass" and self.band_low_cpp >= self.cutoff_cpp:
            raise ValueError("band_low_cpp must be strictly less than cutoff_cpp for bandpass filtering")
        return self


class MorphologyAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: uuid.UUID
    roi: CropBox | None = None
    config: MorphologyConfig = Field(default_factory=MorphologyConfig)


class FrequencyAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: uuid.UUID
    roi: CropBox | None = None
    options: FrequencyOptions = Field(default_factory=FrequencyOptions)


class CombinedAnalysisRequest(BaseModel):
    """Submit Member 1 (morphology) + Member 2 (spatial frequency) on the same image & ROI."""

    model_config = ConfigDict(extra="forbid")

    image_id: uuid.UUID
    roi: CropBox | None = None
    morphology_config: MorphologyConfig = Field(default_factory=MorphologyConfig)
    frequency_options: FrequencyOptions = Field(default_factory=FrequencyOptions)


class CombinedAnalysisResponse(BaseModel):
    """Both queued jobs plus explicit ROI semantics caveat."""

    stripe_morphology: "AnalysisJobRead"
    spatial_frequency: "AnalysisJobRead"
    roi_semantics_note: str = (
        "Member 1 (stripe_morphology) applies the ROI as a mask on the full canonical image, "
        "whereas Member 2 (spatial_frequency) crops and analyses only the ROI pixel box."
    )


class AnalysisCapabilityItem(BaseModel):
    available: bool
    reason: str | None = None
    source_commit: str
    schema_version: str


class AnalysisLimitsRead(BaseModel):
    max_pixels: int
    max_source_pixels: int
    max_dimension: int
    queue_limit: int
    timeout_seconds: int


class AnalysisCapabilitiesResponse(BaseModel):
    stripe_morphology: AnalysisCapabilityItem
    spatial_frequency: AnalysisCapabilityItem
    limits: AnalysisLimitsRead


class AnalysisJobRead(BaseModel):
    """Client-facing analysis job object. Never exposes bucket or filesystem paths."""

    id: uuid.UUID
    image_id: uuid.UUID
    kind: AnalysisKind
    status: RunStatus
    roi: dict[str, int]
    roi_mode: RoiMode
    parameters: dict[str, Any]
    provider: dict[str, Any]
    result: dict[str, Any] | None
    artifacts: list[str]
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @classmethod
    def from_orm_job(cls, job: Any) -> "AnalysisJobRead":
        artifact_map = job.artifacts if isinstance(job.artifacts, dict) else {}
        return cls(
            id=job.id,
            image_id=job.image_asset_id,
            kind=job.kind,
            status=job.status,
            roi=job.roi,
            roi_mode=job.roi_mode,
            parameters=job.parameters,
            provider=job.provider,
            result=job.result,
            artifacts=list(artifact_map.keys()),
            error_code=job.error_code,
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            updated_at=job.updated_at,
        )
