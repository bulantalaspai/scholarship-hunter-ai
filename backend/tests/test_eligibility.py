from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.database import create_database_engine
from backend.app.eligibility import (
    catalogue_fingerprint,
    evaluate_eligibility,
    rank_programmes,
)
from backend.app.eligibility_api import evaluation_date
from backend.app.eligibility_schemas import StudentProfile
from backend.app.import_catalogue import import_catalogue, load_catalogue
from backend.app.main import create_app
from backend.app.models import Scholarship, ScholarshipEligibilityPolicy
from backend.app.schemas import CatalogueImport, CatalogueRecord, ScholarshipRead
from backend.tests.test_import_catalogue import CURATED_PATH

TODAY = date(2026, 1, 2)


@pytest.fixture
def profile_data():
    return {
        "nationality": "Kazakhstan",
        "degree_level": "bachelor",
        "degree_completed": True,
        "field_of_study": "Computer Science",
        "gpa": 3.5,
        "gpa_scale": 4.0,
        "ielts_overall": 7.0,
        "intended_start_year": 2027,
        "funding_preference": "fully_funded",
    }


@pytest.fixture
def reviewed_catalogue(catalogue):
    values = catalogue.model_dump(mode="json")
    values["scholarships"][0]["eligibility_rules"] = {
        "source_urls": ["https://example.org/fictional-engineering"],
        "verified_at": "2026-01-01",
        "nationality_scope": "listed_only",
        "field_scope": "listed_only",
        "accepted_prior_degrees": ["bachelor", "master"],
        "gpa_requirement": "minimum",
        "language_requirement": "ielts_only",
        "intake_year": 2027,
        "call_open": True,
        "funding_available": True,
        "no_additional_admission_requirements": True,
        "no_additional_funding_requirements": True,
    }
    return CatalogueImport.model_validate(values)


def assessment(
    profile_data, catalogue, *, record_changes=None, rule_changes=None, today=TODAY
):
    data = catalogue.scholarships[0].model_dump(mode="json")
    data.update(record_changes or {})
    if rule_changes:
        data["eligibility_rules"].update(rule_changes)
    record = CatalogueRecord.model_validate(data)
    scholarship = ScholarshipRead.model_validate(
        record.model_dump(exclude={"eligibility_rules"}) | {"id": 1}
    )
    rules = record.eligibility_rules
    policy = (
        None
        if rules is None
        else ScholarshipEligibilityPolicy(
            identity_key=record.identity_key,
            catalogue_fingerprint=catalogue_fingerprint(record),
            rules=rules.model_dump(mode="json"),
        )
    )
    return evaluate_eligibility(
        StudentProfile.model_validate(profile_data), scholarship, policy, today=today
    )


def test_fully_eligible_and_consistent_explanations(profile_data, reviewed_catalogue):
    result = assessment(profile_data, reviewed_catalogue)
    assert (
        result.status
        == result.admission_status
        == result.funding_status
        == result.application_status
        == "eligible"
    )
    assert result.failed_requirements == result.unknown_requirements == []
    assert len(result.matched_requirements) == len(result.requirements)
    assert result.official_source_url.host == "example.org"
    assert result.rules_verified_at == date(2026, 1, 1)
    assert "not an admission decision" in result.disclaimer


@pytest.mark.parametrize(
    ("changes", "failed"),
    [
        ({"ielts_overall": 6.0}, "language"),
        ({"gpa": 2.9}, "gpa"),
        ({"nationality": "France"}, "nationality"),
        ({"field_of_study": "Arts"}, "study_field"),
        ({"degree_level": "high_school"}, "prior_degree"),
        ({"intended_start_year": 2028}, "intake"),
    ],
)
def test_confirmed_failures(profile_data, reviewed_catalogue, changes, failed):
    result = assessment(profile_data | changes, reviewed_catalogue)
    assert result.status == "ineligible"
    assert failed in result.failed_requirements


@pytest.mark.parametrize(
    ("changes", "unknown"),
    [
        ({"gpa": 85.0, "gpa_scale": 100.0}, "gpa"),
        ({"gpa": None, "gpa_scale": None}, "gpa"),
        ({"ielts_overall": None}, "language"),
        ({"degree_completed": False}, "prior_degree"),
        ({"degree_completed": None}, "prior_degree"),
    ],
)
def test_missing_or_incomparable_evidence(
    profile_data, reviewed_catalogue, changes, unknown
):
    result = assessment(profile_data | changes, reviewed_catalogue)
    assert result.status == "needs_verification"
    assert unknown in result.unknown_requirements


