"""Optional curator assertions, never accepted from student requests."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, field_validator


class DegreeLevel(StrEnum):
    HIGH_SCHOOL = "high_school"
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    DOCTORATE = "doctorate"
    OTHER = "other"


class EligibilityRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_urls: list[HttpUrl] = Field(min_length=1, max_length=20)
    verified_at: date
    nationality_scope: Literal["listed_only", "any", "unknown"] = "unknown"
    field_scope: Literal["listed_only", "any", "unknown"] = "unknown"
    accepted_prior_degrees: list[DegreeLevel] | None = Field(default=None, min_length=1)
    gpa_requirement: Literal["minimum", "none", "unknown"] = "unknown"
    language_requirement: Literal["ielts_only", "none", "conditional", "unknown"] = (
        "unknown"
    )
    minimum_ielts_component: (
        Annotated[float, Field(ge=0, le=9, strict=True, allow_inf_nan=False)] | None
    ) = None
    intake_year: int | None = Field(default=None, ge=1900, le=2200, strict=True)
    call_open: StrictBool | None = None
    funding_available: StrictBool | None = None
    no_additional_admission_requirements: StrictBool = False
    no_additional_funding_requirements: StrictBool = False

    @field_validator("source_urls")
    @classmethod
    def official_https_urls(cls, values: list[HttpUrl]) -> list[HttpUrl]:
        if any(url.scheme != "https" or url.username or url.password for url in values):
            raise ValueError("Rule evidence must use HTTPS without credentials")
        return values

    @field_validator("verified_at", mode="before")
    @classmethod
    def calendar_date(cls, value: object) -> date:
        if type(value) is date:
            return value
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("Use an ISO calendar date")
        return date.fromisoformat(value)

    @field_validator("verified_at")
    @classmethod
    def not_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Rules cannot be verified in the future")
        return value
