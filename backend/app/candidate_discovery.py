"""Retain deterministic candidates independently of the model's search choices."""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agent_schemas import MAX_IDS
from backend.app.eligibility_api import match_profile
from backend.app.eligibility_schemas import (
    EligibilityStatus,
    MatchRequest,
    RankedProgramme,
    StudentProfile,
)
from backend.app.models import Scholarship
from backend.app.programme_resolution import ProgrammeResolution, resolve_programme
from backend.app.request_preferences import (
    PreferenceCheck,
    RequestPreference,
    check_preferences,
    parse_preferences,
)
from backend.app.schemas import ScholarshipRead


@dataclass(frozen=True)
class DiscoveryResult:
    candidates: list[RankedProgramme]
    candidate_ids: list[int]
    named_target: bool
    resolution: ProgrammeResolution | None = None
    records: list[ScholarshipRead] = field(default_factory=list)
    preferences: list[RequestPreference] = field(default_factory=list)
    preference_checks: dict[int, list[PreferenceCheck]] = field(default_factory=dict)
    scoped_records: list[ScholarshipRead] = field(default_factory=list)
    no_match_message: str | None = None


def rank_for_preferences(
    candidates: list[RankedProgramme], checks: dict[int, list[PreferenceCheck]]
) -> list[RankedProgramme]:
    if not checks:
        return candidates
    priority = {"eligible": 0, "needs_verification": 1, "ineligible": 2}

    def key(item: RankedProgramme) -> tuple[int, int]:
        preferred = sum(
            check.mode == "preferred" and check.status == "confirmed"
            for check in checks[item.assessment.scholarship_id]
        )
        return priority[item.assessment.status], -preferred

    # The stable sort preserves eligibility grouping and existing ranking ties.
    return sorted(candidates, key=key)


def _changed_catalogue(goal: str) -> DiscoveryResult:
    return DiscoveryResult(
        candidates=[],
        candidate_ids=[],
        named_target=False,
        resolution=ProgrammeResolution(
            status="not_found",
            query=goal.strip() or None,
            message="The catalogue changed during discovery. Retry the request.",
        ),
    )


def discover_candidates(
    session: Session, profile: StudentProfile, today: date, goal: str
) -> DiscoveryResult:
    """Scope the matching service's assessments using catalogue evidence.

    Resolved names retain the target, including confirmed failures. Ambiguous or
    unknown explicit names require clarification. Verified request constraints
    apply before seeding the model or returning deterministic candidates.
    """
    ranked: list[RankedProgramme] = []
    page_number = 1
    while True:
        result = match_profile(
            MatchRequest(profile=profile, page=page_number, page_size=100),
            session,
            today,
        )
        ranked.extend(result.eligible + result.needs_verification + result.ineligible)
        if page_number * result.page_size >= result.total:
            break
        page_number += 1

    records = [
        ScholarshipRead.model_validate(record)
        for record in session.scalars(select(Scholarship).order_by(Scholarship.id))
    ]
    by_id = {record.id: record for record in records}
    if (
        len(ranked) != len(records)
        or {item.assessment.scholarship_id for item in ranked} != set(by_id)
        or any(
            item.assessment.scholarship_name
            != by_id[item.assessment.scholarship_id].scholarship_name
            or item.assessment.official_source_url
            != by_id[item.assessment.scholarship_id].official_source_url
            or item.assessment.last_verified_at
            != by_id[item.assessment.scholarship_id].last_verified_at
            for item in ranked
        )
    ):
        return _changed_catalogue(goal)
    resolution = resolve_programme(goal, records)
    if resolution.status in {"ambiguous", "not_found"}:
        return DiscoveryResult([], [], False, resolution)
    named = [
        item
        for item in ranked
        if item.assessment.scholarship_id in resolution.candidate_ids
    ]
    if resolution.status == "matched":
        if len(named) != len(resolution.candidate_ids):
            return _changed_catalogue(goal)
        candidates = named
    else:
        candidates = [
            item
            for item in ranked
            if item.assessment.status != EligibilityStatus.INELIGIBLE
        ]
    preferences = parse_preferences(goal, records)
    checks = {}
    if preferences:
        checks = {
            identifier: check_preferences(preferences, record)
            for identifier, record in by_id.items()
        }
        candidates = [
            item
            for item in candidates
            if all(
                check.mode != "required" or check.status == "confirmed"
                for check in checks[item.assessment.scholarship_id]
            )
        ]
    ordered = rank_for_preferences(candidates, checks)
    candidate_ids = [item.assessment.scholarship_id for item in ordered]
    required = ", ".join(pref.label for pref in preferences if pref.mode == "required")
    return DiscoveryResult(
        candidates=ordered[:MAX_IDS],
        candidate_ids=candidate_ids,
        named_target=resolution.status == "matched",
        resolution=resolution,
        records=[by_id[identifier] for identifier in candidate_ids[:MAX_IDS]],
        preferences=preferences,
        preference_checks=checks,
        scoped_records=[by_id[identifier] for identifier in candidate_ids]
        if preferences
        else [],
        no_match_message=(
            f"No catalogue candidate with verified evidence for {required} "
            "could be shortlisted with this profile. Review your request and profile."
            if not candidates and required
            else None
        ),
    )