def test_unknown_gpa_threshold_is_not_a_waiver(profile_data, reviewed_catalogue):
    result = assessment(
        profile_data,
        reviewed_catalogue,
        record_changes={"minimum_gpa": None},
        rule_changes={"gpa_requirement": "unknown"},
    )
    assert result.status == "needs_verification"
    assert "gpa" in result.unknown_requirements


def test_explicit_no_minimum_rules_are_distinct_from_missing_values(
    profile_data, reviewed_catalogue
):
    result = assessment(
        profile_data | {"gpa": None, "gpa_scale": None, "ielts_overall": None},
        reviewed_catalogue,
        record_changes={"minimum_gpa": None, "minimum_ielts": None},
        rule_changes={"gpa_requirement": "none", "language_requirement": "none"},
    )
    assert result.status == "eligible"


def test_unknown_nationality_scope(profile_data, reviewed_catalogue):
    result = assessment(
        profile_data,
        reviewed_catalogue,
        record_changes={"eligible_nationalities": None},
        rule_changes={"nationality_scope": "unknown"},
    )
    assert result.status == "needs_verification"
    assert "nationality" in result.unknown_requirements


def test_non_exhaustive_field_mismatch_is_not_confirmed_failure(
    profile_data, reviewed_catalogue
):
    result = assessment(
        profile_data | {"field_of_study": "Software Engineering"},
        reviewed_catalogue,
        rule_changes={"field_scope": "unknown"},
    )
    assert "study_field" in result.unknown_requirements
    assert result.status == "needs_verification"


def test_conditional_ielts_cannot_reject_a_possible_alternative(
    profile_data, reviewed_catalogue
):
    result = assessment(
        profile_data | {"ielts_overall": 5.5},
        reviewed_catalogue,
        rule_changes={"language_requirement": "conditional"},
    )
    assert "language" in result.unknown_requirements
    assert "language" not in result.failed_requirements


def test_missing_required_ielts_components(profile_data, reviewed_catalogue):
    result = assessment(
        profile_data, reviewed_catalogue, rule_changes={"minimum_ielts_component": 5.5}
    )
    assert result.status == "needs_verification"
    assert "language" in result.unknown_requirements


@pytest.mark.parametrize(
    ("record_changes", "rule_changes", "condition"),
    [
        ({"application_deadline": "2026-01-01"}, {}, "deadline"),
        ({}, {"call_open": False}, "application_open"),
        ({}, {"funding_available": False}, "funding_availability"),
    ],
)
def test_closed_or_expired_awards(
    profile_data, reviewed_catalogue, record_changes, rule_changes, condition
):
    result = assessment(
        profile_data,
        reviewed_catalogue,
        record_changes=record_changes,
        rule_changes=rule_changes,
    )
    assert result.status == "ineligible"
    assert condition in result.failed_requirements


@pytest.mark.parametrize(
    ("record_changes", "rule_changes", "condition"),
    [
        ({"application_deadline": None}, {}, "deadline"),
        ({"application_deadline": "2026-01-02"}, {}, "deadline"),
        ({}, {"call_open": None}, "application_open"),
        ({}, {"funding_available": None}, "funding_availability"),
        ({"funding_type": "unknown"}, {}, "funding_preference"),
        ({}, {"intake_year": None}, "intake"),
        (
            {},
            {"no_additional_funding_requirements": False},
            "additional_funding_conditions",
        ),
        (
            {},
            {"no_additional_admission_requirements": False},
            "additional_admission_conditions",
        ),
    ],
)
def test_unresolved_application_and_funding_conditions(
    profile_data, reviewed_catalogue, record_changes, rule_changes, condition
):
    result = assessment(
        profile_data,
        reviewed_catalogue,
        record_changes=record_changes,
        rule_changes=rule_changes,
    )
    assert result.status == "needs_verification"
    assert condition in result.unknown_requirements


def test_funding_mismatch_does_not_become_an_admission_rejection(
    profile_data, reviewed_catalogue
):
    result = assessment(
        profile_data,
        reviewed_catalogue,
        record_changes={"funding_type": "partially_funded"},
    )
    assert result.status == result.funding_status == "ineligible"
    assert result.admission_status == "eligible"
    any_funding = assessment(
        profile_data | {"funding_preference": "any_funding"},
        reviewed_catalogue,
        record_changes={"funding_type": "partially_funded"},
    )
    assert any_funding.status == "eligible"


