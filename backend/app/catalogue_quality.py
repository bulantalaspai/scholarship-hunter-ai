"""Reproducible, offline catalogue completeness and provenance reporting.

Documented source reviews are not proof that an applicant meets all conditions.
NULL values and conditional rules remain unresolved rather than being waived.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationError,
    field_validator,
)

from backend.app.eligibility import MAX_RULE_AGE_DAYS, normalized
from backend.app.import_catalogue import load_catalogue
from backend.app.schemas import (
    CatalogueImport,
    CatalogueRecord,
    FundingType,
    LongText,
    ShortText,
)

DEFAULT_CATALOGUE = (
    Path(__file__).resolve().parents[1] / "data" / "curated_scholarships.json"
)
COMPLETENESS_FIELDS = (
    "destination_country",
    "degree_level",
    "eligible_study_fields",
    "eligible_nationalities",
    "minimum_gpa",
    "gpa_scale",
    "minimum_ielts",
    "tuition_coverage",
    "living_stipend",
    "application_deadline",
    "application_cycle",
    "additional_requirements",
)


class SourceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    claims: LongText

    @field_validator("url")
    @classmethod
    def public_evidence_url(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https" or value.username or value.password:
            raise ValueError("Evidence requires HTTPS without credentials")
        return value


class ProgrammeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scholarship_name: ShortText
    sources: list[SourceEvidence] = Field(min_length=1)
    gaps: list[str] = Field(default_factory=list)


class EvidenceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[ProgrammeEvidence]


def unresolved_rule_conditions(record: CatalogueRecord, as_of: date) -> list[str]:
    """Review completeness only; no synthetic applicant or eligibility verdict."""
    rules = record.eligibility_rules
    if rules is None:
        return ["structured_eligibility_rules_not_reviewed"]
    gaps = []
    age = (as_of - rules.verified_at).days
    if not 0 <= age <= MAX_RULE_AGE_DAYS:
        gaps.append("rule_review_outside_current_review_window")
    for name in ("nationality_scope", "field_scope", "gpa_requirement"):
        if getattr(rules, name) == "unknown":
            gaps.append(name)
    if rules.accepted_prior_degrees is None:
        gaps.append("accepted_prior_degrees")
    if rules.language_requirement in {"unknown", "conditional"}:
        gaps.append("language_conditions")
    if rules.minimum_ielts_component is not None:
        gaps.append("language_component_evidence_not_modelled_in_student_profile")
    for name in ("intake_year", "call_open", "funding_available"):
        if getattr(rules, name) is None:
            gaps.append(name)
    for name in (
        "no_additional_admission_requirements",
        "no_additional_funding_requirements",
    ):
        if not getattr(rules, name):
            gaps.append(name)
    if record.funding_type == FundingType.UNKNOWN:
        gaps.append("funding_type")
    return gaps


def build_quality_report(
    catalogue: CatalogueImport,
    *,
    as_of: date,
    evidence: EvidenceManifest | None = None,
) -> dict:
    records = catalogue.scholarships
    identity_counts = Counter(record.identity_key for record in records)
    programmes = defaultdict(list)
    provenance = defaultdict(list)
    if evidence is not None:
        for item in evidence.records:
            provenance[normalized(item.scholarship_name)].append(item)
    details = []
    for record in records:
        programmes[
            (
                normalized(record.scholarship_name),
                normalized(record.university_or_provider),
            )
        ].append(record)
        reviews = provenance.get(normalized(record.scholarship_name), [])
        documented = (
            any(
                str(source.url) == str(record.official_source_url)
                for review in reviews
                for source in review.sources
            )
            if evidence is not None
            else None
        )
        details.append(
            {
                "scholarship_name": record.scholarship_name,
                "university_or_provider": record.university_or_provider,
                "official_source_url": str(record.official_source_url),
                "last_verified_at": record.last_verified_at.isoformat(),
                "funding_type": record.funding_type.value,
                "application_cycle": record.application_cycle,
                "application_deadline": (
                    record.application_deadline.isoformat()
                    if record.application_deadline is not None
                    else None
                ),
                "missing_fields": [
                    name
                    for name in COMPLETENESS_FIELDS
                    if getattr(record, name) is None
                ],
                "unresolved_rule_conditions": unresolved_rule_conditions(record, as_of),
                "source_review_documented": documented,
                "documented_gaps": [gap for review in reviews for gap in review.gaps],
                "source_date_after_report_date": record.last_verified_at > as_of,
            }
        )
    dates = Counter(record.last_verified_at.isoformat() for record in records)
    funding = Counter(record.funding_type.value for record in records)
    missing = Counter(name for item in details for name in item["missing_fields"])
    needing_review = sum(bool(item["unresolved_rule_conditions"]) for item in details)
    catalogue_names = {normalized(record.scholarship_name) for record in records}
    return {
        "as_of": as_of.isoformat(),
        "total_records": len(records),
        "unique_identity_records": len(identity_counts),
        "source_metadata_complete_records": sum(
            not item["source_date_after_report_date"] for item in details
        ),
        "source_review_documented_records": (
            sum(item["source_review_documented"] is True for item in details)
            if evidence is not None
            else None
        ),
        "records_without_documented_source_review": (
            [
                item["scholarship_name"]
                for item in details
                if not item["source_review_documented"]
            ]
            if evidence is not None
            else None
        ),
        "fully_reviewed_current_rule_records": len(records) - needing_review,
        "records_requiring_further_eligibility_verification": needing_review,
        "funding_counts": {kind.value: funding[kind.value] for kind in FundingType},
        # Future deadlines do not establish that a scholarship call is open.
        "deadline_counts": {
            "past": sum(
                record.application_deadline is not None
                and record.application_deadline < as_of
                for record in records
            ),
            "today": sum(record.application_deadline == as_of for record in records),
            "future": sum(
                record.application_deadline is not None
                and record.application_deadline > as_of
                for record in records
            ),
            "unknown": sum(record.application_deadline is None for record in records),
        },
        "missing_field_counts": {name: missing[name] for name in COMPLETENESS_FIELDS},
        "verification_date_counts": dict(sorted(dates.items())),
        "earliest_verification_date": min(dates, default=None),
        "latest_verification_date": max(dates, default=None),
        "duplicate_identity_keys": [
            {"identity_key": key, "occurrences": count}
            for key, count in sorted(identity_counts.items())
            if count > 1
        ],
        "programme_provider_multiple_cycles": [
            {
                "scholarship_name": items[0].scholarship_name,
                "university_or_provider": items[0].university_or_provider,
                "application_cycles": sorted(
                    {item.application_cycle or "<unknown>" for item in items}
                ),
            }
            for _, items in sorted(programmes.items())
            if len({item.application_cycle for item in items}) > 1
        ],
        "duplicate_evidence_names": [
            key for key, items in sorted(provenance.items()) if len(items) > 1
        ],
        "unused_evidence_names": sorted(set(provenance) - catalogue_names),
        "interpretation": (
            "Source metadata and recorded official-source reviews document catalogue "
            "facts, not complete applicant eligibility. Missing numeric fields may "
            "represent unknown, conditional or non-comparable requirements; "
            "they never imply a waiver. "
            "Rule completeness is profile-independent and is not an eligible verdict. "
            "This offline report cannot independently authenticate website claims."
        ),
        "records": details,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogue", nargs="?", type=Path, default=DEFAULT_CATALOGUE)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat)
    arguments = parser.parse_args(argv)
    try:
        evidence = (
            EvidenceManifest.model_validate_json(
                arguments.evidence.read_text(encoding="utf-8-sig")
            )
            if arguments.evidence is not None
            else None
        )
        report = build_quality_report(
            load_catalogue(arguments.catalogue),
            as_of=arguments.as_of or datetime.now(UTC).date(),
            evidence=evidence,
        )
    except OSError, UnicodeError, ValidationError:
        print("Cannot read or validate catalogue/evidence inputs.", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
