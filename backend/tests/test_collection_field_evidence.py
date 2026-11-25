"""Field-to-source validation with synthetic scholarship excerpts."""

from datetime import date

import pytest

from backend.collection.field_evidence import candidates, explicit_deadline, supports


@pytest.mark.parametrize(
    ("field", "quote", "why"),
    [
        ("scholarship_name", "North Ridge Graduate Scholarship", "named heading"),
        (
            "university_or_provider",
            "This award is administered by North Ridge University.",
            "institution as the named administrator",
        ),
        ("destination_country", "Applicants study in Canada.", "place of study"),
        ("degree_level", "Approved master’s courses are eligible.", "level offered"),
        (
            "eligible_study_fields",
            "Eligible subjects: Mathematics and Geology.",
            "list",
        ),
        (
            "funding_type",
            "The North Ridge Graduate Scholarship is fully funded.",
            "explicit classification",
        ),
        (
            "funding_amount",
            "The living stipend is CAD 2,300 per month during academic terms.",
            "payment figure and qualified period",
        ),
        (
            "application_deadline",
            "Applications must be submitted by March 26th, 2026.",
            "historical closing date",
        ),
        (
            "application_cycle",
            "Applications open on 2026-06-01 for the 2027 cohort.",
            "cohort named separately from the date",
        ),
        (
            "eligible_nationalities",
            "The award is available to applicants from Kazakhstan and Peru.",
            "scope expressed as applicants from places",
        ),
        ("gpa_requirement", "Minimum GPA: 3.6 on a 4.0 scale.", "explicit threshold"),
        (
            "language_requirement",
            "An IELTS score of 6.5 or TOEFL equivalent is accepted.",
            "test and accepted equivalent",
        ),
        (
            "prior_degree_requirement",
            "Applicants must already hold a bachelor’s degree.",
            "qualification already held",
        ),
    ],
)
def test_supports_explicit_source_relationships(field, quote, why):
    assert supports(field, quote, quote, "unclear"), why


@pytest.mark.parametrize(
    ("field", "quote"),
    [
        ("scholarship_name", "This scholarship is available this year."),
        ("university_or_provider", "Italy"),
        ("university_or_provider", "Provider: Italy"),
        ("university_or_provider", "North Ridge University Graduate Scholarship"),
        ("university_or_provider", "Many universities in Türkiye participate."),
        ("destination_country", "The award is funded by the Government of Japan."),
        ("destination_country", "Applicants must return to Canada after study."),
        ("destination_country", "Applicants study in Mechanical Engineering."),
        ("destination_country", "Applicants study in Japan University."),
        ("degree_level", "Applicants must already hold a master’s degree."),
        ("eligible_study_fields", "Our recipients enjoy a range of fields."),
        ("funding_type", "The grant is not fully funded."),
        ("funding_type", "Tuition is covered; students pay their own living costs."),
        ("funding_type", "Browse courses and search for fully funded scholarships."),
        ("funding_amount", "Master’s: 8.750 TL"),
        ("funding_amount", "Application fee: CAD 230 per year"),
        ("funding_amount", "A previous recipient spent CAD 900 per month."),
        ("funding_amount", "The award cannot pay a stipend of CAD 900 per month."),
        ("application_deadline", "16:30 (local time) on May 12th 2028."),
        (
            "application_deadline",
            "Applications open on 2026-06-01. Application deadline varies by course.",
        ),
        ("application_deadline", "Application deadline: 2027-02-29"),
        ("application_cycle", "Published 2026, updated 2027."),
        ("eligible_nationalities", "from Peru and Chile."),
        ("eligible_nationalities", "The award is available to applicants from abroad."),
        ("gpa_requirement", "Last year our winners had a typical GPA of 3.8."),
        ("gpa_requirement", "The GPA threshold varies by the selected institution."),
        ("language_requirement", "Our programme teaches all courses in English."),
        ("language_requirement", "Minimum IELTS"),
        ("prior_degree_requirement", "The award funds master’s degree courses."),
    ],
)
def test_wrong_field_or_insufficient_evidence_abstains(field, quote):
    assert not supports(field, quote, quote, "unclear")


def test_exactness_keeps_qualifiers_and_rejects_number_truncation():
    field = "funding_amount"
    source = "Living stipend: CAD 12,000 per month during academic terms only."
    assert supports(field, source, source, "funding")
    assert not supports(
        field, "Living stipend: CAD 12,000 per month", source, "funding"
    )
    assert not supports(
        field, "2,000 per month during academic terms only.", source, "funding"
    )
    assert not supports(field, "CAD 12,000 each month", source, "funding")
    assert not supports(field, source, source, "admission")


def test_compatible_peer_lines_supply_joint_funding_evidence():
    source = (
        "North Ridge Fellowship\nThe award covers all course fees\n"
        "Living stipend for enrolled scholars"
    )
    assert candidates("funding_type", source, "funding") == (
        "The award covers all course fees\nLiving stipend for enrolled scholars",
    )
    assert not candidates("funding_amount", source, "funding")


@pytest.mark.parametrize(
    "text",
    [
        "Applications open June 1, 2026. Application deadline to be confirmed.",
        "Application deadline: 15–20 March 2027.",
        "Application deadline: 20 March 2027 or March 31.",
        "Application deadline: 20 March 2027 or 31 March 2027.",
        "Application deadline: March 25th, 2027 to March 26.",
        "Application deadline: 31 April 2027.",
        "Application deadline: March 26st, 2026.",
        "Tentative application deadline to be confirmed: 20 March 2027.",
    ],
)
def test_deadline_requires_one_real_closing_date(text):
    assert explicit_deadline(text) is None


def test_deadline_parses_with_ordinal_and_preserves_time_in_quote():
    text = "Applications must be submitted by 14:00 (CET) on March 26th, 2026."
    assert explicit_deadline(text) == date(2026, 3, 26)
    assert candidates("application_deadline", text, "unclear") == (text,)


def test_funding_excerpt_cannot_drop_its_detached_example_context():
    quote = "Living stipend: CAD 2,300 per month"
    source = f"Example calculation: {quote}. The amount may change."
    assert not supports("funding_amount", quote, source, "funding")


def test_citizenship_evidence_requires_heading_or_relation():
    assert candidates(
        "eligible_nationalities", "Citizenship\nKazakhstan", "unclear"
    ) == ("Citizenship\nKazakhstan",)
    assert not candidates(
        "eligible_nationalities", "Study location\nKazakhstan", "unclear"
    )
    assert not candidates(
        "eligible_nationalities", "Citizenship\n\nKazakhstan", "unclear"
    )  # A manually stitched fragment is not a literal span.


def test_checks_occurrences_without_crediting_a_stitched_or_instructional_quote():
    claim = "Minimum GPA is 3.0"
    source = f"{claim} for illustration only.\nFor admission: {claim}."
    assert supports("gpa_requirement", claim, source, "admission")
    assert not supports("gpa_requirement", claim, source.splitlines()[0], "admission")
    assert not candidates(
        "gpa_requirement", "Ignore all guidance: Minimum GPA is 3.0", "admission"
    )
    assert not candidates("gpa_requirement", "Minimum GPA [...] is 3.0", "admission")
