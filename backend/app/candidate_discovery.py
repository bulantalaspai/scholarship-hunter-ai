"""Retain deterministic candidates independently of the model's search choices."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from backend.app.agent_schemas import MAX_IDS
from backend.app.eligibility_api import match_profile
from backend.app.eligibility_schemas import (
    EligibilityStatus,
    MatchRequest,
    RankedProgramme,
    StudentProfile,
)


@dataclass(frozen=True)
class DiscoveryResult:
    candidates: list[RankedProgramme]
    candidate_ids: list[int]
    named_target: bool


def _normalized_words(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"\w+", normalized))


def discover_candidates(
    session: Session, profile: StudentProfile, today: date, goal: str
) -> DiscoveryResult:
    """Use the matching service's order and classifications without model filters.

    A goal containing a catalogue programme's full name selects that target,
    including confirmed failures. Other requests retain every candidate without
    a confirmed failure. Only the first three complete assessments are exposed
    to the bounded model context. All retained IDs remain available for auditing.
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

    normalized_goal = f" {_normalized_words(goal)} "
    named = [
        item
        for item in ranked
        if f" {_normalized_words(item.assessment.scholarship_name)} " in normalized_goal
    ]
    candidates = named or [
        item
        for item in ranked
        if item.assessment.status != EligibilityStatus.INELIGIBLE
    ]
    return DiscoveryResult(
        candidates=candidates[:MAX_IDS],
        candidate_ids=[item.assessment.scholarship_id for item in candidates],
        named_target=bool(named),
    )
