"""Frozen retrieval comparison and independently reviewed academic metrics.

python -m backend.evaluation.final --before BEFORE --after AFTER \
    --review-package evaluation/human_review --output OUTPUT --miss-analysis ANALYSIS
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from backend.app.schemas import ScholarshipQuery
from backend.evaluation.extract import EXTRACTION_KEYS
from backend.evaluation.metrics import (
    STATUSES,
    citation_metrics,
    extraction_metrics,
    precision_at_3,
)
from backend.evaluation.reliability import (
    assisted_candidates,
    input_signature,
    ratio,
    retention_metrics,
    round_metrics,
    unique_index,
    validate_comparable,
)
from backend.evaluation.reviews import PACKAGE, canonical_json, validate_reviews
from backend.evaluation.run import (
    CATALOGUE,
    DATA,
    INPUT_FILES,
    ROOT,
    case_predictions,
    file_hashes,
    operational_metrics,
    output_facts,
    read_json,
    write_checkpoint,
)

NOT_EVALUABLE = "NOT_EVALUABLE"


def target_predictions(cases: list[dict], runs: list[dict], field: str) -> dict:
    """Read target assessments without accepting substitute programmes."""
    definitions = unique_index(cases, "id")
    indexed = unique_index(runs, "case_id")
    if not set(indexed).issubset(definitions):
        raise ValueError("Unknown named-target case")
    predictions = {}
    for identifier, run in indexed.items():
        expected = definitions[identifier]["scholarship_name"]
        records = (
            assisted_candidates(run) if field == "assisted" else run.get(field, [])
        )
        matches = [item for item in records if item["scholarship_name"] == expected]
        if len(matches) > 1:
            raise ValueError("Duplicate target assessments")
        if matches:
            predictions[identifier] = matches[0]["status"]
    return predictions


def named_recall(cases: list[dict], runs: list[dict], field: str) -> dict:
    predictions = target_predictions(cases, runs, field)
    return {
        "requested_cases": len(cases),
        "targets_returned": len(predictions),
        "recall": ratio(len(predictions), len(cases)),
        "scope": "Named catalogue target retrieval with no relevance assumption",
    }


def _excluded_filters(record: dict, arguments: dict) -> list[str]:
    """Apply the existing public catalogue's literal filter semantics."""
    query = ScholarshipQuery(
        **{
            key: value
            for key, value in arguments.items()
            if key in {"country", "field", "funding_type"}
        }
    )
    excluded = []
    if query.country is not None and not any(
        value.casefold() == query.country.casefold()
        for value in record.get("destination_country") or []
    ):
        excluded.append("country")
    if query.field is not None and not any(
        query.field.casefold() in value.casefold()
        for value in record.get("eligible_study_fields") or []
    ):
        excluded.append("field")
    if (
        query.funding_type is not None
        and query.funding_type.value != record["funding_type"]
    ):
        excluded.append("funding_type")
    return excluded