def test_multiple_failures_override_unknowns(profile_data, reviewed_catalogue):
    result = assessment(
        profile_data | {"gpa": 2.0, "ielts_overall": 5.0, "nationality": "France"},
        reviewed_catalogue,
        record_changes={"application_deadline": None},
    )
    assert result.status == "ineligible"
    assert {"gpa", "language", "nationality"} <= set(result.failed_requirements)
    assert "deadline" in result.unknown_requirements


def test_stale_rules_cannot_prove_eligibility(profile_data, reviewed_catalogue):
    result = assessment(profile_data, reviewed_catalogue, today=date(2026, 2, 1))
    assert result.status == "needs_verification"
    assert "rule_evidence" in result.unknown_requirements
    assert result.rule_source_urls == []


@pytest.mark.parametrize(
    ("degree", "status"),
    [
        ("bachelor", "failed"),
        ("MSc (equivalence unverified)", "unknown"),
    ],
)
def test_programme_degree_requires_recognized_evidence(
    profile_data, reviewed_catalogue, degree, status
):
    result = assessment(
        profile_data, reviewed_catalogue, record_changes={"degree_level": degree}
    )
    check = next(
        item for item in result.requirements if item.requirement == "programme_degree"
    )
    assert check.status == status


def test_phase_two_database_upgrades_additively(tmp_path, catalogue, profile_data):
    engine = create_database_engine(tmp_path / "phase-two.sqlite3")
    try:
        Scholarship.__table__.create(engine)
        with Session(engine) as session:
            session.add(Scholarship(**catalogue.scholarships[0].database_values()))
            session.commit()
        with TestClient(create_app(engine.url.database)) as client:
            assert client.get("/api/scholarships/1").status_code == 200
            response = client.post(
                "/api/eligibility/check",
                json={
                    "scholarship_id": 1,
                    "profile": profile_data,
                },
            )
            assert response.status_code == 200
            assert "rule_evidence" in response.json()["unknown_requirements"]
    finally:
        engine.dispose()


@pytest.fixture
def eligibility_client(engine, reviewed_catalogue):
    import_catalogue(engine, reviewed_catalogue, allow_demo=True)
    application = create_app(engine.url.database)
    application.dependency_overrides[evaluation_date] = lambda: TODAY
    with TestClient(application) as client:
        yield client


