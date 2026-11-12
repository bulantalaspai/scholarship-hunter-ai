"""Deterministic comparisons of documented facts; no free-text rule inference."""

import hashlib
import json
import unicodedata
from datetime import date

from backend.app.eligibility_schemas import (
    EligibilityResult,
    EligibilityStatus,
    FundingPreference,
    RankedProgramme,
    RequirementResult,
    StudentProfile,
)
from backend.app.models import ScholarshipEligibilityPolicy
from backend.app.schemas import CatalogueRecord, ScholarshipInput, ScholarshipRead

MAX_RULE_AGE_DAYS = 30


def normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", " ".join(value.split())).casefold()


def catalogue_fingerprint(record: ScholarshipInput) -> str:
    # Explicit base fields exclude DB identity, output ID, and nested curator rules.
    snapshot = ScholarshipInput.model_validate(
        {name: getattr(record, name) for name in ScholarshipInput.model_fields}
    ).model_dump(mode="json")
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def aggregate(results: list[RequirementResult]) -> EligibilityStatus:
    if any(result.status == "failed" for result in results):
        return EligibilityStatus.INELIGIBLE
    if not results or any(result.status == "unknown" for result in results):
        return EligibilityStatus.NEEDS_VERIFICATION
    return EligibilityStatus.ELIGIBLE


