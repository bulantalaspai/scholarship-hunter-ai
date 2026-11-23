"""Deterministic discovery retains unknowns and explicitly requested negatives."""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from backend.app import candidate_discovery as discovery_module
from backend.app.candidate_discovery import DiscoveryResult, discover_candidates
from backend.app.eligibility_api import match_profile
from backend.app.eligibility_schemas import MatchRequest, StudentProfile
from backend.app.import_catalogue import import_catalogue, load_catalogue
from backend.app.models import Scholarship
from backend.app.programme_resolution import ProgrammeResolution
from backend.app.schemas import CatalogueImport

TODAY = date(2026, 11, 12)
CATALOGUE = Path(__file__).parents[1] / "data" / "curated_scholarships.json"


@pytest.fixture
def profile():
    return StudentProfile(
        nationality="Kazakhstan",
        degree_level="bachelor",
        degree_completed=True,
        field_of_study="Computer Science",
        gpa=3.5,
        gpa_scale=4.0,
        ielts_overall=7.0,
        intended_start_year=2027,
        funding_preference="fully_funded",
    )


def test_general_discovery_preserves_matching_order_and_unknowns(session, profile):
    profile.funding_preference = "any_funding"
    expected = match_profile(MatchRequest(profile=profile), session, TODAY)
    result = discover_candidates(session, profile, TODAY, "Find scholarships")
    assert result.candidates == expected.eligible + expected.needs_verification
    assert result.candidate_ids == [1, 2, 3]
    assert result.named_target is False
    assert [record.id for record in result.records] == result.candidate_ids
    assert all(
        item.assessment.status == "needs_verification"
        and item.assessment.unknown_requirements
        for item in result.candidates
    )


def test_unknown_or_different_field_does_not_discard_candidates(session, profile):
    profile.field_of_study = "A field absent from the catalogue"
    result = discover_candidates(session, profile, TODAY, "Find scholarships")
    assert result.candidate_ids == [1, 3]
    assert result.candidates[1].assessment.scholarship_name.endswith("Award")
    assert result.candidates[1].assessment.status == "needs_verification"


def test_named_target_retains_confirmed_failure_and_exact_metadata(session, profile):
    result = discover_candidates(
        session,
        profile,
        TODAY,
        "Assess Fictional Demo Arts Grant for my profile.",
    )
    assert result.named_target is True
    assert result.candidate_ids == [2]
    assessment = result.candidates[0].assessment
    assert assessment.status == "ineligible"
    assert "funding_preference" in assessment.failed_requirements
    assert str(assessment.official_source_url) == "https://example.org/fictional-arts"
    assert assessment.last_verified_at == date(2026, 1, 1)
    assert len(result.records) == 1 and result.records[0].id == 2
    assert result.records[0].scholarship_name == assessment.scholarship_name
    assert result.records[0].official_source_url == assessment.official_source_url
    assert result.records[0].last_verified_at == assessment.last_verified_at


def test_named_target_normalizes_unicode_punctuation_and_whitespace(session, profile):
    result = discover_candidates(
        session,
        profile,
        TODAY,
        "Please assess FICTIONAL\tDEMO — ARTS GRANT!",
    )
    assert result.named_target is True and result.candidate_ids == [2]


def test_name_requires_complete_word_boundaries(session, profile):
    result = discover_candidates(
        session, profile, TODAY, "prefixFictional Demo Arts Grantsuffix"
    )
    assert result.named_target is False and result.candidate_ids == [1, 3]


@pytest.mark.parametrize(
    ("name", "failed_requirement"),
    [
        (
            "MEXT Research Students Scholarship - master's route (Kazakhstan embassy)",
            "deadline",
        ),
        (
            "Study Scholarships - Master Studies for All Academic Disciplines",
            "funding_preference",
        ),
    ],
)
def test_source_backed_negative_targets_survive_profile_filters(
    engine, profile, name, failed_requirement
):
    import_catalogue(engine, load_catalogue(CATALOGUE))
    with Session(engine) as session:
        result = discover_candidates(
            session, profile, TODAY, f"Assess {name} for my profile."
        )
    assert result.named_target is True and len(result.candidate_ids) == 1
    assessment = result.candidates[0].assessment
    assert assessment.scholarship_name == name
    assert assessment.status == "ineligible"
    assert failed_requirement in assessment.failed_requirements
    assert assessment.official_source_url and assessment.last_verified_at


def test_discovery_keeps_all_ids_beyond_matching_api_page_size(
    engine, catalogue, profile
):
    template = catalogue.scholarships[2]
    data = CatalogueImport(
        schema_version=1,
        data_kind="fictional_demo",
        scholarships=[
            template.model_copy(
                update={"scholarship_name": f"Fictional Demo Pagination Award {index}"}
            )
            for index in range(105)
        ],
    )
    import_catalogue(engine, data, allow_demo=True)
    with Session(engine) as session:
        result = discover_candidates(session, profile, TODAY, "Find scholarships")
        named = discover_candidates(
            session, profile, TODAY, "Assess Fictional Demo Pagination Award 104"
        )
    assert len(result.candidates) == 3 and len(result.candidate_ids) == 105
    assert len(result.records) == 3
    assert [record.id for record in result.records] == [
        item.assessment.scholarship_id for item in result.candidates
    ]
    assert len(set(result.candidate_ids)) == 105
    assert named.named_target is True and len(named.candidates) == 1
    assert named.candidates[0].assessment.scholarship_name.endswith("104")


