"""Annotation integrity checks that never derive labels from engine predictions."""

import json
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from backend.app.eligibility_schemas import StudentProfile

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "evaluation" / "data"
LABEL_STATUSES = {"verified_gold", "provisional", "unresolved"}
VERDICTS = {"eligible", "ineligible", "needs_verification"}
EXTRACTION_FIELDS = {
    "minimum_ielts_overall",
    "minimum_ielts_component",
    "ielts_only_route",
    "minimum_gpa",
    "gpa_scale",
    "tuition_covered",
    "stipend_amount",
    "stipend_currency",
    "stipend_period",
    "deadline",
}


def read_data(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def annotations():
    return {
        "profiles": read_data("profiles.json"),
        "eligibility": read_data("eligibility_cases.json"),
        "relevance": read_data("relevance_judgments.json"),
        "sources": read_data("source_annotations.json"),
        "catalogue": json.loads(
            (ROOT / "backend" / "data" / "curated_scholarships.json").read_text(
                encoding="utf-8"
            )
        ),
    }


def assert_official_url(url, official_hosts):
    parsed = urlsplit(url)
    assert parsed.scheme == "https"
    assert parsed.hostname in official_hosts
    assert parsed.username is parsed.password is None
    assert parsed.port in (None, 443)
    assert not parsed.fragment


def test_twenty_synthetic_profiles_are_valid_and_diverse(annotations):
    document = annotations["profiles"]
    assert document["schema_version"] == 1 and document["synthetic"] is True
    profiles = document["profiles"]
    assert {row["id"] for row in profiles} == {
        f"P{number:02}" for number in range(1, 21)
    }
    assert len(profiles) == 20
    validated = [StudentProfile.model_validate(row["profile"]) for row in profiles]
    assert len({row.model_dump_json() for row in validated}) == 20
    assert {row.funding_preference.value for row in validated} == {
        "fully_funded",
        "any_funding",
    }
    assert {row.gpa_scale for row in validated if row.gpa_scale is not None} == {
        4,
        5,
        10,
        100,
    }
    assert {row.degree_completed for row in validated} == {True, False, None}
    assert len({row.degree_level for row in validated}) >= 5
    assert len({row.field_of_study for row in validated}) >= 10
    assert len({row.nationality for row in validated}) >= 3
    for row in profiles:
        assert row["description"].strip()
        assert 1 <= len(row["goal"].strip()) <= 300


def test_eligibility_annotations_have_unique_valid_references_and_statuses(annotations):
    document = annotations["eligibility"]
    assert document["schema_version"] == 1
    assert date.fromisoformat(document["as_of"]) == date(2026, 11, 12)
    assert document["annotation_method"].strip()
    cases = document["cases"]
    assert len(cases) >= 50
    assert len({case["id"] for case in cases}) == len(cases)
    pairs = {(case["profile_id"], case["scholarship_name"]) for case in cases}
    assert len(pairs) == len(cases)
    profile_ids = {row["id"] for row in annotations["profiles"]["profiles"]}
    records = annotations["catalogue"]["scholarships"]
    programme_names = {row["scholarship_name"] for row in records}
    hosts = {urlsplit(row["official_source_url"]).hostname for row in records}
    for case in cases:
        assert case["profile_id"] in profile_ids
        assert case["scholarship_name"] in programme_names
        assert case["label_status"] in LABEL_STATUSES
        assert case["expected_status"] in VERDICTS | {None}
        assert case["rationale"].strip()
        assert case["source_urls"]
        for url in case["source_urls"]:
            assert_official_url(url, hosts)
        if case["label_status"] == "unresolved":
            assert case["expected_status"] is None
        else:
            assert case["expected_status"] in VERDICTS


def test_initial_gold_scope_is_negative_and_uncertainty_is_explicit(annotations):
    cases = annotations["eligibility"]["cases"]
    counts = Counter(case["label_status"] for case in cases)
    assert counts == {"verified_gold": 30, "provisional": 20, "unresolved": 10}
    # The initial independent source review establishes only decisive negatives.
    # A later positive gold review requires corresponding provenance and scope updates.
    gold = [case for case in cases if case["label_status"] == "verified_gold"]
    assert {case["expected_status"] for case in gold} == {"ineligible"}
    provisional = [case for case in cases if case["label_status"] == "provisional"]
    assert {case["expected_status"] for case in provisional} == {
        "ineligible",
        "needs_verification",
    }


def test_relevance_judgments_preserve_unknowns_and_match_gold_case_negatives(
    annotations,
):
    document = annotations["relevance"]
    assert document["schema_version"] == 1 and document["limitations"]
    rows = document["judgments"]
    assert len({(row["profile_id"], row["scholarship_name"]) for row in rows}) == len(
        rows
    )
    profile_ids = {row["id"] for row in annotations["profiles"]["profiles"]}
    records = annotations["catalogue"]["scholarships"]
    names = {row["scholarship_name"] for row in records}
    hosts = {urlsplit(row["official_source_url"]).hostname for row in records}
    for row in rows:
        assert row["profile_id"] in profile_ids
        assert row["scholarship_name"] in names
        assert row["label_status"] in LABEL_STATUSES
        assert row["relevant"] is False or row["relevant"] is None
        assert row["rationale"].strip() and row["source_urls"]
        if row["label_status"] == "unresolved":
            assert row["relevant"] is None
        if row["label_status"] == "verified_gold":
            assert row["relevant"] is False
        for url in row["source_urls"]:
            assert_official_url(url, hosts)
    by_pair = {(row["profile_id"], row["scholarship_name"]): row for row in rows}
    for case in annotations["eligibility"]["cases"]:
        if case["label_status"] == "verified_gold":
            judgment = by_pair[(case["profile_id"], case["scholarship_name"])]
            assert judgment["relevant"] is False
            assert judgment["label_status"] == "verified_gold"


def test_extraction_examples_have_bounded_independent_source_annotations(annotations):
    document = annotations["sources"]
    assert document["schema_version"] == 1
    assert document["annotation_method"].strip() and document["limitations"]
    examples = document["examples"]
    assert len(examples) >= 12
    assert len({row["id"] for row in examples}) == len(examples)
    records = {
        row["scholarship_name"]: row for row in annotations["catalogue"]["scholarships"]
    }
    hosts = {urlsplit(row["official_source_url"]).hostname for row in records.values()}
    quoted_words = Counter()
    for row in examples:
        assert row["scholarship_name"] in records
        assert_official_url(row["source_url"], hosts)
        assert date.fromisoformat(row["accessed_at"]) <= date(2026, 11, 12)
        assert row["excerpt"].strip()
        quoted_words[row["source_url"]] += len(
            row["excerpt"].replace("[...]", "").split()
        )
        assert row["annotation_status"] in {"source_checked", "provisional"}
        assert row["expected_fields"]
        assert row["expected_fields"].keys() <= EXTRACTION_FIELDS
        for name, value in row["expected_fields"].items():
            assert value is None or type(value) in (bool, str, int, float)
            if name == "deadline" and value is not None:
                date.fromisoformat(value)
            if name in {"tuition_covered", "ielts_only_route"}:
                assert type(value) is bool or value is None
            if name in {"stipend_amount", "minimum_ielts_overall"}:
                assert type(value) in (int, float) or value is None
        for claim in row["claims"]:
            assert claim["field"] in {"scholarship_name", "funding_type"}
            assert claim["support"] in {"supported", "unsupported", "unresolved"}
            assert claim["rationale"].strip()
            if claim["support"] == "supported":
                assert (
                    claim["value"] == records[row["scholarship_name"]][claim["field"]]
                )
    assert all(count <= 25 for count in quoted_words.values())


def test_source_examples_keep_absent_funding_and_conditional_routes_unresolved(
    annotations,
):
    examples = annotations["sources"]["examples"]
    assert any(
        row["expected_fields"].get("tuition_covered") is False for row in examples
    )
    assert any(
        row["expected_fields"].get("ielts_only_route") is False for row in examples
    )
    assert any(
        claim["field"] == "funding_type" and claim["support"] == "unresolved"
        for row in examples
        for claim in row["claims"]
    )
    for row in examples:
        if "minimum_ielts_overall" in row["expected_fields"]:
            # Each annotated IELTS excerpt also names accepted alternatives.
            assert row["expected_fields"]["ielts_only_route"] is False
