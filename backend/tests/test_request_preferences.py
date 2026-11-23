from datetime import date

import pytest

from backend.app.request_preferences import (
    check_preferences,
    matches_destination,
    parse_preferences,
)
from backend.app.schemas import FundingType, ScholarshipRead


def _record(
    destinations: list[str] | None, funding: FundingType = FundingType.UNKNOWN
) -> ScholarshipRead:
    fully_funded = funding == FundingType.FULLY_FUNDED
    return ScholarshipRead(
        id=1,
        scholarship_name="Fictional master's programme",
        university_or_provider="Fictional university",
        destination_country=destinations,
        eligible_nationalities=["Kazakhstan"],
        eligible_study_fields=["Computer Science"],
        funding_type=funding,
        tuition_coverage="Test tuition coverage" if fully_funded else None,
        living_stipend="Test stipend" if fully_funded else None,
        official_source_url="https://example.edu/scholarships",
        last_verified_at=date(2026, 1, 1),
    )


def test_destination_required_and_partial_funding_options_preferred():
    germany = _record(["Germany", "Sweden"], FundingType.FULLY_FUNDED)
    other = _record(["Belgium", "Greece", "Spain", "Finland"], FundingType.FULLY_FUNDED)
    preferences = parse_preferences(
        "Find master’s scholarships in GERMANY for a student from Kazakhstan, "
        "including partial funding options.",
        [germany, other],
    )

    assert [preference.model_dump() for preference in preferences] == [
        {"kind": "destination", "label": "Germany", "mode": "required"},
        {"kind": "funding", "label": "Partially funded", "mode": "preferred"},
    ]
    country, funding = check_preferences(preferences, germany)
    assert country.status == "confirmed"
    assert "Germany, Sweden" in country.evidence
    assert funding.status == "unmatched"
    assert "classifies this programme as fully funded" in funding.evidence
    assert check_preferences(preferences, other)[0].status == "unmatched"


@pytest.mark.parametrize(
    ("goal", "label", "mode"),
    [
        ("Find programmes in Japan", "Japan", "required"),
        ("Find programmes across Europe", "Europe", "required"),
        ("Find a scholarship in the EU", "European Union", "required"),
        ("Find Japanese master’s scholarships", "Japan", "required"),
        ("I prefer German scholarships", "Germany", "preferred"),
        ("Ideally in Japan", "Japan", "preferred"),
        ("Find programmes in Germany if possible", "Germany", "preferred"),
        ("I prefer funding for programmes in Germany", "Germany", "required"),
        ("Find programmes only in Germany", "Germany", "required"),
        ("Find programmes in Canada", "Canada", "required"),
        ("Find programmes only in Atlantis", "Atlantis", "required"),
        ("Destination: Peru", "Peru", "required"),
    ],
)
def test_destination_constraints(goal, label, mode):
    france = _record(["France"])
    [preference] = parse_preferences(goal, [france])
    assert preference.model_dump() == {
        "kind": "destination",
        "label": label,
        "mode": mode,
    }
    if label not in {"Europe", "European Union"}:
        assert check_preferences([preference], france)[0].status == "unmatched"


@pytest.mark.parametrize(
    "goal",
    [
        "Find a master's in Computer Science for a student from Kazakhstan",
        "Find scholarships for students currently in Kazakhstan",
        "Assess SMACCs for my profile",
        "Find SMACCs. Destination includes Belgium. Check or rank it for my profile.",
    ],
)
def test_non_destination_phrases_do_not_add_a_constraint(goal):
    assert parse_preferences(goal, [_record(["Belgium"])]) == []


def test_geographical_europe_and_eu_membership_are_separate():
    assert matches_destination(_record(["Norway"]), "Europe")
    assert not matches_destination(_record(["Norway"]), "EU")
    assert not matches_destination(_record(["Cyprus"]), "Europe")
    assert matches_destination(_record(["Cyprus"]), "European Union")
    assert not matches_destination(_record(["Japan"]), "Europe")
    assert matches_destination(_record(["Germany"]), "deutschland")
    assert matches_destination(_record(["Japan"]), "Ｊａｐａｎ")
    assert not matches_destination(_record(["United Kingdom"]), "England")


def test_multiple_destinations_support_alternatives_and_both():
    germany = _record(["Germany"])
    germany_japan = _record(["Germany", "Japan"])
    alternatives = parse_preferences(
        "Search in Germany or Japan with both funding options", [germany, germany_japan]
    )
    both = parse_preferences(
        "Search in both Germany and Japan", [germany, germany_japan]
    )
    assert alternatives[0].label == "Germany or Japan"
    assert check_preferences(alternatives, germany)[0].status == "confirmed"
    assert both[0].label == "Germany and Japan"
    assert check_preferences(both, germany)[0].status == "unmatched"
    assert check_preferences(both, germany_japan)[0].status == "confirmed"


@pytest.mark.parametrize(
    ("query", "mode", "full", "partial"),
    [
        ("Only partially funded scholarships", "required", "unmatched", "confirmed"),
        ("Find fully funded scholarships", "required", "confirmed", "unmatched"),
        ("Prefer fully funded scholarships", "preferred", "confirmed", "unmatched"),
        ("Partial funding is fine", "preferred", "unmatched", "confirmed"),
        ("Open to partial funding", "preferred", "unmatched", "confirmed"),
        ("Find full or partial funding", "required", "confirmed", "confirmed"),
        ("Find partial or fully funded options", "required", "confirmed", "confirmed"),
        (
            "Prefer full funding but open to partial funding",
            "preferred",
            "confirmed",
            "confirmed",
        ),
    ],
)
def test_verified_funding_classifications(query, mode, full, partial):
    unknown = _record(None)
    fully_funded = _record(None, FundingType.FULLY_FUNDED)
    partially_funded = _record(None, FundingType.PARTIALLY_FUNDED)
    preferences = parse_preferences(query, [])
    assert [(preference.kind, preference.mode) for preference in preferences] == [
        ("funding", mode)
    ]
    assert check_preferences(preferences, unknown)[0].status == "unverified"
    assert check_preferences(preferences, fully_funded)[0].status == full
    assert check_preferences(preferences, partially_funded)[0].status == partial


def test_unknown_catalogue_destination_remains_unverified():
    record = _record(None)
    preferences = parse_preferences("Find opportunities in Germany", [record])
    [check] = check_preferences(preferences, record)
    assert check.status == "unverified"
    assert "Destinations are not documented" in check.evidence
    assert not matches_destination(record, "Germany")
