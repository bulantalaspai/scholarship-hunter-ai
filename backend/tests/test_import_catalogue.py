import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.import_catalogue import import_catalogue, load_catalogue, main
from backend.app.models import Scholarship
from backend.app.schemas import CatalogueImport, ScholarshipInput
from backend.tests.conftest import FIXTURE_PATH

CURATED_PATH = Path(__file__).parents[1] / "data" / "curated_scholarships.json"


def rows(engine):
    with Session(engine) as session:
        return session.scalars(select(Scholarship).order_by(Scholarship.id)).all()


def modified_catalogue(catalogue, index=0, **changes):
    values = catalogue.model_dump()
    values["scholarships"][index].update(changes)
    return CatalogueImport.model_validate(values)


def test_imports_fixture_only_with_explicit_demo_opt_in(engine, catalogue):
    with pytest.raises(ValueError, match="Fictional demo"):
        import_catalogue(engine, catalogue)
    assert rows(engine) == []
    result = import_catalogue(engine, catalogue, allow_demo=True)
    assert result.created == 3
    assert len(rows(engine)) == 3


def test_repeated_import_is_idempotent_and_keeps_ids(seeded_engine, catalogue):
    before = [row.id for row in rows(seeded_engine)]
    result = import_catalogue(seeded_engine, catalogue, allow_demo=True)
    assert result.model_dump() == {
        "created": 0,
        "updated": 0,
        "unchanged": 3,
        "skipped_older": 0,
    }
    assert [row.id for row in rows(seeded_engine)] == before


def test_normalized_identity_prevents_case_and_whitespace_duplicates(
    seeded_engine, catalogue
):
    changed = modified_catalogue(
        catalogue,
        scholarship_name="  FICTIONAL   DEMO engineering award ",
        university_or_provider="fictional demo university",
    )
    result = import_catalogue(seeded_engine, changed, allow_demo=True)
    assert result.updated == 1
    assert len(rows(seeded_engine)) == 3
    assert rows(seeded_engine)[0].id == 1


def test_different_application_cycles_are_separate_awards(seeded_engine, catalogue):
    changed = modified_catalogue(catalogue, application_cycle="2028-2029")
    result = import_catalogue(seeded_engine, changed, allow_demo=True)
    assert result.created == 1
    assert len(rows(seeded_engine)) == 4


def test_identical_duplicates_within_a_file_are_collapsed(engine, catalogue):
    values = catalogue.model_dump()
    values["scholarships"].append(values["scholarships"][0].copy())
    duplicated = CatalogueImport.model_validate(values)
    result = import_catalogue(engine, duplicated, allow_demo=True)
    assert result.created == 3
    assert len(rows(engine)) == 3


def test_conflicting_duplicates_reject_entire_import(engine, catalogue):
    values = catalogue.model_dump()
    values["scholarships"].append(values["scholarships"][0] | {"minimum_ielts": 7.0})
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        import_catalogue(
            engine, CatalogueImport.model_validate(values), allow_demo=True
        )
    assert rows(engine) == []


def test_more_recent_facts_update_existing_record_and_source_url(
    seeded_engine, catalogue
):
    changed = modified_catalogue(
        catalogue,
        last_verified_at=date(2026, 1, 2),
        minimum_ielts=7.0,
        official_source_url="https://example.org/fictional-revised",
    )
    result = import_catalogue(seeded_engine, changed, allow_demo=True)
    updated = rows(seeded_engine)[0]
    assert result.updated == 1
    assert updated.id == 1
    assert updated.minimum_ielts == 7.0
    assert updated.official_source_url == "https://example.org/fictional-revised"


def test_older_verification_does_not_replace_newer_data(seeded_engine, catalogue):
    changed = modified_catalogue(
        catalogue, last_verified_at=date(2025, 1, 1), minimum_ielts=7.0
    )
    result = import_catalogue(seeded_engine, changed, allow_demo=True)
    assert result.skipped_older == 1
    assert rows(seeded_engine)[0].minimum_ielts == 6.5


def test_database_failure_rolls_back_all_records(engine, catalogue):
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER reject_test_record BEFORE INSERT ON scholarships "
            "WHEN NEW.scholarship_name = 'Fictional Demo Arts Grant' "
            "BEGIN SELECT RAISE(ABORT, 'intentional test failure'); END"
        )
    with pytest.raises(IntegrityError, match="intentional test failure"):
        import_catalogue(engine, catalogue, allow_demo=True)
    assert rows(engine) == []


