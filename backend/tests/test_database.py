import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.database import create_database_engine, initialize_database
from backend.app.models import Scholarship


def test_creates_schema_with_all_required_columns(engine):
    columns = {column["name"] for column in inspect(engine).get_columns("scholarships")}
    assert columns >= {
        "id",
        "scholarship_name",
        "university_or_provider",
        "destination_country",
        "degree_level",
        "eligible_study_fields",
        "eligible_nationalities",
        "minimum_gpa",
        "gpa_scale",
        "minimum_ielts",
        "funding_type",
        "tuition_coverage",
        "living_stipend",
        "application_deadline",
        "application_cycle",
        "official_source_url",
        "last_verified_at",
        "additional_requirements",
        "notes",
    }


def test_initialization_is_nondestructive_and_persists_on_reconnect(seeded_engine):
    initialize_database(seeded_engine)
    another_engine = create_database_engine(seeded_engine.url.database)
    try:
        with Session(another_engine) as session:
            assert len(session.scalars(select(Scholarship)).all()) == 3
    finally:
        another_engine.dispose()


def test_unique_constraint_prevents_direct_duplicate_insertion(
    seeded_engine, catalogue
):
    with Session(seeded_engine) as session, pytest.raises(IntegrityError):
        session.add(Scholarship(**catalogue.scholarships[0].database_values()))
        session.commit()


@pytest.mark.parametrize(
    "changes",
    [
        {"minimum_gpa": -1},
        {"minimum_gpa": 5, "gpa_scale": 4},
        {"gpa_scale": None},
        {"minimum_ielts": 10},
        {"funding_type": "unverified_value"},
        {"tuition_coverage": None},
        {"destination_country": []},
        {"eligible_study_fields": []},
        {"scholarship_name": "   "},
    ],
)
def test_database_constraints_reject_invalid_records(engine, catalogue, changes):
    values = catalogue.scholarships[0].database_values() | changes
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(Scholarship(**values))
        session.commit()


@pytest.mark.parametrize(
    "path", ["https://example.org/db", "//server/db", "\\\\server\\db", ""]
)
def test_only_local_database_file_paths_are_accepted(path):
    with pytest.raises(ValueError, match="local SQLite file"):
        create_database_engine(path)
