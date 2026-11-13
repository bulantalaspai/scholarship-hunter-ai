"""Fictional test attestations exercise review validation in temporary files only."""

import csv
import json
from collections import Counter
from datetime import date

import pytest

from backend.evaluation.reviews import (
    COLUMNS,
    DECISION_FIELDS,
    REVIEWERS,
    SHEET_NAMES,
    ReviewValidationError,
    build_manifest,
    generate_package,
    manifest_hash,
    validate_reviews,
)

TODAY = date(2026, 11, 13)


@pytest.fixture
def package(tmp_path):
    generate_package(tmp_path)
    return tmp_path


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def save(path, data):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(data)


def complete(package, item_id, *, reviewers=2, **changes):
    count = 0
    for filename in SHEET_NAMES:
        path = package / filename
        data = rows(path)
        for row in data:
            if row["item_id"] == item_id and count < reviewers:
                row.update(
                    reviewer_decision="accept",
                    reviewed_value=row["proposed_label"],
                    rationale="Fictional unit-test attestation only.",
                    review_date=TODAY.isoformat(),
                    review_evidence_url=row["official_evidence"].split(" | ")[0],
                    review_evidence_excerpt_or_section="Fictional test section.",
                    evidence_access_date=TODAY.isoformat(),
                )
                row.update(changes)
                count += 1
        save(path, data)
    assert count == reviewers


def first_item(package, category, *, proposed="any"):
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    return next(
        item
        for item in manifest["items"]
        if item["category"] == category
        and (proposed == "any" or item["proposed_value"] == proposed)
    )


def result_item(result, identifier):
    return next(item for item in result["items"] if item["id"] == identifier)


def test_package_has_full_provisional_population_and_blank_balanced_sheets(package):
    manifest = build_manifest()
    assert Counter(item["category"] for item in manifest["items"]) == {
        "eligibility": 60,
        "extraction": 120,
        "relevance": 80,
        "citation": 24,
    }
    assert len({item["id"] for item in manifest["items"]}) == 284
    assert all(
        item["annotation_origin"] == "ai_generated_provisional"
        for item in manifest["items"]
    )
    assignments = []
    for reviewer, filename in zip(REVIEWERS, SHEET_NAMES, strict=True):
        data = rows(package / filename)
        assignments.append(len(data))
        assert all(row["reviewer"] == reviewer for row in data)
        assert all(not row[field] for row in data for field in DECISION_FIELDS)
        assert all(row["official_evidence"].startswith("https://") for row in data)
        assert all(row["evidence_reference"] for row in data)
        assert all(row["student_profile"] for row in data if row["profile_id"])
    assert sum(assignments) == 568 and max(assignments) - min(assignments) == 1
    result = validate_reviews(package, today=TODAY)
    assert result["summary"]["human_reviewed_items"] == 0
    assert result["summary"]["academic_metrics_status"] == "NOT_EVALUABLE"
    assert result["summary"]["pending"] == 284
    assert all(item["reviewed_value"] is None for item in result["items"])


def test_blank_generation_is_reproducible(package):
    before = {path.name: path.read_bytes() for path in package.iterdir()}
    generate_package(package)
    assert {path.name: path.read_bytes() for path in package.iterdir()} == before
    assert manifest_hash(build_manifest()) == manifest_hash(build_manifest())


def test_one_actual_attestation_is_partial_and_supplies_no_consensus_label(package):
    item = first_item(package, "eligibility")
    complete(package, item["id"], reviewers=1)
    result = validate_reviews(package, today=TODAY)
    observed = result_item(result, item["id"])
    assert observed["status"] == "partial" and observed["reviewed_value"] is None
    assert result["summary"]["completed_reviews"] == 1
    assert result["summary"]["human_reviewed_items"] == 0


def test_two_matching_attestations_supply_typed_consensus(package):
    item = first_item(package, "eligibility")
    complete(package, item["id"])
    result = validate_reviews(package, today=TODAY)
    observed = result_item(result, item["id"])
    assert observed["status"] == "reviewed"
    assert observed["reviewed_value"] == "ineligible"
    assert len(observed["reviews"]) == len(observed["reviewers"]) == 2
    assert result["summary"]["human_reviewed_items"] == 1
    assert observed["profile_id"] == "P01" and observed["case_id"] == item["case_id"]


