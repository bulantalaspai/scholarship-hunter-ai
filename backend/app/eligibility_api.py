"""Stateless eligibility and grouped recommendations over the local catalogue."""

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from backend.app.eligibility import evaluate_eligibility, rank_programmes
from backend.app.eligibility_schemas import (
    EligibilityRequest,
    EligibilityResult,
    EligibilityStatus,
    MatchRequest,
    MatchResult,
)
from backend.app.models import Scholarship, ScholarshipEligibilityPolicy
from backend.app.schemas import ScholarshipRead
from backend.app.scholarships import DatabaseSession

router = APIRouter(prefix="/api/eligibility", tags=["Eligibility"])


def evaluation_date() -> date:
    """Use a server-controlled UTC date, never a student-provided date."""
    return datetime.now(UTC).date()


EvaluationDate = Annotated[date, Depends(evaluation_date)]


@router.post("/check", response_model=EligibilityResult)
def check_eligibility(
    request: EligibilityRequest,
    session: DatabaseSession,
    today: EvaluationDate,
) -> EligibilityResult:
    scholarship = session.get(Scholarship, request.scholarship_id)
    if scholarship is None:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    policy = session.get(ScholarshipEligibilityPolicy, scholarship.identity_key)
    return evaluate_eligibility(
        request.profile,
        ScholarshipRead.model_validate(scholarship),
        policy,
        today=today,
    )


@router.post("/matches", response_model=MatchResult)
def match_profile(
    request: MatchRequest,
    session: DatabaseSession,
    today: EvaluationDate,
) -> MatchResult:
    # One outer join avoids per-record database queries; no profile is persisted.
    rows = session.execute(
        select(Scholarship, ScholarshipEligibilityPolicy).outerjoin(
            ScholarshipEligibilityPolicy,
            Scholarship.identity_key == ScholarshipEligibilityPolicy.identity_key,
        )
    ).all()
    ranked = rank_programmes(
        request.profile,
        [(ScholarshipRead.model_validate(record), policy) for record, policy in rows],
        today=today,
    )
    counts = {
        status: sum(item.assessment.status == status for item in ranked)
        for status in EligibilityStatus
    }
    start = (request.page - 1) * request.page_size
    page = ranked[start : start + request.page_size]
    return MatchResult(
        **{
            status.value: [item for item in page if item.assessment.status == status]
            for status in EligibilityStatus
        },
        counts=counts,
        total=len(ranked),
        page=request.page,
        page_size=request.page_size,
    )
