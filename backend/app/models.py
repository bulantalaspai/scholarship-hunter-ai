"""SQLite catalogue schema; NULL means unknown, never unrestricted."""

from datetime import date

from sqlalchemy import JSON, CheckConstraint, Date, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Scholarship(Base):
    __tablename__ = "scholarships"
    __table_args__ = (
        CheckConstraint("length(trim(scholarship_name)) > 0", name="nonempty_name"),
        CheckConstraint(
            "length(trim(university_or_provider)) > 0", name="nonempty_provider"
        ),
        CheckConstraint(
            "funding_type IN ('fully_funded', 'partially_funded', 'unknown')",
            name="valid_funding_type",
        ),
        CheckConstraint(
            "minimum_gpa IS NULL OR "
            "(minimum_gpa >= 0 AND gpa_scale IS NOT NULL AND minimum_gpa <= gpa_scale)",
            name="valid_gpa",
        ),
        CheckConstraint(
            "gpa_scale IS NULL OR gpa_scale > 0", name="positive_gpa_scale"
        ),
        CheckConstraint(
            "minimum_ielts IS NULL OR minimum_ielts BETWEEN 0 AND 9",
            name="valid_ielts",
        ),
        CheckConstraint(
            "funding_type != 'fully_funded' OR "
            "(tuition_coverage IS NOT NULL AND living_stipend IS NOT NULL)",
            name="funding_details_required",
        ),
        *(
            CheckConstraint(
                f"{column} IS NULL OR "
                f"(json_type({column}) = 'array' AND json_array_length({column}) > 0)",
                name=f"{column}_nonempty_array",
            )
            for column in (
                "destination_country",
                "eligible_study_fields",
                "eligible_nationalities",
            )
        ),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Internal identity: normalized programme name, provider, and application cycle.
    identity_key: Mapped[str] = mapped_column(String(64), unique=True)
    scholarship_name: Mapped[str] = mapped_column(String(300))
    university_or_provider: Mapped[str] = mapped_column(String(300))
    destination_country: Mapped[list[str] | None] = mapped_column(
        JSON(none_as_null=True)
    )
    degree_level: Mapped[str | None] = mapped_column(String(100))
    eligible_study_fields: Mapped[list[str] | None] = mapped_column(
        JSON(none_as_null=True)
    )
    eligible_nationalities: Mapped[list[str] | None] = mapped_column(
        JSON(none_as_null=True)
    )
    minimum_gpa: Mapped[float | None] = mapped_column(Float)
    gpa_scale: Mapped[float | None] = mapped_column(Float)
    minimum_ielts: Mapped[float | None] = mapped_column(Float)
    funding_type: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    tuition_coverage: Mapped[str | None] = mapped_column(Text)
    living_stipend: Mapped[str | None] = mapped_column(Text)
    application_deadline: Mapped[date | None] = mapped_column(Date)
    application_cycle: Mapped[str | None] = mapped_column(String(100))
    official_source_url: Mapped[str] = mapped_column(String(2048))
    last_verified_at: Mapped[date] = mapped_column(Date)
    additional_requirements: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class ScholarshipEligibilityPolicy(Base):
    """Additive table; existing Phase 2 databases need no column migration."""

    __tablename__ = "scholarship_eligibility_policies"

    identity_key: Mapped[str] = mapped_column(
        ForeignKey("scholarships.identity_key", ondelete="CASCADE"), primary_key=True
    )
    catalogue_fingerprint: Mapped[str] = mapped_column(String(64))
    rules: Mapped[dict] = mapped_column(JSON)