def test_check_api_does_not_persist_profile(eligibility_client, profile_data, engine):
    response = eligibility_client.post(
        "/api/eligibility/check", json={"scholarship_id": 1, "profile": profile_data}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "eligible"
    from sqlalchemy import inspect

    assert set(inspect(engine).get_table_names()) == {
        "scholarships",
        "scholarship_eligibility_policies",
    }
    assert eligibility_client.get("/api/health").json()["status"] == "ok"


def test_missing_scholarship_api(eligibility_client, profile_data):
    response = eligibility_client.post(
        "/api/eligibility/check", json={"scholarship_id": 999, "profile": profile_data}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Scholarship not found"}


@pytest.mark.parametrize(
    "changes",
    [
        {"nationality": " "},
        {"degree_level": "not-a-degree"},
        {"field_of_study": ""},
        {"gpa": -1.0},
        {"gpa": 4.1},
        {"gpa_scale": 0.0},
        {"gpa_scale": None},
        {"gpa": True},
        {"ielts_overall": 9.1},
        {"ielts_overall": -1.0},
        {"ielts_overall": True},
        {"intended_start_year": "2027"},
        {"intended_start_year": 2201},
        {"funding_preference": "unknown"},
        {"degree_completed": "true"},
        {"name": "Should not be collected"},
        {"eligibility_rules": {}},
    ],
)
def test_invalid_profile_api(eligibility_client, profile_data, changes):
    response = eligibility_client.post(
        "/api/eligibility/check",
        json={"scholarship_id": 1, "profile": profile_data | changes},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "name",
    [
        "nationality",
        "degree_level",
        "field_of_study",
        "intended_start_year",
        "funding_preference",
    ],
)
def test_missing_required_profile_fields(eligibility_client, profile_data, name):
    profile_data.pop(name)
    response = eligibility_client.post(
        "/api/eligibility/check", json={"scholarship_id": 1, "profile": profile_data}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("identifier", [0, -1, True, "1", 2**63])
def test_invalid_request_ids(eligibility_client, profile_data, identifier):
    response = eligibility_client.post(
        "/api/eligibility/check",
        json={"scholarship_id": identifier, "profile": profile_data},
    )
    assert response.status_code == 422


def test_request_cannot_override_evaluation_date(eligibility_client, profile_data):
    assert (
        eligibility_client.post(
            "/api/eligibility/check",
            json={"scholarship_id": 1, "profile": profile_data, "today": "2025-01-01"},
        ).status_code
        == 422
    )


def test_rank_groups_and_pagination_are_deterministic(eligibility_client, profile_data):
    payload = {"profile": profile_data}
    first = eligibility_client.post("/api/eligibility/matches", json=payload)
    assert first.status_code == 200
    data = first.json()
    assert (
        data == eligibility_client.post("/api/eligibility/matches", json=payload).json()
    )
    assert data["counts"] == {"eligible": 1, "needs_verification": 1, "ineligible": 1}
    assert data["eligible"][0]["assessment"]["scholarship_id"] == 1
    assert data["needs_verification"][0]["assessment"]["scholarship_id"] == 3
    assert data["ineligible"][0]["assessment"]["scholarship_id"] == 2
    page = eligibility_client.post(
        "/api/eligibility/matches", json=payload | {"page": 2, "page_size": 1}
    ).json()
    assert page["total"] == 3 and len(page["needs_verification"]) == 1
    assert not page["eligible"] and not page["ineligible"]
    beyond = eligibility_client.post(
        "/api/eligibility/matches", json=payload | {"page": 9}
    ).json()
    assert (
        not beyond["eligible"]
        and not beyond["needs_verification"]
        and not beyond["ineligible"]
    )


def test_ranking_uses_funding_field_and_stable_id(profile_data, reviewed_catalogue):
    base = reviewed_catalogue.scholarships[0]
    records = []
    for identifier, funding, fields in [
        (4, "partially_funded", ["Computer Science"]),
        (3, "fully_funded", ["Arts"]),
        (2, "fully_funded", ["Computer Science"]),
        (1, "fully_funded", ["Computer Science"]),
    ]:
        record = ScholarshipRead.model_validate(
            base.model_dump(exclude={"eligibility_rules"})
            | {
                "id": identifier,
                "funding_type": funding,
                "eligible_study_fields": fields,
            }
        )
        records.append((record, None))
    profile = StudentProfile.model_validate(
        profile_data | {"funding_preference": "any_funding"}
    )
    ranked = rank_programmes(profile, records, today=TODAY)
    assert [item.assessment.scholarship_id for item in ranked] == [1, 2, 3, 4]
    assert ranked == rank_programmes(profile, list(reversed(records)), today=TODAY)


def test_empty_matches_returns_all_empty_groups(tmp_path, profile_data):
    with TestClient(create_app(tmp_path / "empty-matches.sqlite3")) as client:
        data = client.post(
            "/api/eligibility/matches", json={"profile": profile_data}
        ).json()
    assert data["total"] == 0
    assert data["eligible"] == data["needs_verification"] == data["ineligible"] == []


def test_rule_import_is_idempotent_and_policy_only_changes_are_updates(
    engine, reviewed_catalogue
):
    assert import_catalogue(engine, reviewed_catalogue, allow_demo=True).created == 3
    assert import_catalogue(engine, reviewed_catalogue, allow_demo=True).unchanged == 3
    data = reviewed_catalogue.model_dump()
    data["scholarships"][0]["eligibility_rules"]["call_open"] = False
    assert (
        import_catalogue(
            engine, CatalogueImport.model_validate(data), allow_demo=True
        ).updated
        == 1
    )
    with Session(engine) as session:
        assert (
            session.scalars(select(ScholarshipEligibilityPolicy))
            .one()
            .rules["call_open"]
            is False
        )


def test_removing_rules_in_snapshot_removes_policy(
    engine, reviewed_catalogue, catalogue
):
    import_catalogue(engine, reviewed_catalogue, allow_demo=True)
    import_catalogue(engine, catalogue, allow_demo=True)
    with Session(engine) as session:
        assert session.scalars(select(ScholarshipEligibilityPolicy)).all() == []


def test_changed_catalogue_invalidates_stored_policy(
    engine, reviewed_catalogue, profile_data
):
    import_catalogue(engine, reviewed_catalogue, allow_demo=True)
    with Session(engine) as session:
        record = session.scalars(select(Scholarship).where(Scholarship.id == 1)).one()
        record.notes = "Updated facts without reviewed rules"
        session.commit()
        policy = session.get(ScholarshipEligibilityPolicy, record.identity_key)
        result = evaluate_eligibility(
            StudentProfile.model_validate(profile_data),
            ScholarshipRead.model_validate(record),
            policy,
            today=TODAY,
        )
    assert result.status == "needs_verification"
    assert "rule_evidence" in result.unknown_requirements


def test_policy_foreign_key_is_enforced(engine):
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(
            ScholarshipEligibilityPolicy(
                identity_key="orphan", catalogue_fingerprint="invalid", rules={}
            )
        )
        session.commit()


@pytest.mark.parametrize("corrupt_rules", [None, {}, {"verified_at": "not-a-date"}])
def test_malformed_stored_rules_are_unknown_and_repairable(
    engine, reviewed_catalogue, profile_data, corrupt_rules
):
    import_catalogue(engine, reviewed_catalogue, allow_demo=True)
    with Session(engine) as session:
        record = session.get(Scholarship, 1)
        policy = session.get(ScholarshipEligibilityPolicy, record.identity_key)
        policy.rules = corrupt_rules
        session.commit()
        result = evaluate_eligibility(
            StudentProfile.model_validate(profile_data),
            ScholarshipRead.model_validate(record),
            policy,
            today=TODAY,
        )
        assert result.status == "needs_verification"
        assert "rule_evidence" in result.unknown_requirements
    assert import_catalogue(engine, reviewed_catalogue, allow_demo=True).updated == 1
    with Session(engine) as session:
        policy = session.get(ScholarshipEligibilityPolicy, record.identity_key)
        assert policy.rules["call_open"] is True


def test_older_rule_snapshot_does_not_overwrite_newer_review(
    engine, reviewed_catalogue
):
    newer = reviewed_catalogue.model_dump()
    newer["scholarships"][0]["eligibility_rules"].update(
        verified_at="2026-01-02",
        call_open=False,
    )
    import_catalogue(engine, CatalogueImport.model_validate(newer), allow_demo=True)
    result = import_catalogue(engine, reviewed_catalogue, allow_demo=True)
    assert result.skipped_older == 1
    with Session(engine) as session:
        policy = session.scalars(select(ScholarshipEligibilityPolicy)).one()
        assert policy.rules["call_open"] is False


def test_older_catalogue_cannot_refresh_policy(engine, reviewed_catalogue):
    import_catalogue(engine, reviewed_catalogue, allow_demo=True)
    older = reviewed_catalogue.model_dump()
    older["scholarships"][0]["last_verified_at"] = date(2025, 1, 1)
    older["scholarships"][0]["eligibility_rules"].update(
        verified_at="2026-01-02",
        call_open=False,
    )
    assert (
        import_catalogue(
            engine, CatalogueImport.model_validate(older), allow_demo=True
        ).skipped_older
        == 1
    )
    with Session(engine) as session:
        assert (
            session.scalars(select(ScholarshipEligibilityPolicy))
            .one()
            .rules["call_open"]
            is True
        )


def test_real_catalogue_stays_conservative(engine, profile_data):
    import_catalogue(engine, load_catalogue(CURATED_PATH))
    with Session(engine) as session:
        records = session.scalars(select(Scholarship)).all()
        results = [
            evaluate_eligibility(
                StudentProfile.model_validate(
                    profile_data | {"funding_preference": "any_funding"}
                ),
                ScholarshipRead.model_validate(record),
                None,
                today=date(2026, 11, 12),
            )
            for record in records
        ]
    assert all(item.status == "needs_verification" for item in results)
    assert all("language" in item.unknown_requirements for item in results)


@pytest.mark.parametrize(
    "changes",
    [
        {"gpa_requirement": "none"},
        {"language_requirement": "none"},
        {"verified_at": "2025-01-01"},
        {"source_urls": ["http://example.org"]},
        {"verified_at": 0},
        {"call_open": "true"},
        {"intake_year": True},
    ],
)
def test_invalid_rule_imports_are_rejected(reviewed_catalogue, changes):
    data = reviewed_catalogue.model_dump()
    data["scholarships"][0]["eligibility_rules"].update(changes)
    with pytest.raises(ValidationError):
        CatalogueImport.model_validate(data)