def test_disagreement_is_visible_and_excluded(package):
    item = first_item(package, "eligibility")
    complete(package, item["id"])
    changed = False
    for filename in SHEET_NAMES:
        path = package / filename
        data = rows(path)
        for row in data:
            if row["item_id"] == item["id"] and not changed:
                row.update(reviewer_decision="revise", reviewed_value='"eligible"')
                changed = True
        save(path, data)
    result = validate_reviews(package, today=TODAY)
    observed = result_item(result, item["id"])
    assert observed["status"] == "disagreement" and observed["reviewed_value"] is None
    assert result["summary"]["disagreement"] == 1


def test_unresolved_versus_decisive_review_is_an_excluded_disagreement(package):
    item = first_item(package, "eligibility")
    complete(package, item["id"])
    modified = False
    for filename in SHEET_NAMES:
        path = package / filename
        data = rows(path)
        for row in data:
            if row["item_id"] == item["id"] and not modified:
                row.update(reviewer_decision="unresolved", reviewed_value="null")
                modified = True
        save(path, data)
    observed = result_item(validate_reviews(package, today=TODAY), item["id"])
    assert observed["status"] == "disagreement" and observed["reviewed_value"] is None


def test_numeric_json_equivalence_uses_the_existing_scorer_contract(package):
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    item = next(
        item
        for item in manifest["items"]
        if item["category"] == "extraction" and item["field"] == "stipend_amount"
    )
    complete(package, item["id"], reviewed_value="1400.0")
    observed = result_item(validate_reviews(package, today=TODAY), item["id"])
    assert observed["status"] == "reviewed" and observed["reviewed_value"] == 1400


def test_review_sheet_header_and_column_count_are_enforced(package):
    path = package / SHEET_NAMES[0]
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace("item_id,", "unexpected,", 1), encoding="utf-8")
    with pytest.raises(ReviewValidationError, match="columns"):
        validate_reviews(package, today=TODAY)


def test_human_needs_verification_is_a_valid_consensus_class(package):
    item = first_item(package, "eligibility")
    complete(
        package,
        item["id"],
        reviewer_decision="revise",
        reviewed_value='"needs_verification"',
    )
    observed = result_item(validate_reviews(package, today=TODAY), item["id"])
    assert observed["status"] == "reviewed"
    assert observed["reviewed_value"] == "needs_verification"


@pytest.mark.parametrize("category", ["eligibility", "relevance"])
def test_accepting_unresolved_proposal_never_creates_a_positive_label(
    package, category
):
    item = first_item(package, category, proposed=None)
    complete(package, item["id"])
    observed = result_item(validate_reviews(package, today=TODAY), item["id"])
    assert observed["status"] == "unresolved" and observed["reviewed_value"] is None


def test_explicit_unresolved_decisions_exclude_even_extraction_absence(package):
    item = first_item(package, "extraction", proposed=None)
    complete(package, item["id"], reviewer_decision="unresolved", reviewed_value="null")
    observed = result_item(validate_reviews(package, today=TODAY), item["id"])
    assert observed["status"] == "unresolved"


def test_reviewed_extraction_null_means_confirmed_absence_only_in_that_excerpt(package):
    item = first_item(package, "extraction", proposed=None)
    complete(package, item["id"])
    observed = result_item(validate_reviews(package, today=TODAY), item["id"])
    assert observed["status"] == "reviewed" and observed["reviewed_value"] is None
    assert observed["example_id"] and observed["field"]


@pytest.mark.parametrize("suffix", ["another-page", "?different=query"])
def test_citation_support_cannot_credit_another_page_on_the_same_host(package, suffix):
    item = first_item(package, "citation")
    complete(package, item["id"], review_evidence_url=item["source_url"] + suffix)
    with pytest.raises(ReviewValidationError, match="exact cited page"):
        validate_reviews(package, today=TODAY)


