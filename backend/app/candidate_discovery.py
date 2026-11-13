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
from backend.app.schemas import ScholarshipRead


@dataclass(frozen=True)
class DiscoveryResult:
    candidates: list[RankedProgramme]
    candidate_ids: list[int]
    named_target: bool
    resolution: ProgrammeResolution | None = None
    records: list[ScholarshipRead] = field(default_factory=list)


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
    """Use the matching service's order and classifications without model filters.

    Resolved names retain the target, including confirmed failures. Ambiguous or
    unknown explicit names require clarification. General discovery retains every
    candidate without a confirmed failure. The first three complete assessments
    enter the bounded model context. All retained IDs remain available for auditing.
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
    retained = candidates[:MAX_IDS]
    return DiscoveryResult(
        candidates=retained,
        candidate_ids=[item.assessment.scholarship_id for item in candidates],
        named_target=bool(named),
        resolution=resolution,
        records=[by_id[item.assessment.scholarship_id] for item in retained],
    )