def analyze_misses(result: dict, cases: list[dict], catalogue: list[dict]) -> dict:
    """Record observed, nonexclusive events in failed model target retrieval."""
    definitions = unique_index(cases, "id")
    records = unique_index(catalogue, "scholarship_name")
    targets = target_predictions(cases, result["agent_cases"], "assessments")
    baseline = unique_index(result["baseline"], "profile_id")
    missed = []
    for run in result["agent_cases"]:
        identifier = run["case_id"]
        if identifier in targets:
            continue
        case = definitions[identifier]
        name = case["scholarship_name"]
        target = next(
            item
            for item in baseline[case["profile_id"]]["assessments"]
            if item["scholarship_name"] == name
        )
        target_id = target["scholarship_id"]
        searches, requested_ids = [], set()
        blocked_without_id = 0
        for event in run["trace"]:
            arguments = event.get("arguments", {})
            if event["name"] == "search_scholarships" and event["status"] == "ok":
                searches.append(
                    {
                        "arguments": arguments,
                        "target_excluded_by": _excluded_filters(
                            records[name], arguments
                        ),
                    }
                )
            if event["name"] == "check_eligibility":
                if "scholarship_id" in arguments:
                    requested_ids.add(arguments["scholarship_id"])
                elif event["status"] == "blocked":
                    blocked_without_id += 1
            if event["name"] == "rank_scholarships":
                requested_ids.update(arguments.get("scholarship_ids", []))
        rounds = run.get("rounds", [])
        wrong_final = sorted(
            {
                value
                for event in rounds
                for value in event.get("final_ids", [])
                if value != target_id
            }
        )
        counts = Counter(event.get("final_validation") for event in rounds)
        preseeded = target_id in run.get("discovery_candidate_ids", [])
        missed.append(
            {
                "case_id": identifier,
                "profile_id": case["profile_id"],
                "scholarship_name": name,
                "target_id": target_id,
                "target_preseeded": preseeded,
                "flags": {
                    "missing_target_assessment": True,
                    "name_matching_failure": not preseeded,
                    "incorrect_search_filters": any(
                        item["target_excluded_by"] for item in searches
                    ),
                    "wrong_requested_ids": bool(requested_ids - {target_id}),
                    "invalid_final_schema": counts["invalid_schema"] > 0,
                    "outside_named_target": counts["outside_named_target"] > 0,
                    "budget_stop": run["status"] == "limit_reached",
                },
                "searches": searches,
                "wrong_requested_ids": sorted(requested_ids - {target_id}),
                "wrong_final_ids": wrong_final,
                "blocked_checks_without_recorded_id": blocked_without_id,
                "final_validation_counts": {
                    key: value for key, value in counts.items() if key is not None
                },
                "status": run["status"],
            }
        )
    flags = Counter(
        key for item in missed for key, value in item["flags"].items() if value
    )
    return {
        "requested_cases": len(cases),
        "missed_targets": len(missed),
        "observed_nonexclusive_flag_counts": dict(sorted(flags.items())),
        "aliases_and_abbreviations": {
            "status": "NOT_ASSESSED",
            "reason": "Frozen case goals use complete canonical programme names",
        },
        "scope": (
            "Observed co-occurrences in missed target assessments. Filter exclusions "
            "use the existing catalogue query rules. A filter exclusion does not "
            "establish ineligibility. Raw invalid model prose was not retained. "
            "Blocked attempts without recorded IDs cannot identify the attempted ID."
        ),
        "cases": missed,
    }


def reviewed_items(review_result: dict, category: str) -> list[dict]:
    items = review_result.get("items", [])
    unique_index(items, "id")
    reviewed = [
        item
        for item in items
        if item["category"] == category and item["status"] == "reviewed"
    ]
    for item in reviewed:
        reviewers = item.get("reviewers", [])
        if len(set(reviewers)) < 2:
            raise ValueError("Reviewed labels require two independent reviewers")
    return reviewed


def _label_counts(expected: dict, predicted: dict) -> dict:
    assessed = sum(predicted.get(identifier) in STATUSES for identifier in expected)
    correct = sum(
        predicted.get(identifier) == value for identifier, value in expected.items()
    )
    return {
        "reviewed_cases": len(expected),
        "assessed_reviewed_cases": assessed,
        "correct": correct,
        "missing_or_invalid": len(expected) - assessed,
        "reviewed_subset_accuracy": ratio(correct, len(expected)),
        "conditional_accuracy_among_assessed": ratio(correct, assessed),
    }


