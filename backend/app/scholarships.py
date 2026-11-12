"""Read-only, parameterized catalogue queries. No eligibility matching occurs here."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database import get_session
from backend.app.models import Scholarship
from backend.app.schemas import ScholarshipPage, ScholarshipQuery, ScholarshipRead

router = APIRouter(prefix="/api/scholarships", tags=["Scholarships"])
DatabaseSession = Annotated[Session, Depends(get_session)]


@router.get("", response_model=ScholarshipPage)
def list_scholarships(
    filters: Annotated[ScholarshipQuery, Query()], session: DatabaseSession
) -> ScholarshipPage:
    conditions = []
    if filters.country is not None:
        countries = func.json_each(Scholarship.destination_country).table_valued(
            "value"
        )
        conditions.append(
            select(1)
            .select_from(countries)
            .where(func.casefold(countries.c.value) == filters.country.casefold())
            .exists()
        )
    if filters.field is not None:
        fields = func.json_each(Scholarship.eligible_study_fields).table_valued("value")
        conditions.append(
            select(1)
            .select_from(fields)
            .where(
                func.instr(func.casefold(fields.c.value), filters.field.casefold()) > 0
            )
            .exists()
        )
    if filters.funding_type is not None:
        conditions.append(Scholarship.funding_type == filters.funding_type.value)

    total = session.scalar(
        select(func.count()).select_from(Scholarship).where(*conditions)
    )
    records = session.scalars(
        select(Scholarship)
        .where(*conditions)
        .order_by(Scholarship.id)
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).all()
    return ScholarshipPage(
        items=[ScholarshipRead.model_validate(record) for record in records],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


@router.get("/{scholarship_id}", response_model=ScholarshipRead)
def get_scholarship(
    scholarship_id: Annotated[int, Path(gt=0, le=2**63 - 1)], session: DatabaseSession
) -> ScholarshipRead:
    record = session.get(Scholarship, scholarship_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    return ScholarshipRead.model_validate(record)
