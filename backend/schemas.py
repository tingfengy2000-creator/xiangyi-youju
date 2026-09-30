from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Requirements(StrictModel):
    region: str = Field(default="河北省蔚县", max_length=80)
    project: str = Field(default="剪纸", max_length=50)
    people: int = Field(default=8, ge=1, le=100, strict=True)
    budget_per_person: float = Field(default=160, ge=0, le=10000, allow_inf_nan=False)
    available_minutes: int = Field(default=150, ge=1, le=720, strict=True)
    start_time: str = Field(default="09:30", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    preferred_plan: Literal["light", "deep"] = "deep"
    note: str = Field(default="", max_length=1000)


class Overrides(StrictModel):
    capacity: int = Field(default=12, ge=1, le=100, strict=True)
    teachers: int = Field(default=1, ge=0, le=10, strict=True)
    rooms: int = Field(default=1, ge=0, le=10, strict=True)
    reuse: bool = True


class RunInput(StrictModel):
    text: str = Field(min_length=1, max_length=1800)
    requirements: Requirements = Field(default_factory=Requirements)
    operating_overrides: Overrides = Field(default_factory=Overrides)


class Approval(StrictModel):
    confirmed: Literal[True]
    plan_id: Literal["light", "deep"]


class UsageChange(StrictModel):
    usage_status: Literal["available", "withdrawn", "restricted"]


class ExtractedClaim(StrictModel):
    sentence_id: str
    text: str
    query: str


class Understanding(StrictModel):
    summary: str
    audience: str
    claims: list[ExtractedClaim] = Field(min_length=1, max_length=12)


class Judgment(StrictModel):
    claim_id: str
    status: Literal["supported", "contradicted", "conflicting", "insufficient"]
    evidence_ids: list[str]
    reason: str
    suggested_text: str


class Audit(StrictModel):
    judgments: list[Judgment]


class Choice(StrictModel):
    plan_id: Literal["light", "deep", "none"]
    explanation: str
