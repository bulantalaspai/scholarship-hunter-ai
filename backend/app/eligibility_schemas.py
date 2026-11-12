"""Stateless student inputs and explainable eligibility responses."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, model_validator

from backend.app.eligibility_rules import DegreeLevel
from backend.app.schemas import NonnegativeNumber, ShortText


class FundingPreference(StrEnum):
    FULLY_FUNDED = "fully_funded"
    ANY_FUNDING = "any_funding"


class StudentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nationality: ShortText
    degree_level: DegreeLevel
    degree_completed: StrictBool | None = None
    field_of_study: ShortText
    gpa: NonnegativeNumber | None = None
    gpa_scale: (
        Annotated[float, Field(gt=0, strict=True, allow_inf_nan=False)] | None
    ) = None
    ielts_overall: (
        Annotated[float, Field(ge=0, le=9, strict=True, allow_inf_nan=False)] | None
    ) = None
    intended_start_year: int = Field(ge=1900, le=2200, strict=True)
    funding_preference: FundingPreference

    @model_validator(mode="after")
    def consistent_gpa(self) -> Self:
        if (self.gpa is None) != (self.gpa_scale is None):
            raise ValueError("Provide GPA and its scale together, or omit both")
        if self.gpa is not None and self.gpa > self.gpa_scale:
            raise ValueError("GPA cannot exceed its scale")
        return self


class EligibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scholarship_id: int = Field(gt=0, le=2**63 - 1, strict=True)
    profile: StudentProfile


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    NEEDS_VERIFICATION = "needs_verification"


class RequirementResult(BaseModel):
    requirement: str
    scope: Literal["admission", "funding", "application"]
    status: Literal["met", "failed", "unknown"]
    explanation: str
    suggestion: str | None = None


class EligibilityResult(BaseModel):
    scholarship_id: int
    scholarship_name: str
    status: EligibilityStatus
    admission_status: EligibilityStatus
    funding_status: EligibilityStatus
    application_status: EligibilityStatus
    requirements: list[RequirementResult]
    matched_requirements: list[str]
    failed_requirements: list[str]
    unknown_requirements: list[str]
    suggestions: list[str]
    explanation: str
    official_source_url: HttpUrl
    last_verified_at: date
    rule_source_urls: list[HttpUrl]
    rules_verified_at: date | None
    evaluated_on: date
    disclaimer: str = (
        "A rules-based assessment is not an admission decision or a scholarship award. "
        "Confirm all conditions with the official provider."
    )


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: StudentProfile
    page: int = Field(default=1, ge=1, le=1_000_000, strict=True)
    page_size: int = Field(default=20, ge=1, le=100, strict=True)


class RankedProgramme(BaseModel):
    assessment: EligibilityResult
    ranking_reasons: list[str]


class MatchResult(BaseModel):
    eligible: list[RankedProgramme]
    needs_verification: list[RankedProgramme]
    ineligible: list[RankedProgramme]
    counts: dict[EligibilityStatus, int]
    total: int
    page: int
    page_size: int
