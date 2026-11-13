"""Deterministic discovery retains unknowns and explicitly requested negatives."""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from backend.app.candidate_discovery import discover_candidates
from backend.app.eligibility_api import match_profile
from backend.app.eligibility_schemas import MatchRequest, StudentProfile
from backend.app.import_catalogue import import_catalogue, load_catalogue
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
