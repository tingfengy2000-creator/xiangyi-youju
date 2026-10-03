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
    planning_mode: Literal["packages", "modules"] = "packages"
    audience: Literal["general", "family"] = "general"
    tea_preference: Literal["any", "include", "exclude"] = "any"
    min_craft_minutes: int = Field(default=0, ge=0, le=180, strict=True)
    teaching_enabled: bool = False


class Overrides(StrictModel):
    capacity: int = Field(default=12, ge=1, le=100, strict=True)
    teachers: int = Field(default=1, ge=0, le=10, strict=True)
    rooms: int = Field(default=1, ge=0, le=10, strict=True)
    reuse: bool = True


class RunInput(StrictModel):
    case_id: Literal["jinshan-paper-light"] | None = None
    demo_assumptions_confirmed: bool = False
    text: str = Field(min_length=1, max_length=1800)
    requirements: Requirements = Field(default_factory=Requirements)
    operating_overrides: Overrides = Field(default_factory=Overrides)
    constraint_resolution: Literal["ask", "form"] = "ask"
    previous_run_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class Approval(StrictModel):
    confirmed: Literal[True]
    plan_id: str = Field(pattern=r"^(light|deep|mod-[a-z0-9-]+)$", max_length=300)


class UsageChange(StrictModel):
    usage_status: Literal["available", "withdrawn", "restricted"]


class ExtractedClaim(StrictModel):
    sentence_id: str
    text: str
    query: str
    kind: Literal["cultural_fact", "public_activity_fact", "operating_promise", "user_requirement"] = Field(
        default="cultural_fact", description="文化事实、公开活动公告条件、营业/授课/收益等经营承诺、游客提出的活动要求分开；公开活动条件不等于当前资源")


class Understanding(StrictModel):
    summary: str
    audience: str
    claims: list[ExtractedClaim] = Field(min_length=1, max_length=12)


class Intent(StrictModel):
    exclude_tags: list[Literal["story", "craft", "tea", "observation", "sharing", "extension"]]
    require_tags: list[Literal["story", "craft", "tea", "observation", "sharing", "extension"]]
    min_craft_minutes: int | None = Field(ge=0, le=180)
    maximize_craft: bool
    audience: Literal["general", "family"] | None
    people: int | None = Field(ge=1, le=100)
    budget_per_person: float | None = Field(ge=0, le=10000, allow_inf_nan=False)
    available_minutes: int | None = Field(ge=1, le=720)
    ambiguities: list[str]


class NotePreferences(StrictModel):
    tea_preference: Literal["not_mentioned", "include", "exclude"] = Field(description="文字未谈茶歇为not_mentioned；明确需要为include；明确不要为exclude")
    min_craft_minutes: int | None = Field(ge=0, le=180, description="只提取明确的手作最低分钟；未提到为null")
    maximize_craft: bool = Field(description="明确要求更多手作时间才为true")
    audience: Literal["general", "family"] | None
    people: int | None = Field(ge=1, le=100)
    budget_per_person: float | None = Field(ge=0, le=10000, allow_inf_nan=False)
    available_minutes: int | None = Field(ge=1, le=720)
    ambiguities: list[str] = Field(description="仅填写真正相互矛盾或需要新增未配置服务的活动要求；编辑说明与已有资源不足均不属于歧义")


class NoteIssue(StrictModel):
    index: int = Field(ge=0)
    text: str
    category: Literal["editorial_note", "configured_resource_check", "needs_clarification"]
    reason: str


class NoteIssueReview(StrictModel):
    items: list[NoteIssue]


class ContentUnderstanding(Understanding):
    claims: list[ExtractedClaim] = Field(min_length=1, max_length=24)


class ModuleUnderstanding(ContentUnderstanding):
    intent: Intent


class Judgment(StrictModel):
    claim_id: str
    status: Literal["supported", "contradicted", "conflicting", "insufficient"]
    evidence_ids: list[str]
    reason: str
    suggested_text: str


class Audit(StrictModel):
    judgments: list[Judgment]


class Choice(StrictModel):
    plan_id: str = Field(pattern=r"^(light|deep|none|mod-[a-z0-9-]+)$", max_length=300)
    explanation: str