def human_eligibility(result: dict, cases: list[dict], reviews: dict) -> dict:
    definitions = unique_index(cases, "id")
    labels = {}
    for item in reviewed_items(reviews, "eligibility"):
        identifier = item["case_id"]
        case = definitions[identifier]
        if (
            item["profile_id"] != case["profile_id"]
            or item["scholarship_name"] != case["scholarship_name"]
            or item["reviewed_value"] not in STATUSES
            or identifier in labels
        ):
            raise ValueError("Human eligibility label conflicts with the frozen case")
        labels[identifier] = item["reviewed_value"]
    classes = Counter(labels.values())
    complete = len(labels) == len(cases) and bool(cases)
    three_classes = all(classes[status] for status in STATUSES)
    evaluable = complete and three_classes
    raw = target_predictions(cases, result["agent_cases"], "assessments")
    assisted = target_predictions(cases, result["agent_cases"], "assisted")
    methods = {
        "deterministic_baseline": case_predictions(cases, result["baseline"]),
        "raw_qwen_tool_assessments": raw,
        "qwen_with_deterministic_assistance": assisted,
    }
    return {
        "status": "MEASURED" if evaluable else NOT_EVALUABLE,
        "total_cases": len(cases),
        "reviewed_cases": len(labels),
        "excluded_pending_or_unresolved_cases": len(cases) - len(labels),
        "reviewed_class_counts": {status: classes[status] for status in STATUSES},
        "methods": {
            name: _label_counts(labels, predictions)
            | {
                "eligibility_accuracy": ratio(
                    sum(predictions.get(key) == value for key, value in labels.items()),
                    len(labels),
                )
                if evaluable
                else None
            }
            for name, predictions in methods.items()
        },
        "target_status": "EVALUABLE" if evaluable else NOT_EVALUABLE,
        "reason": (
            "Final three-class accuracy requires complete independent review and "
            "human examples of each class. Partial human-subset diagnostics remain "
            "separate. Missing target predictions count against their denominator."
        ),
    }


def human_extraction(result: dict, examples: list[dict], reviews: dict) -> dict:
    definitions = unique_index(examples, "id")
    by_example = {identifier: {} for identifier in definitions}
    for item in reviewed_items(reviews, "extraction"):
        fields = by_example[item["example_id"]]
        if item["field"] not in EXTRACTION_KEYS or item["field"] in fields:
            raise ValueError("Duplicate or unknown human extraction slot")
        fields[item["field"]] = item["reviewed_value"]
    complete = [
        {
            "id": identifier,
            "annotation_status": "source_checked",
            "expected_fields": fields,
        }
        for identifier, fields in by_example.items()
        if set(fields) == set(EXTRACTION_KEYS)
    ]
    predictions = {
        item["example_id"]: item["fields"] for item in result.get("extraction", [])
    }
    measured = extraction_metrics(complete, predictions)
    evaluable = len(complete) == len(examples) and measured["status"] == "MEASURED"
    return {
        "status": "MEASURED" if evaluable else NOT_EVALUABLE,
        "total_examples": len(examples),
        "reviewed_slots": sum(len(fields) for fields in by_example.values()),
        "required_slots": len(examples) * len(EXTRACTION_KEYS),
        "fully_reviewed_examples": len(complete),
        "precision": measured["precision"] if evaluable else None,
        "recall": measured["recall"] if evaluable else None,
        "f1": measured["f1"] if evaluable else None,
        "reviewed_subset_counts": {
            key: measured[key] for key in ("tp", "fp", "fn", "predicted_examples")
        },
        "target_status": "EVALUABLE" if evaluable else NOT_EVALUABLE,
        "reason": (
            "All requested slots of an excerpt need independent review before "
            "closed-excerpt precision is scored. Reviewed null slots assert absence. "
            "Partial or unresolved examples are excluded from final F1."
        ),
    }