def test_cli_initializes_and_imports_real_curated_file_idempotently(tmp_path, capsys):
    database_path = tmp_path / "cli.sqlite3"
    common = ["--database-path", str(database_path)]
    assert main([*common, "init"]) == 0
    assert database_path.is_file()
    capsys.readouterr()
    assert main([*common, "import", str(CURATED_PATH)]) == 0
    count = len(load_catalogue(CURATED_PATH).scholarships)
    assert json.loads(capsys.readouterr().out)["created"] == count
    assert main([*common, "import", str(CURATED_PATH)]) == 0
    assert json.loads(capsys.readouterr().out)["unchanged"] == count


def test_cli_rejects_fixture_before_creating_database(tmp_path, capsys):
    database_path = tmp_path / "not-created.sqlite3"
    assert (
        main(["--database-path", str(database_path), "import", str(FIXTURE_PATH)]) == 1
    )
    assert "Fictional demo" in capsys.readouterr().err
    assert not database_path.exists()


def test_invalid_record_causes_no_partial_import(
    seeded_engine, catalogue, tmp_path, capsys
):
    values = catalogue.model_dump(mode="json")
    values["data_kind"] = "curated"
    values["scholarships"][0]["minimum_ielts"] = 7.0
    values["scholarships"][1]["last_verified_at"] = "not-a-date"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    assert (
        main(["--database-path", seeded_engine.url.database, "import", str(path)]) == 1
    )
    assert capsys.readouterr().err
    assert rows(seeded_engine)[0].minimum_ielts == 6.5


@pytest.mark.parametrize(
    "text", ["not JSON", "[]", '{"schema_version": 2}', '{"scholarships": []}']
)
def test_rejects_invalid_import_documents(tmp_path, text):
    path = tmp_path / "invalid.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_catalogue(path)


def test_unknown_requirements_remain_null_after_import(seeded_engine):
    unknown = rows(seeded_engine)[2]
    assert unknown.minimum_gpa is None
    assert unknown.gpa_scale is None
    assert unknown.minimum_ielts is None
    assert unknown.eligible_nationalities is None
    assert unknown.eligible_study_fields is None
    assert unknown.application_deadline is None
    assert unknown.funding_type == "unknown"


@pytest.mark.parametrize(
    "changes",
    [
        {"scholarship_name": " "},
        {"minimum_gpa": -0.1},
        {"minimum_gpa": 5.0, "gpa_scale": 4.0},
        {"gpa_scale": None},
        {"gpa_scale": 0.0},
        {"minimum_ielts": 9.5},
        {"minimum_ielts": True},
        {"minimum_gpa": float("nan")},
        {"funding_type": "probably_full"},
        {"tuition_coverage": None},
        {"living_stipend": None},
        {"destination_country": []},
        {"eligible_study_fields": []},
        {"eligible_nationalities": []},
        {"official_source_url": "not-a-url"},
        {"official_source_url": "http://example.org/test"},
        {"official_source_url": "https://user:password@example.org/test"},
        {"last_verified_at": "9999-01-01"},
        {"last_verified_at": None},
        {"last_verified_at": 0},
        {"application_deadline": 0},
        {"application_deadline": "2027-01-01T00:00:00"},
        {"unrecognized_property": "typo"},
    ],
)
def test_validates_curated_record_values(catalogue, changes):
    with pytest.raises(ValidationError):
        ScholarshipInput.model_validate(
            catalogue.scholarships[0].model_dump() | changes
        )


def test_official_seed_validates_without_promoting_unknown_funding(engine):
    catalogue = load_catalogue(CURATED_PATH)
    result = import_catalogue(engine, catalogue)
    assert result.created >= 1
    with Session(engine) as session:
        daad = session.scalar(
            select(Scholarship).where(Scholarship.university_or_provider == "DAAD")
        )
        assert daad.funding_type == "partially_funded"
        assert daad.minimum_gpa is None
        assert daad.minimum_ielts is None
        assert (
            session.scalar(select(func.count()).select_from(Scholarship))
            == result.created
        )
