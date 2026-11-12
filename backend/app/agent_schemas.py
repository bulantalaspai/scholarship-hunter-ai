"""Local agent contracts. The model can select IDs, never write factual output."""

from datetime import date, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.app.eligibility_schemas import RankedProgramme, StudentProfile
from backend.app.schemas import FundingType, SearchText

MODEL = "qwen3:4b-instruct"
MAX_STEPS = 4
MAX_TOOL_CALLS = 8
CONTEXT_TOKENS = 4096
MAX_IDS = 3
ScholarshipId = Annotated[int, Field(gt=0, le=2**63 - 1, strict=True)]


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: StudentProfile
    goal: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ] = "Find master's scholarships matching my profile."

    @model_validator(mode="after")
    def compact_profile(self) -> Self:
        if len(self.profile.model_dump_json().encode("utf-8")) > 1500:
            raise ValueError(
                "Profile is too large for the local 4096-token agent context"
            )
        return self


class ToolTrace(BaseModel):
    step: int = Field(ge=1, le=MAX_STEPS)
    name: str = Field(max_length=64)
    status: Literal["ok", "invalid_arguments", "blocked", "error", "unknown_tool"]
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str
    source_url: str | None = None
    fetched_at: datetime | None = None


class AgentResponse(BaseModel):
    status: Literal["completed", "needs_verification", "limit_reached", "no_matches"]
    model: Literal["qwen3:4b-instruct"] = MODEL
    evaluated_on: date
    steps: int = Field(ge=0, le=MAX_STEPS)
    tool_calls: int = Field(ge=0, le=MAX_TOOL_CALLS)
    recommendations: list[RankedProgramme] = Field(max_length=MAX_IDS)
    fallback_recommendations: list[RankedProgramme] = Field(
        default_factory=list, max_length=MAX_IDS
    )
    fallback_reason: str | None = None
    message: str
    warnings: list[str]
    tool_trace: list[ToolTrace] = Field(max_length=MAX_TOOL_CALLS)
    disclaimer: str = (
        "AI selects candidates, not eligibility. Confirm official requirements; "
        "no admission or funding award is guaranteed."
    )


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchArguments(ToolArguments):
    country: SearchText | None = None
    field: SearchText | None = None
    funding_type: FundingType | None = None


class FetchArguments(ToolArguments):
    url: Annotated[str, StringConstraints(min_length=1, max_length=2048)]


class CheckArguments(ToolArguments):
    scholarship_id: ScholarshipId


class RankArguments(ToolArguments):
    scholarship_ids: list[ScholarshipId] = Field(min_length=1, max_length=MAX_IDS)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len(set(self.scholarship_ids)) != len(self.scholarship_ids):
            raise ValueError("Duplicate IDs are not allowed")
        return self


class FinalSelection(ToolArguments):
    recommendation_ids: list[ScholarshipId] = Field(max_length=MAX_IDS)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len(set(self.recommendation_ids)) != len(self.recommendation_ids):
            raise ValueError("Duplicate IDs are not allowed")
        return self