def human_relevance(result: dict, reviews: dict) -> dict:
    eligibility = {
        (item["profile_id"], item["scholarship_name"]): item["reviewed_value"]
        for item in reviewed_items(reviews, "eligibility")
    }
    judgments = [
        {
            "profile_id": item["profile_id"],
            "scholarship_name": item["scholarship_name"],
            "label_status": "verified_gold",
            "relevant": item["reviewed_value"],
            "eligibility_status": eligibility.get(
                (item["profile_id"], item["scholarship_name"])
            ),
        }
        for item in reviewed_items(reviews, "relevance")
        if type(item["reviewed_value"]) is bool
    ]
    methods = {
        "deterministic_baseline": result["baseline"],
        "raw_qwen": result["agent"],
        "qwen_with_deterministic_assistance": [
            run | {"recommendations": assisted_candidates(run)}
            for run in result["agent"]
        ],
    }
    metrics = {name: precision_at_3(runs, judgments) for name, runs in methods.items()}
    complete = bool(metrics) and all(
        item["target_status"] == "EVALUABLE" for item in metrics.values()
    )
    return {
        "status": "MEASURED" if complete else NOT_EVALUABLE,
        "reviewed_relevance_labels": len(judgments),
        "methods": metrics,
        "target_status": "EVALUABLE" if complete else NOT_EVALUABLE,
        "reason": (
            "Each profile needs three human-reviewed relevant and eligible "
            "opportunities plus judgments for every returned top-three record. "
            "Engine classifications cannot supply missing human eligibility labels."
        ),
    }


def human_citations(result: dict, reviews: dict) -> dict:
    annotations = [
        {
            "annotation_status": "source_checked",
            "scholarship_name": item["scholarship_name"],
            "source_url": item["source_url"],
            "claims": [
                {
                    "field": item["field"],
                    "value": item["claim_value"],
                    "support": item["reviewed_value"],
                }
            ],
        }
        for item in reviewed_items(reviews, "citation")
        if item["reviewed_value"] in {"supported", "unsupported"}
    ]
    methods = {
        "deterministic_baseline": output_facts(result["baseline"]),
        "raw_qwen": output_facts(result["agent"]),
        "qwen_with_deterministic_assistance": output_facts(
            [
                run | {"recommendations": assisted_candidates(run)}
                for run in result["agent"]
            ]
        ),
    }
    metrics = {}
    for name, facts in methods.items():
        scored = citation_metrics(facts, annotations)
        metrics[name] = scored | {
            "human_support_status": "MEASURED"
            if scored["audited_claims"] == scored["claims"] and facts
            else NOT_EVALUABLE,
            "scope": "Emitted programme names and funding labels only",
        }
    return {
        "methods": metrics,
        "reviewed_claim_source_pairs": len(annotations),
        "target_status": NOT_EVALUABLE,
        "target_achieved": None,
        "reason": (
            "HTTPS link presence is an engineering measurement. Human support "
            "covers reviewed exact claim/value/source pairs. Complete factual "
            "support additionally requires auditing requirement explanations and "
            "student-specific conclusions."
        ),
    }


def operational_summary(result: dict, cases: list[dict]) -> dict:
    raw = [
        run | {"error": run.get("error") or run.get("model_error")}
        for run in result["agent"]
    ]
    assisted = [run | {"recommendations": assisted_candidates(run)} for run in raw]
    case_runs = result["agent_cases"]
    baseline_targets = case_predictions(cases, result["baseline"])
    raw_final_targets = target_predictions(cases, case_runs, "recommendations")
    assisted_targets = target_predictions(cases, case_runs, "assisted")
    return {
        "baseline": operational_metrics(result["baseline"]),
        "raw_qwen": operational_metrics(raw),
        "qwen_with_deterministic_assistance": operational_metrics(assisted),
        "retention": retention_metrics(result["baseline"], raw),
        "named_targets": {
            "deterministic_baseline": {
                "requested_cases": len(cases),
                "targets_returned": len(baseline_targets),
                "recall": ratio(len(baseline_targets), len(cases)),
                "scope": "Full-catalogue deterministic assessments",
            },
            "raw_tool_assessment": named_recall(cases, case_runs, "assessments"),
            "raw_final_selection": named_recall(cases, case_runs, "recommendations"),
            "assisted_response": named_recall(cases, case_runs, "assisted"),
        },
        "case_operational": operational_metrics(
            [
                run | {"error": run.get("error") or run.get("model_error")}
                for run in case_runs
            ]
        ),
        "general_rounds": round_metrics(raw),
        "case_rounds": round_metrics(case_runs),
        "explicit_fallback_responses": sum(
            bool(run.get("fallback_recommendations")) for run in raw
        ),
        "case_explicit_fallback_responses": sum(
            bool(run.get("fallback_recommendations")) for run in case_runs
        ),
        "case_assistance_needed_requests": len(
            set(assisted_targets) - set(raw_final_targets)
        ),
    }


