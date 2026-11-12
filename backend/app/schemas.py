"""Validated import and API contracts, with explicit unknown values."""

import hashlib
import json
import unicodedata
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)

ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]
LongText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]
TextList = Annotated[list[ShortText], Field(min_length=1, max_length=300)]
SearchText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
NonnegativeNumber = Annotated[float, Field(ge=0, strict=True, allow_inf_nan=False)]


class FundingType(StrEnum):
    FULLY_FUNDED = "fully_funded"
    PARTIALLY_FUNDED = "partially_funded"
    UNKNOWN = "unknown"


class ScholarshipInput(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    scholarship_name: ShortText
    university_or_provider: ShortText
    destination_country: TextList | None = None
    degree_level: ShortText | None = None
    eligible_study_fields: TextList | None = None
    eligible_nationalities: TextList | None = None
    minimum_gpa: NonnegativeNumber | None = None
    gpa_scale: (
        Annotated[float, Field(gt=0, strict=True, allow_inf_nan=False)] | None
    ) = None
    minimum_ielts: (
        Annotated[float, Field(ge=0, le=9, strict=True, allow_inf_nan=False)] | None
    ) = None
    funding_type: FundingType = FundingType.UNKNOWN
    tuition_coverage: LongText | None = None
    living_stipend: LongText | None = None
    application_deadline: date | None = None
    application_cycle: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
        ]
        | None
    ) = None
    official_source_url: HttpUrl = Field(max_length=2048)
    last_verified_at: date
    additional_requirements: LongText | None = None
    notes: LongText | None = None

    @field_validator("destination_country", mode="before")
    @classmethod
    def accept_single_country(cls, value: object) -> object:
        return [value] if isinstance(value, str) else value

    @field_validator(
        "destination_country", "eligible_study_fields", "eligible_nationalities"
    )
    @classmethod
    def deduplicate_values(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unique = {}
        for item in value:
            unique.setdefault(item.casefold(), item)
        return list(unique.values())

    @field_validator("official_source_url")
    @classmethod
    def validate_source_url(cls, value: HttpUrl) -> HttpUrl:
        if (
            value.scheme != "https"
            or value.username
            or value.password
            or value.fragment
        ):
            raise ValueError(
                "Source URL must use HTTPS without credentials or a fragment"
            )
        return value

    @field_validator("application_deadline", "last_verified_at", mode="before")
    @classmethod
    def require_calendar_date(cls, value: object) -> date | None:
        if value is None or type(value) is date:
            return value
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("Use an ISO calendar date (YYYY-MM-DD), not a timestamp")
        return date.fromisoformat(value)

    @field_validator("last_verified_at")
    @classmethod
    def reject_future_verification(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Verification date cannot be in the future")
        return value

    @model_validator(mode="after")
    def validate_requirements(self) -> Self:
        if self.minimum_gpa is not None and (
            self.gpa_scale is None or self.minimum_gpa > self.gpa_scale
        ):
            raise ValueError(
                "A minimum GPA requires a known scale and cannot exceed it"
            )
        if self.funding_type == FundingType.FULLY_FUNDED and (
            self.tuition_coverage is None or self.living_stipend is None
        ):
            raise ValueError(
                "Fully funded records need verified tuition and stipend details"
            )
        return self

    @property
    def identity_key(self) -> str:
        parts = [
            self.scholarship_name,
            self.university_or_provider,
            self.application_cycle or "",
        ]
        normalized = [
            unicodedata.normalize("NFKC", " ".join(part.split())).casefold()
            for part in parts
        ]
        return hashlib.sha256(
            json.dumps(normalized, ensure_ascii=False).encode()
        ).hexdigest()

    def database_values(self) -> dict:
        values = self.model_dump()
        values["official_source_url"] = str(self.official_source_url)
        values["funding_type"] = self.funding_type.value
        return {**values, "identity_key": self.identity_key}


class ScholarshipRead(ScholarshipInput):
    id: int = Field(gt=0)


class ScholarshipPage(BaseModel):
    items: list[ScholarshipRead]
    total: int
    page: int
    page_size: int


class ScholarshipQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country: SearchText | None = None
    field: SearchText | None = None
    funding_type: FundingType | None = None
    page: int = Field(default=1, ge=1, le=1_000_000)
    page_size: int = Field(default=20, ge=1, le=100)


class CatalogueImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    data_kind: Literal["curated", "fictional_demo"]
    scholarships: list[ScholarshipInput] = Field(max_length=10_000)


class ImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_older: int = 0
