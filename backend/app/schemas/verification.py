import uuid

from pydantic import BaseModel, Field, model_validator

from app.models.enums import VerificationDecision
from app.schemas.common import Timestamped


class VerificationCreate(BaseModel):
    """confirmed: candidate_id required (zebra taken from the candidate).
    rejected: candidate_id required. unknown: no candidate_id."""

    run_id: uuid.UUID
    decision: VerificationDecision
    candidate_id: uuid.UUID | None = None
    verified_by: str = Field(min_length=1, max_length=120)
    notes: str | None = None

    @model_validator(mode="after")
    def shape(self):
        needs_candidate = self.decision in (VerificationDecision.CONFIRMED, VerificationDecision.REJECTED)
        if needs_candidate and self.candidate_id is None:
            raise ValueError(f"{self.decision.value} requires candidate_id")
        if self.decision == VerificationDecision.UNKNOWN and self.candidate_id is not None:
            raise ValueError("unknown decision must not reference a candidate")
        return self


class VerificationSubmit(BaseModel):
    """Body of POST /identifications/{run_id}/verifications (run comes from the path).
    confirmed/rejected need candidate_id; unknown must not set it."""

    decision: VerificationDecision
    candidate_id: uuid.UUID | None = None
    verified_by: str = Field(min_length=1, max_length=120)
    notes: str | None = None


class VerificationRead(Timestamped):
    run_id: uuid.UUID
    candidate_id: uuid.UUID | None
    zebra_id: uuid.UUID | None
    decision: VerificationDecision
    verified_by: str
    notes: str | None