def compare_final(
    before: dict, after: dict, cases: list[dict], examples: list[dict], reviews: dict
) -> dict:
    validate_comparable(before, after)
    expected_cases = set(unique_index(cases, "id"))
    expected_examples = set(unique_index(examples, "id"))
    for result in (before, after):
        if set(unique_index(result["agent_cases"], "case_id")) != expected_cases:
            raise ValueError("Named-target benchmark population is incomplete")
        if (
            set(unique_index(result.get("extraction", []), "example_id"))
            != expected_examples
        ):
            raise ValueError("Extraction benchmark population is incomplete")
    if reviews.get("input_hashes") != input_signature(after)[0]:
        raise ValueError("Human reviews and benchmark input hashes differ")
    preliminary = after.get("metrics", {}).get("extraction_probe")
    return {
        "schema_version": 1,
        "as_of": input_signature(after)[1],
        "input_hashes": input_signature(after)[0],
        "before": operational_summary(before, cases),
        "after": operational_summary(after, cases),
        "human_review_status": reviews.get("summary", {}),
        "human_review_manifest_sha256": reviews.get("manifest_sha256"),
        "human_metrics": {
            "eligibility": human_eligibility(after, cases, reviews),
            "extraction": human_extraction(after, examples, reviews),
            "precision_at_3": human_relevance(after, reviews),
            "citations": human_citations(after, reviews),
        },
        "provisional_extraction_probe": {
            "metrics": preliminary,
            "annotation_origin": "AI-authored provisional source annotations",
            "academic_target_status": NOT_EVALUABLE,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--review-package", type=Path, default=PACKAGE)
    parser.add_argument(
        "--reviews",
        type=Path,
        help="Optional snapshot checked against actual review sheets",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--miss-analysis", type=Path)
    arguments = parser.parse_args()
    reviews = validate_reviews(arguments.review_package)
    if arguments.reviews and canonical_json(
        read_json(arguments.reviews)
    ) != canonical_json(reviews):
        raise ValueError("Review snapshot differs from validated human review sheets")
    before, after = read_json(arguments.before), read_json(arguments.after)
    if input_signature(after)[0] != file_hashes(INPUT_FILES):
        raise ValueError("Local frozen input hashes differ from the experiment")
    implementation = after["signature"]["implementation"]
    if implementation != file_hashes([ROOT / name for name in implementation]):
        raise ValueError("Current implementation differs from the recorded experiment")
    cases = read_json(DATA / "eligibility_cases.json")["cases"]
    examples = read_json(DATA / "source_annotations.json")["examples"]
    result = compare_final(before, after, cases, examples, reviews)
    result["sources"] = {
        "before": arguments.before.as_posix(),
        "after": arguments.after.as_posix(),
        "review_package": arguments.review_package.as_posix(),
        "reviews": arguments.reviews.as_posix() if arguments.reviews else None,
    }
    result["postprocessing_hashes"] = file_hashes(
        [Path(__file__), Path(__file__).with_name("reviews.py")]
    )
    write_checkpoint(arguments.output, result)
    if arguments.miss_analysis:
        analysis = analyze_misses(before, cases, read_json(CATALOGUE)["scholarships"])
        analysis["input_hashes"] = input_signature(before)[0]
        analysis["source_result"] = arguments.before.as_posix()
        write_checkpoint(arguments.miss_analysis, analysis)
    print(json.dumps(result["human_review_status"], indent=2))


if __name__ == "__main__":
    main()
