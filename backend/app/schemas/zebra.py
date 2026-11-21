from pydantic import BaseModel, Field, model_validator

from app.models.enums import ZebraStatus
from app.schemas.common import Timestamped, reject_nulls


class ZebraCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str | None = Field(default=None, max_length=120)
    species: str | None = Field(default=None, max_length=80)
    sex: str | None = Field(default=None, max_length=20)
    status: ZebraStatus = ZebraStatus.ACTIVE
    notes: str | None = None
    attributes: dict = Field(default_factory=dict)


class ZebraUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    species: str | None = Field(default=None, max_length=80)
    sex: str | None = Field(default=None, max_length=20)
    status: ZebraStatus | None = None
    notes: str | None = None
    attributes: dict | None = None

    @model_validator(mode="after")
    def no_null_required(self):
        reject_nulls(self, "status", "attributes")
        return self


class ZebraRead(Timestamped):
    code: str
    name: str | None
    species: str | None
    sex: str | None
    status: ZebraStatus
    notes: str | None
    attributes: dict
