"""Tests use synthetic clauses and never consult provider websites."""

from datetime import date
from decimal import Decimal

import pytest

from backend.collection.funding_evidence import extract_funding, funding_conflicts

OLD = "https://example.org/archived-award"
NEW = "https://example.org/current-award"
OLD_TEXT = "The award includes a stipend of $2,000 CAD per month during academic terms."
NEW_TEXT = "A living allowance of CAD 2,300 per month during academic terms."


def test_funding_observation_preserves_exact_source_and_explicit_scope():
    (observation,) = extract_funding(
        OLD_TEXT,
        OLD,
        publication_year=2022,
        cycle="2023",
        retrieved_on=date(2026, 11, 25),
    )
    assert observation.amount == Decimal("2000")
    assert observation.currency == "CAD"
    assert observation.period == "month"
    assert observation.payment_scope == "academic_terms"
    assert observation.quote == OLD_TEXT[observation.start : observation.end]
    assert observation.quote.endswith("during academic terms")
    assert observation.source_url == OLD
    assert observation.retrieved_on == date(2026, 11, 25)
    assert observation.publication_year == 2022
    assert observation.cycle == "2023"


@pytest.mark.parametrize(
    ("source", "amount", "currency", "period", "scope", "qualifier"),
    [
        ("A living stipend of $350 per month.", "350", None, "month", None, "exact"),
        ("The monthly stipend is €1,234.50.", "1234.50", "EUR", "month", None, "exact"),
        (
            "A stipend of 1.234,50 EUR per year.",
            "1234.50",
            "EUR",
            "year",
            None,
            "exact",
        ),
        (
            "A stipend of at least USD 300 per annum.",
            "300",
            "USD",
            "year",
            None,
            "at_least",
        ),
        ("A stipend of up to USD 300 per term.", "300", "USD", "term", None, "up_to"),
        ("Stipend: GBP 900 per month.", "900", "GBP", "month", None, "exact"),
        ("Stipend of INR 90,000.", "90000", "INR", None, None, "exact"),
    ],
)
def test_parses_only_supported_financial_dimensions(
    source, amount, currency, period, scope, qualifier
):
    (observation,) = extract_funding(source, NEW)
    assert observation.amount == Decimal(amount)
    assert observation.currency == currency
    assert observation.period == period
    assert observation.payment_scope == scope
    assert observation.qualifier == qualifier
    assert observation.publication_year is None
    assert observation.cycle is None


@pytest.mark.parametrize(
    "source",
    [
        "An application fee of CAD 200 per month.",
        "Illustration only: a stipend of USD 500 per year.",
        "No stipend of USD 500 per month is available.",
        "A stipend of USD 500 per month is not available.",
        "A stipend of USD 500–800 per month.",
        "A stipend of USD 500 to 800 per month.",
        "A stipend of EUR 1.234 per month.",
        "A stipend of 2,3,4 CAD per month.",
        "A stipend of £200 CAD per month.",
        "A stipend of $200 EUR per month.",
        "A stipend of ¥200 CAD per month.",
        "A stipend of USD 500+ per month.",
        "An IELTS score of 6.5 is required for the scholarship.",
        "Masters: 9.500 TL",
        "A stipend of USD 500 per year or EUR 600 per year.",
    ],
)
def test_rejects_ambiguous_or_wrong_kind_number(source):
    assert extract_funding(source, NEW) == ()


def test_version_comparison_preserves_old_and_new_without_selecting_either():
    (old,) = extract_funding(OLD_TEXT, OLD, publication_year=2022, cycle="2023")
    (new,) = extract_funding(NEW_TEXT, NEW, cycle="2027")
    (undated,) = extract_funding(OLD_TEXT, NEW)
    (same_cycle,) = extract_funding(OLD_TEXT, NEW, cycle="2027")

    (change,) = funding_conflicts((old, new))
    assert change.left == old and change.right == new
    assert change.status == "distinct_cycles"
    (unresolved,) = funding_conflicts((undated, new))
    assert unresolved.status == "unresolved_time_scope"
    (conflict,) = funding_conflicts((same_cycle, new))
    assert conflict.status == "same_cycle_conflict"


def test_different_publication_years_alone_do_not_resolve_conflict():
    (old,) = extract_funding(OLD_TEXT, OLD, publication_year=2022)
    (new,) = extract_funding(NEW_TEXT, NEW, publication_year=2026)
    (difference,) = funding_conflicts((old, new))
    assert difference.status == "unresolved_time_scope"


def test_scopes_and_rates_are_not_compared_across_different_dimensions():
    (term,) = extract_funding(OLD_TEXT, OLD)
    (unknown_scope,) = extract_funding("A stipend of CAD 2300 per month.", NEW)
    (annual,) = extract_funding("A stipend of CAD 2300 per year.", NEW)
    (different_currency,) = extract_funding("A stipend of EUR 2300 per month.", NEW)
    assert funding_conflicts((term, unknown_scope, annual, different_currency)) == ()


def test_two_observations_at_one_url_are_retained():
    observations = extract_funding(OLD_TEXT + "\n" + NEW_TEXT, NEW)
    assert [o.amount for o in observations] == [Decimal("2000"), Decimal("2300")]
    (difference,) = funding_conflicts(observations)
    assert difference.status == "unresolved_time_scope"