@pytest.mark.parametrize("fragment", ["#funding", "#requirements"])
def test_citation_support_accepts_a_section_anchor_on_the_exact_page(package, fragment):
    item = first_item(package, "citation")
    complete(package, item["id"], review_evidence_url=item["source_url"] + fragment)
    observed = result_item(validate_reviews(package, today=TODAY), item["id"])
    assert observed["status"] == "reviewed"
    assert all(
        review["evidence_url"].endswith(fragment) for review in observed["reviews"]
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"reviewer_decision": "approved"},
        {"reviewed_value": "true"},
        {"reviewed_value": '{"label":"ineligible"}'},
        {"reviewed_value": '"eligible"'},
        {"reviewed_value": "invalid JSON"},
        {"rationale": ""},
        {"review_date": "20261113"},
        {"review_date": "2026-02-30"},
        {"review_date": "2027-01-01"},
        {"evidence_access_date": "2026-11-14"},
        {"review_evidence_url": "http://127.0.0.1/private"},
        {"review_evidence_url": "https://example.org/unsupported"},
        {"review_evidence_url": "https://name:password@www.kz.emb-japan.go.jp/"},
        {"review_evidence_url": "https://www.kz.emb-japan.go.jp:444/"},
        {"review_evidence_url": "https://["},
        {"review_evidence_excerpt_or_section": ""},
    ],
)
def test_invalid_attestations_fail_validation_without_partial_metric_labels(
    package, changes
):
    item = first_item(package, "eligibility")
    complete(package, item["id"], reviewers=1, **changes)
    with pytest.raises(ReviewValidationError):
        validate_reviews(package, today=TODAY)


@pytest.mark.parametrize(
    ("category", "changes"),
    [
        ("relevance", {"reviewer_decision": "revise", "reviewed_value": "1"}),
        ("citation", {"reviewer_decision": "revise", "reviewed_value": "true"}),
        ("extraction", {"reviewer_decision": "revise", "reviewed_value": "true"}),
        ("extraction", {"reviewer_decision": "revise", "reviewed_value": "NaN"}),
        ("extraction", {"reviewer_decision": "revise", "reviewed_value": "-1"}),
    ],
)
def test_category_types_are_strict(package, category, changes):
    item = first_item(package, category)
    complete(package, item["id"], reviewers=1, **changes)
    with pytest.raises(ReviewValidationError):
        validate_reviews(package, today=TODAY)


@pytest.mark.parametrize(
    "mutation", ["duplicate", "missing", "unknown", "immutable", "reviewer"]
)
def test_sheet_provenance_and_assignments_are_enforced(package, mutation):
    path = package / SHEET_NAMES[0]
    data = rows(path)
    if mutation == "duplicate":
        data.append(dict(data[0]))
    elif mutation == "missing":
        data.pop()
    elif mutation == "unknown":
        data[0]["item_id"] = "invented-case"
    elif mutation == "immutable":
        data[0]["proposed_label"] = '"eligible"'
    else:
        data[0]["reviewer"] = REVIEWERS[1]
    save(path, data)
    with pytest.raises(ReviewValidationError):
        validate_reviews(package, today=TODAY)


@pytest.mark.parametrize("filename", ["manifest.json", "evidence.json"])
def test_manifest_and_evidence_tampering_are_rejected(package, filename):
    path = package / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    data["tampered"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ReviewValidationError):
        validate_reviews(package, today=TODAY)


def test_generation_refuses_to_overwrite_completed_or_partial_human_input(package):
    item = first_item(package, "eligibility")
    complete(package, item["id"], reviewers=1)
    before = {path.name: path.read_bytes() for path in package.iterdir()}
    with pytest.raises(ReviewValidationError, match="overwrite"):
        generate_package(package)
    assert {path.name: path.read_bytes() for path in package.iterdir()} == before


def test_generation_leaves_an_invalid_existing_sheet_untouched(package):
    path = package / SHEET_NAMES[0]
    path.write_text(
        "item_id,rationale\ncase,Actual partial human input\n", encoding="utf-8"
    )
    before = {path.name: path.read_bytes() for path in package.iterdir()}
    with pytest.raises(ReviewValidationError):
        generate_package(package)
    assert {path.name: path.read_bytes() for path in package.iterdir()} == before


def test_committed_review_sheets_contain_no_completed_human_decisions():
    from backend.evaluation.reviews import PACKAGE

    result = validate_reviews(PACKAGE, today=TODAY)
    assert result["summary"]["completed_reviews"] == 0
    assert result["summary"]["human_reviewed_items"] == 0
