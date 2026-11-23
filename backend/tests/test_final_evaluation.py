"""Fictional review fixtures test scoring and never represent real human reviews."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from backend.evaluation import final as final_module
from backend.evaluation.extract import EXTRACTION_KEYS
from backend.evaluation.final import (
    analyze_misses,
    compare_final,
    human_citations,
    human_eligibility,
    human_extraction,
    human_relevance,
    named_recall,
    reviewed_items,
)
from backend.evaluation.reviews import generate_package, validate_reviews
from backend.evaluation.run import CATALOGUE, DATA, read_json


def candidate(identifier, status="needs_verification"):
    return {
        "scholarship_id": identifier,
        "scholarship_name": f"Fictional Demo Programme {identifier}",
        "status": status,
        "source_url": f"https://example.org/fictional-{identifier}",
        "ranking_reasons": ["Published funding: fully_funded; award not guaranteed."],
    }


def run(**values):
    return {
        "profile_id": "DEMO_P1",
        "seconds": 1,
        "status": "completed",
        "error": None,
        "model_error": None,
        "recommendations": [],
        "assessments": [],
        "discovery_candidates": [],
        "discovery_candidate_ids": [],
        "trace": [],
        "rounds": [],
        **values,
    }


def reviewed(category, identifier, value, **values):
    return {
        "id": identifier,
        "category": category,
        "status": "reviewed",
        "reviewed_value": value,
        "reviewers": ["Fictional Reviewer A", "Fictional Reviewer B"],
        **values,
    }


@pytest.fixture
def population():
    records = [candidate(1, "eligible"), candidate(2, "ineligible"), candidate(3)]
    cases = [
        {
            "id": f"DEMO_C{index}",
            "profile_id": "DEMO_P1",
            "scholarship_name": record["scholarship_name"],
            "label_status": "verified_gold",
            "expected_status": record["status"],
        }
        for index, record in enumerate(records, 1)
    ]
    examples = [{"id": "DEMO_S1"}]
    result = {
        "signature": {"inputs": {"demo.json": "hash"}, "as_of": "2026-11-12"},
        "baseline": [run(recommendations=[records[0]], assessments=records)],
        "agent": [
            run(
                recommendations=[records[0]],
                discovery_candidates=[records[0], records[2]],
                discovery_candidate_ids=[1, 3],
            )
        ],
        "agent_cases": [
            run(
                case_id=case["id"],
                assessments=[] if index == 1 else [records[index]],
                discovery_candidates=[records[index]],
            )
            for index, case in enumerate(cases)
        ],
        "extraction": [{"example_id": "DEMO_S1", "fields": {}}],
    }
    return result, cases, examples


def eligibility_reviews(cases):
    return {
        "items": [
            reviewed(
                "eligibility",
                f"E-{case['id']}",
                case["expected_status"],
                case_id=case["id"],
                profile_id=case["profile_id"],
                scholarship_name=case["scholarship_name"],
            )
            for case in cases
        ]
    }


def test_ai_authored_labels_cannot_create_human_accuracy(population):
    result, cases, examples = population
    reviews = {"items": [], "input_hashes": {"demo.json": "hash"}}
    summary = compare_final(result, result, cases, examples, reviews)
    assert summary["human_metrics"]["eligibility"]["status"] == "NOT_EVALUABLE"
    assert summary["human_metrics"]["eligibility"]["reviewed_cases"] == 0
    assert summary["human_metrics"]["extraction"]["f1"] is None
    assert summary["human_metrics"]["precision_at_3"]["status"] == "NOT_EVALUABLE"
    assert summary["human_metrics"]["citations"]["target_status"] == "NOT_EVALUABLE"


def test_pending_disagreed_and_unresolved_labels_are_excluded(population):
    result, cases, _ = population
    reviews = eligibility_reviews(cases)
    reviews["items"][0]["status"] = "pending"
    reviews["items"][1]["status"] = "disagreement"
    reviews["items"][2]["status"] = "unresolved"
    score = human_eligibility(result, cases, reviews)
    assert score["status"] == "NOT_EVALUABLE" and score["reviewed_cases"] == 0
    assert all(
        metric["reviewed_subset_accuracy"] is None
        for metric in score["methods"].values()
    )


def test_complete_human_three_class_labels_count_missing_raw_targets(population):
    result, cases, _ = population
    metrics = human_eligibility(result, cases, eligibility_reviews(cases))
    assert metrics["status"] == "MEASURED"
    assert metrics["methods"]["deterministic_baseline"]["eligibility_accuracy"] == 1
    raw = metrics["methods"]["raw_qwen_tool_assessments"]
    assert raw["missing_or_invalid"] == 1 and raw["eligibility_accuracy"] == 2 / 3
    assert raw["conditional_accuracy_among_assessed"] == 1
    assert (
        metrics["methods"]["qwen_with_deterministic_assistance"]["eligibility_accuracy"]
        == 1
    )


def test_partial_or_single_class_human_review_does_not_establish_proposal_accuracy(
    population,
):
    result, cases, _ = population
    partial = eligibility_reviews(cases[:1])
    metrics = human_eligibility(result, cases, partial)
    assert metrics["status"] == "NOT_EVALUABLE"
    assert metrics["methods"]["deterministic_baseline"]["reviewed_subset_accuracy"] == 1
    assert metrics["methods"]["deterministic_baseline"]["eligibility_accuracy"] is None
    single_class = eligibility_reviews(cases)
    for item in single_class["items"]:
        item["reviewed_value"] = "needs_verification"
    assert human_eligibility(result, cases, single_class)["status"] == "NOT_EVALUABLE"


def test_duplicate_or_mismatched_human_case_fails_validation(population):
    result, cases, _ = population
    reviews = eligibility_reviews(cases)
    reviews["items"][0]["scholarship_name"] = "Fictional substitute"
    with pytest.raises(ValueError, match="conflicts"):
        human_eligibility(result, cases, reviews)
    duplicate = eligibility_reviews(cases)
    duplicate["items"].append(deepcopy(duplicate["items"][0]))
    with pytest.raises(ValueError, match="unique"):
        reviewed_items(duplicate, "eligibility")


def test_a_single_reviewer_cannot_produce_independent_consensus(population):
    _, cases, _ = population
    reviews = eligibility_reviews(cases)
    reviews["items"][0]["reviewers"] = ["Fictional Reviewer A"]
    with pytest.raises(ValueError, match="two independent"):
        reviewed_items(reviews, "eligibility")


def extraction_reviews():
    return {
        "items": [
            reviewed(
                "extraction",
                f"X-DEMO_S1-{field}",
                {"stipend_amount": 1400, "deadline": "2027-01-01"}.get(field),
                example_id="DEMO_S1",
                field=field,
            )
            for field in EXTRACTION_KEYS
        ]
    }


def test_extraction_scores_only_fully_reviewed_slots_and_preserves_null_absence(
    population,
):
    result, _, examples = population
    result["extraction"][0]["fields"] = {
        "stipend_amount": 1400,
        "ielts_only_route": False,
    }
    reviews = extraction_reviews()
    metrics = human_extraction(result, examples, reviews)
    assert metrics["status"] == "MEASURED"
    assert metrics["precision"] == metrics["recall"] == metrics["f1"] == 0.5
    assert metrics["reviewed_subset_counts"] == {
        "tp": 1,
        "fp": 1,
        "fn": 1,
        "predicted_examples": 1,
    }
    reviews["items"][0]["status"] = "unresolved"
    partial = human_extraction(result, examples, reviews)
    assert partial["fully_reviewed_examples"] == 0 and partial["f1"] is None


def test_empty_or_absence_only_extraction_cannot_create_perfect_f1(population):
    result, _, examples = population
    assert human_extraction(result, examples, {"items": []})["f1"] is None
    reviews = extraction_reviews()
    for item in reviews["items"]:
        item["reviewed_value"] = None
    assert human_extraction(result, examples, reviews)["f1"] is None


def test_relevance_true_needs_independent_eligible_labels(population):
    result, cases, _ = population
    records = [candidate(index, "eligible") for index in range(1, 4)]
    result["baseline"][0]["recommendations"] = records
    result["agent"][0]["recommendations"] = records
    result["agent"][0]["discovery_candidates"] = records
    reviews = {
        "items": [
            reviewed(
                "relevance",
                f"R-{index}",
                True,
                profile_id="DEMO_P1",
                scholarship_name=record["scholarship_name"],
            )
            for index, record in enumerate(records)
        ]
    }
    unavailable = human_relevance(result, reviews)
    assert unavailable["status"] == "NOT_EVALUABLE"
    assert unavailable["methods"]["raw_qwen"]["precision_at_3"] is None
    for item in eligibility_reviews(cases)["items"]:
        item["reviewed_value"] = "eligible"
        reviews["items"].append(item)
    scored = human_relevance(result, reviews)
    assert scored["status"] == "MEASURED"
    assert scored["methods"]["raw_qwen"]["precision_at_3"] == 1


def test_citation_links_have_no_human_support_without_reviews(population):
    result, _, _ = population
    metrics = human_citations(result, {"items": []})
    raw = metrics["methods"]["raw_qwen"]
    assert raw["citation_coverage"] == 1 and raw["claims"] == 2
    assert raw["human_support_status"] == "NOT_EVALUABLE"
    assert raw["citation_support_rate"] is None and raw["unresolved_claims"] == 2
    assert metrics["target_status"] == "NOT_EVALUABLE"


def test_citation_support_joins_exact_claim_value_and_url(population):
    result, _, _ = population
    record = result["agent"][0]["recommendations"][0]
    reviews = {
        "items": [
            reviewed(
                "citation",
                "C-DEMO-1",
                "supported",
                scholarship_name=record["scholarship_name"],
                source_url=record["source_url"],
                field="scholarship_name",
                claim_value=record["scholarship_name"],
            )
        ]
    }
    raw = human_citations(result, reviews)["methods"]["raw_qwen"]
    assert raw["supported_claims"] == 1 and raw["unresolved_claims"] == 1
    reviews["items"][0]["source_url"] += "/wrong"
    assert (
        human_citations(result, reviews)["methods"]["raw_qwen"]["supported_claims"] == 0
    )


@pytest.mark.parametrize("change", ["hash", "cases", "extraction", "reviews"])
def test_inconsistent_frozen_population_or_provenance_is_rejected(population, change):
    before, cases, examples = population
    after = deepcopy(before)
    reviews = {"items": [], "input_hashes": {"demo.json": "hash"}}
    if change == "hash":
        after["signature"]["inputs"]["demo.json"] = "changed"
    elif change == "cases":
        after["agent_cases"].pop()
    elif change == "extraction":
        after["extraction"] = []
    else:
        reviews["input_hashes"]["demo.json"] = "changed"
    with pytest.raises(ValueError):
        compare_final(before, after, cases, examples, reviews)


def test_named_recall_excludes_substitute_selections(population):
    result, cases, _ = population
    result["agent_cases"][0]["recommendations"] = [candidate(999)]
    assert named_recall(cases, result["agent_cases"], "recommendations")["recall"] == 0
    assert named_recall(cases, result["agent_cases"], "assessments")["recall"] == 2 / 3
    assert named_recall(cases, result["agent_cases"], "assisted")["recall"] == 1


def test_phase_6c_miss_analysis_uses_observed_traces_without_alias_speculation():
    root = Path(__file__).resolve().parents[2]
    result = read_json(root / "evaluation/results/reliability_after_2026-11-13.json")
    analysis = analyze_misses(
        result,
        read_json(DATA / "eligibility_cases.json")["cases"],
        read_json(CATALOGUE)["scholarships"],
    )
    assert analysis["missed_targets"] == 34
    assert all(case["target_preseeded"] for case in analysis["cases"])
    assert analysis["observed_nonexclusive_flag_counts"] == {
        "budget_stop": 18,
        "incorrect_search_filters": 34,
        "invalid_final_schema": 4,
        "missing_target_assessment": 34,
        "outside_named_target": 17,
        "wrong_requested_ids": 21,
    }
    assert analysis["aliases_and_abbreviations"]["status"] == "NOT_ASSESSED"


def test_cli_rejects_edited_review_snapshot_without_creating_metrics(
    tmp_path, monkeypatch
):
    package = tmp_path / "review-package"
    generate_package(package)
    snapshot = validate_reviews(package)
    # This deliberately forged derived record is a fictional attack fixture.
    # The actual assigned CSV decisions remain blank.
    item = snapshot["items"][0]
    item.update(
        status="reviewed",
        reviewed_value="eligible",
        reviewers=list(item["assigned_reviewers"]),
    )
    snapshot["summary"]["human_reviewed_items"] = 1
    reviews_path = tmp_path / "forged-snapshot.json"
    reviews_path.write_text(json.dumps(snapshot), encoding="utf-8")
    output = tmp_path / "metrics.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "final",
            "--before",
            str(tmp_path / "unused-before.json"),
            "--after",
            str(tmp_path / "unused-after.json"),
            "--review-package",
            str(package),
            "--reviews",
            str(reviews_path),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(ValueError, match="snapshot differs"):
        final_module.main()
    assert not output.exists()
    assert validate_reviews(package)["summary"]["human_reviewed_items"] == 0


@pytest.mark.parametrize("include_snapshot", [False, True])
def test_cli_derives_reviews_from_actual_sheets(
    tmp_path, monkeypatch, include_snapshot
):
    package = tmp_path / "review-package"
    generate_package(package)
    validated = validate_reviews(package)
    before_path, after_path = tmp_path / "before.json", tmp_path / "after.json"
    before_path.write_text("{}", encoding="utf-8")
    after_path.write_text(
        json.dumps(
            {
                "signature": {
                    "inputs": validated["input_hashes"],
                    "as_of": validated["as_of"],
                    "implementation": {},
                }
            }
        ),
        encoding="utf-8",
    )
    observed = []

    def compare(before, after, cases, examples, reviews):
        observed.append(reviews)
        return {"human_review_status": reviews["summary"]}

    monkeypatch.setattr(final_module, "compare_final", compare)
    output = tmp_path / "metrics.json"
    argv = [
        "final",
        "--before",
        str(before_path),
        "--after",
        str(after_path),
        "--review-package",
        str(package),
        "--output",
        str(output),
    ]
    if include_snapshot:
        snapshot_path = tmp_path / "review-snapshot.json"
        snapshot_path.write_text(json.dumps(validated), encoding="utf-8")
        argv.extend(["--reviews", str(snapshot_path)])
    monkeypatch.setattr(sys, "argv", argv)
    final_module.main()
    result = json.loads(output.read_text(encoding="utf-8"))
    assert observed == [validated]
    assert result["human_review_status"]["human_reviewed_items"] == 0
    assert result["sources"]["review_package"] == package.as_posix()
    assert bool(result["sources"]["reviews"]) == include_snapshot
    assert "backend/evaluation/reviews.py" in result["postprocessing_hashes"]