def test_empty_database_has_empty_discovery(engine, profile):
    with Session(engine) as session:
        result = discover_candidates(session, profile, TODAY, "Find scholarships")
    assert result.candidates == [] and result.candidate_ids == []
    assert result.named_target is False


def test_all_failed_candidates_are_retained_only_when_named(session, profile):
    profile.intended_start_year = 2025
    general = discover_candidates(session, profile, TODAY, "Find scholarships")
    named = discover_candidates(
        session, profile, TODAY, "Assess Fictional Demo Unknown Requirements Award"
    )
    assert general.candidates == [] and general.candidate_ids == []
    assert named.named_target is True and named.candidate_ids == [3]
    assert named.candidates[0].assessment.status == "ineligible"


def assert_changed_catalogue(result):
    assert result.candidates == result.candidate_ids == result.records == []
    assert result.named_target is False
    assert result.resolution.status == "not_found"
    assert result.resolution.options == result.resolution.candidate_ids == []
    assert "changed during discovery" in result.resolution.message
    assert "Retry" in result.resolution.message


def test_matched_named_target_absent_from_earlier_ranked_snapshot_never_substitutes(
    engine, profile, monkeypatch
):
    import_catalogue(engine, load_catalogue(CATALOGUE))

    def earlier_snapshot(request, session, today):
        matched = match_profile(request, session, today)
        return matched.model_copy(
            update={
                "ineligible": [
                    item
                    for item in matched.ineligible
                    if item.assessment.scholarship_id != 20
                ],
                "total": matched.total - 1,
            }
        )

    monkeypatch.setattr(discovery_module, "match_profile", earlier_snapshot)
    with Session(engine) as session:
        result = discover_candidates(
            session,
            profile,
            TODAY,
            "Assess MEXT Research Students Scholarship - master's route "
            "(Kazakhstan embassy) for my profile.",
        )
    assert_changed_catalogue(result)


def test_deleted_general_record_produces_retry_without_stale_candidates(
    session, profile, monkeypatch
):
    def delete_after_ranking(request, session, today):
        matched = match_profile(request, session, today)
        record = session.get(Scholarship, 1)
        session.delete(record)
        session.flush()
        return matched

    monkeypatch.setattr(discovery_module, "match_profile", delete_after_ranking)
    result = discover_candidates(session, profile, TODAY, "Find scholarships")
    assert_changed_catalogue(result)


def test_duplicate_ranked_ids_cannot_hide_a_missing_snapshot_record(
    session, profile, monkeypatch
):
    profile.funding_preference = "any_funding"

    def inconsistent_page(request, session, today):
        matched = match_profile(request, session, today)
        values = matched.needs_verification
        return matched.model_copy(
            update={"needs_verification": [values[0], values[0], values[2]]}
        )

    monkeypatch.setattr(discovery_module, "match_profile", inconsistent_page)
    result = discover_candidates(session, profile, TODAY, "Find scholarships")
    assert_changed_catalogue(result)


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("scholarship_name", "Fictional Demo Changed Engineering Award"),
        ("official_source_url", "https://example.org/fictional-changed-source"),
        ("last_verified_at", date(2026, 1, 2)),
    ],
)
@pytest.mark.parametrize(
    "goal", ["Find scholarships", "Assess Fictional Demo Engineering Award"]
)
def test_changed_metadata_produces_retry_for_general_and_named_requests(
    session, profile, monkeypatch, attribute, value, goal
):
    def change_after_ranking(request, session, today):
        matched = match_profile(request, session, today)
        record = session.get(Scholarship, 1)
        setattr(record, attribute, value)
        session.flush()
        return matched

    monkeypatch.setattr(discovery_module, "match_profile", change_after_ranking)
    result = discover_candidates(session, profile, TODAY, goal)
    assert_changed_catalogue(result)


def test_snapshot_records_are_validated_and_independent_of_later_orm_edits(
    session, profile
):
    result = discover_candidates(session, profile, TODAY, "Find scholarships")
    assert result.records
    snapshot = result.records[0]
    record = session.get(Scholarship, snapshot.id)
    original_name = snapshot.scholarship_name
    record.scholarship_name = "Fictional Demo Later Change"
    session.flush()
    assert snapshot.scholarship_name == original_name
    assert snapshot.scholarship_name == result.candidates[0].assessment.scholarship_name


def test_inconsistent_matched_id_cannot_reenable_general_discovery(
    session, profile, monkeypatch
):
    actual = discovery_module.resolve_programme(
        "Assess Fictional Demo Engineering Award",
        [discovery_module.ScholarshipRead.model_validate(session.get(Scholarship, 1))],
    )
    altered = actual.model_dump()
    altered["candidate_ids"] = [999]
    altered["options"][0]["scholarship_id"] = 999
    monkeypatch.setattr(
        discovery_module,
        "resolve_programme",
        lambda *_args: ProgrammeResolution.model_validate(altered),
    )
    result = discover_candidates(session, profile, TODAY, "Assess named programme")
    assert_changed_catalogue(result)


def test_manual_discovery_result_keeps_default_snapshot_lists_isolated():
    first = DiscoveryResult([], [], False)
    second = DiscoveryResult([], [], False)
    assert first.records == second.records == []
    assert first.records is not second.records