def evaluate_eligibility(
    profile: StudentProfile,
    scholarship: ScholarshipRead,
    policy: ScholarshipEligibilityPolicy | None,
    *,
    today: date,
) -> EligibilityResult:
    rules = None
    evidence_reason = "Complete structured rules have not been reviewed."
    if policy is not None:
        try:
            candidate = CatalogueRecord.model_validate(
                scholarship.model_dump(exclude={"id"})
                | {"eligibility_rules": policy.rules}
            ).eligibility_rules
            if candidate is None:
                raise ValueError("Stored rule evidence is missing")
            age = (today - candidate.verified_at).days
            if (
                policy.catalogue_fingerprint == catalogue_fingerprint(scholarship)
                and candidate.verified_at >= scholarship.last_verified_at
                and 0 <= age <= MAX_RULE_AGE_DAYS
            ):
                rules = candidate
            else:
                evidence_reason = (
                    "Rules are stale, future-dated, or do not match "
                    "the current catalogue snapshot."
                )
        except ValueError:
            evidence_reason = "Stored structured rules need curator review."

    results: list[RequirementResult] = []

    def add(name, scope, state, explanation, suggestion=None):
        results.append(
            RequirementResult(
                requirement=name,
                scope=scope,
                status=state,
                explanation=explanation,
                suggestion=suggestion,
            )
        )

    add(
        "rule_evidence",
        "application",
        "met" if rules else "unknown",
        "Reviewed rules match this snapshot and are within the 30-day review window."
        if rules
        else evidence_reason,
        None
        if rules
        else "Ask the provider or curator to verify the complete current rules.",
    )

    nationalities = {
        normalized(item) for item in scholarship.eligible_nationalities or []
    }
    nationality_scope = rules.nationality_scope if rules else "unknown"
    if (
        nationality_scope == "any"
        or "worldwide" in nationalities
        or normalized(profile.nationality) in nationalities
    ):
        add("nationality", "funding", "met", "Nationality matches the published scope.")
    elif nationality_scope == "listed_only":
        add(
            "nationality",
            "funding",
            "failed",
            "Nationality is outside the reviewed exhaustive funding list.",
        )
    else:
        add(
            "nationality",
            "funding",
            "unknown",
            "No confirmed nationality match or exhaustive exclusion is documented.",
            "Confirm nationality-specific funding eligibility.",
        )

    if scholarship.degree_level is None:
        add(
            "programme_degree",
            "admission",
            "unknown",
            "The awarded programme degree is unknown.",
        )
    elif normalized(scholarship.degree_level) in {
        "bachelor",
        "associate",
        "doctorate",
        "high_school",
    }:
        add(
            "programme_degree",
            "admission",
            "failed",
            "This is not a documented master's programme.",
        )
    elif normalized(scholarship.degree_level) == "master":
        add(
            "programme_degree",
            "admission",
            "met",
            "The award is a master's; prior qualification is checked separately.",
        )
    else:
        add(
            "programme_degree",
            "admission",
            "unknown",
            "Programme degree label is not recognized; equivalence is not inferred.",
        )

    if rules is None or rules.accepted_prior_degrees is None:
        add(
            "prior_degree",
            "admission",
            "unknown",
            "Accepted prior qualifications have not been structured and verified.",
        )
    elif profile.degree_level not in rules.accepted_prior_degrees:
        add(
            "prior_degree",
            "admission",
            "failed",
            "Qualification is outside the reviewed accepted degree levels.",
            "Check the provider's qualifying-degree requirements.",
        )
    elif profile.degree_completed is not True:
        add(
            "prior_degree",
            "admission",
            "unknown",
            "Degree matches; completion before the required date is unverified.",
            "Confirm degree completion and the provider's timing rules.",
        )
    else:
        add(
            "prior_degree",
            "admission",
            "met",
            "The completed degree matches an explicitly accepted prior qualification.",
        )

    fields = {normalized(item) for item in scholarship.eligible_study_fields or []}
    field_scope = rules.field_scope if rules else "unknown"
    if field_scope == "any" or normalized(profile.field_of_study) in fields:
        add(
            "study_field",
            "admission",
            "met",
            "Field matches a documented background or reviewed unrestricted scope.",
        )
    elif field_scope == "listed_only":
        add(
            "study_field",
            "admission",
            "failed",
            "Field is outside the reviewed exhaustive accepted-field list.",
            "Check programmes with a documented match to your academic background.",
        )
    else:
        add(
            "study_field",
            "admission",
            "unknown",
            "No exact field match is documented; related fields need review.",
            "Ask whether your field or equivalent qualification is accepted.",
        )

    if rules and rules.gpa_requirement == "none":
        add(
            "gpa",
            "admission",
            "met",
            "The curator verified that no minimum GPA applies.",
        )
    elif scholarship.minimum_gpa is None:
        add(
            "gpa",
            "admission",
            "unknown",
            "No minimum GPA or explicit absence of a minimum was verified.",
        )
    elif profile.gpa is None:
        add(
            "gpa",
            "admission",
            "unknown",
            "Student GPA and scale were not supplied.",
            "Supply your GPA and its original grading scale.",
        )
    elif profile.gpa_scale != scholarship.gpa_scale:
        add(
            "gpa",
            "admission",
            "unknown",
            "GPA scales differ; no verified conversion is available.",
            "Obtain a provider-approved grade conversion or equivalence assessment.",
        )
    elif profile.gpa < scholarship.minimum_gpa:
        add(
            "gpa",
            "admission",
            "failed",
            f"GPA {profile.gpa} is below minimum {scholarship.minimum_gpa} "
            "on the same scale.",
        )
    else:
        add(
            "gpa",
            "admission",
            "met",
            "GPA meets the documented threshold on the same grading scale.",
        )

    language = rules.language_requirement if rules else "unknown"
    if language == "none":
        add(
            "language",
            "admission",
            "met",
            "The curator verified that no language-test requirement applies.",
        )
    elif language != "ielts_only":
        add(
            "language",
            "admission",
            "unknown",
            "Language alternatives, exemptions, or test conditions are unresolved.",
            "Verify language evidence, exemptions, and required component scores.",
        )
    elif profile.ielts_overall is None:
        add(
            "language",
            "admission",
            "unknown",
            "Mandatory IELTS overall evidence was not supplied.",
            "Supply an IELTS overall result if using the required IELTS route.",
        )
    elif profile.ielts_overall < scholarship.minimum_ielts:
        add(
            "language",
            "admission",
            "failed",
            f"IELTS overall {profile.ielts_overall} is below "
            f"the mandatory minimum {scholarship.minimum_ielts}.",
            "If appropriate, improve the IELTS result before applying.",
        )
    elif rules.minimum_ielts_component is not None:
        add(
            "language",
            "admission",
            "unknown",
            "Overall IELTS meets the threshold; required component scores "
            "are not captured in this profile.",
            "Verify every required IELTS component with the provider.",
        )
    else:
        add(
            "language",
            "admission",
            "met",
            "IELTS meets the reviewed mandatory overall-only requirement.",
        )

    funding = scholarship.funding_type
    if funding == "unknown":
        add("funding_preference", "funding", "unknown", "Funding type is unknown.")
    elif (
        profile.funding_preference == FundingPreference.FULLY_FUNDED
        and funding != "fully_funded"
    ):
        add(
            "funding_preference",
            "funding",
            "failed",
            "Partial funding does not meet the full-funding preference; "
            "this is not an admission rejection.",
            "Consider partial funding only if it fits your budget and preference.",
        )
    else:
        add(
            "funding_preference",
            "funding",
            "met",
            "Funding type matches the preference, without guaranteeing an award.",
        )

    available = rules.funding_available if rules else None
    add(
        "funding_availability",
        "funding",
        "unknown" if available is None else "met" if available else "failed",
        "Funding availability for this cycle is unverified."
        if available is None
        else "Funding is advertised for this cycle; selection remains competitive."
        if available
        else "Reviewed evidence confirms funding is unavailable for this cycle.",
    )

    deadline = scholarship.application_deadline
    if deadline is None:
        add(
            "deadline",
            "application",
            "unknown",
            "The applicable deadline is unknown.",
            "Check the official deadline for your nationality and intake.",
        )
    elif deadline < today:
        add(
            "deadline",
            "application",
            "failed",
            f"Deadline {deadline.isoformat()} has passed for this record; "
            "a future cycle is not inferred.",
        )
    elif deadline == today:
        add(
            "deadline",
            "application",
            "unknown",
            "The deadline is today; cutoff time and timezone require verification.",
        )
    else:
        add(
            "deadline",
            "application",
            "met",
            "Deadline is in the future; this alone does not prove the call is open.",
        )

    if profile.intended_start_year < today.year:
        add(
            "intake",
            "application",
            "failed",
            "The requested start year has already passed.",
        )
    elif rules is None or rules.intake_year is None:
        add(
            "intake",
            "application",
            "unknown",
            "Intake year is unverified; a cycle label is not parsed into an intake.",
        )
    elif profile.intended_start_year != rules.intake_year:
        add(
            "intake",
            "application",
            "failed",
            "Requested start year differs from this record's verified intake.",
        )
    else:
        add(
            "intake",
            "application",
            "met",
            "Requested start year matches the verified intake.",
        )

    opened = rules.call_open if rules else None
    add(
        "application_open",
        "application",
        "unknown" if opened is None else "met" if opened else "failed",
        "Current opening status is unverified."
        if opened is None
        else "The call was verified open in this snapshot; reconfirm before applying."
        if opened
        else "The call is confirmed closed in the reviewed snapshot.",
    )

    for scope in ("admission", "funding"):
        complete = rules and getattr(rules, f"no_additional_{scope}_requirements")
        add(
            f"additional_{scope}_conditions",
            scope,
            "met" if complete else "unknown",
            "The curator confirmed no unmodelled mandatory conditions remain."
            if complete
            else (
                "Conditions such as admission, experience, prior awards, "
                "or language components need individual verification."
            ),
        )

    status = aggregate(results)
    return EligibilityResult(
        scholarship_id=scholarship.id,
        scholarship_name=scholarship.scholarship_name,
        status=status,
        admission_status=aggregate(
            [item for item in results if item.scope == "admission"]
        ),
        funding_status=aggregate([item for item in results if item.scope == "funding"]),
        application_status=aggregate(
            [item for item in results if item.scope == "application"]
        ),
        requirements=results,
        matched_requirements=[
            item.requirement for item in results if item.status == "met"
        ],
        failed_requirements=[
            item.requirement for item in results if item.status == "failed"
        ],
        unknown_requirements=[
            item.requirement for item in results if item.status == "unknown"
        ],
        suggestions=list(
            dict.fromkeys(item.suggestion for item in results if item.suggestion)
        ),
        explanation={
            EligibilityStatus.ELIGIBLE: (
                "All modeled mandatory requirements are positively verified "
                "in the current snapshot."
            ),
            EligibilityStatus.INELIGIBLE: (
                "At least one confirmed condition fails for this record "
                "and the supplied preferences; unresolved conditions remain visible."
            ),
            EligibilityStatus.NEEDS_VERIFICATION: (
                "No confirmed failure was found, "
                "but mandatory conditions remain unverified."
            ),
        }[status],
        official_source_url=scholarship.official_source_url,
        last_verified_at=scholarship.last_verified_at,
        rule_source_urls=rules.source_urls if rules else [],
        rules_verified_at=rules.verified_at if rules else None,
        evaluated_on=today,
    )


def rank_programmes(
    profile: StudentProfile,
    candidates: list[tuple[ScholarshipRead, ScholarshipEligibilityPolicy | None]],
    *,
    today: date,
) -> list[RankedProgramme]:
    ranked = []
    for scholarship, policy in candidates:
        result = evaluate_eligibility(profile, scholarship, policy, today=today)
        exact_field = normalized(profile.field_of_study) in {
            normalized(item) for item in scholarship.eligible_study_fields or []
        }
        funding_priority = {"fully_funded": 2, "partially_funded": 1, "unknown": 0}[
            scholarship.funding_type
        ]
        reasons = [
            f"Eligibility group: {result.status.value}.",
            f"Published funding: {scholarship.funding_type.value}; "
            "award not guaranteed.",
        ]
        if exact_field:
            reasons.append("Exact documented study-field match.")
        key = (
            {"eligible": 0, "needs_verification": 1, "ineligible": 2}[result.status],
            -funding_priority,
            -int(exact_field),
            scholarship.id,
        )
        ranked.append(
            (key, RankedProgramme(assessment=result, ranking_reasons=reasons))
        )
    return [item for _, item in sorted(ranked, key=lambda pair: pair[0])]
