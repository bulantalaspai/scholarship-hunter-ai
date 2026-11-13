"""Compare frozen Phase 6B results with a real Phase 6C evaluation.

python -m backend.evaluation.reliability --before BEFORE --after AFTER --output OUTPUT
An optional --fresh-before file retains the same-day 20-profile reproduction.
"""

import argparse
import json
import statistics
from pathlib import Path

from backend.evaluation.metrics import citation_metrics
from backend.evaluation.run import (
    DATA,
    INPUT_FILES,
    file_hashes,
    operational_metrics,
    output_facts,
    read_json,
    write_checkpoint,
)

NOT_EVALUABLE = "NOT_EVALUABLE"


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def unique_index(items: list[dict], key: str) -> dict:
    indexed = {item[key]: item for item in items}
    if len(indexed) != len(items):
        raise ValueError(f"Evaluation {key} values must be unique")
    return indexed


def input_signature(result: dict) -> tuple[dict, str]:
    signature = result.get("signature", {})
    hashes = signature.get("inputs", result.get("input_hashes"))
    as_of = signature.get("as_of", result.get("as_of"))
    if not isinstance(hashes, dict) or not hashes or not as_of:
        raise ValueError("Evaluation requires input hashes and an assessment date")
    return hashes, as_of


def validate_comparable(*results: dict) -> None:
    """Reject comparisons across different data, dates or profile populations."""
    first = input_signature(results[0])
    profiles = set(unique_index(results[0]["baseline"], "profile_id"))
    for result in results:
        if input_signature(result) != first:
            raise ValueError("Evaluation input hashes or assessment dates differ")
        baseline_ids = set(unique_index(result["baseline"], "profile_id"))
        agent_ids = set(unique_index(result["agent"], "profile_id"))
        if baseline_ids != profiles or agent_ids != profiles:
            raise ValueError("Evaluation profile populations differ or are incomplete")


def candidate_ids(items: list[dict]) -> set[int]:
    return {item["scholarship_id"] for item in items}


def assisted_candidates(run: dict) -> list[dict]:
    """Retain canonical discovery alongside actual model selections, once per ID."""
    retained = run.get("discovery_candidates", run.get("fallback_recommendations", []))
    indexed = {item["scholarship_id"]: item for item in retained}
    for item in run["recommendations"]:
        indexed.setdefault(item["scholarship_id"], item)
    return list(indexed.values())


def retention_metrics(baseline: list[dict], agent: list[dict]) -> dict:
    indexed = unique_index(baseline, "profile_id")
    unique_index(agent, "profile_id")
    profiles = []
    for run in agent:
        reference = indexed[run["profile_id"]]
        expected_top = candidate_ids(reference["recommendations"])
        expected_pool = candidate_ids(
            [
                item
                for item in reference["assessments"]
                if item["status"] != "ineligible"
            ]
        )
        discovered = candidate_ids(run.get("discovery_candidates", []))
        raw = candidate_ids(run["recommendations"])
        assisted = candidate_ids(assisted_candidates(run))
        full_pool = run.get("discovery_candidate_ids")
        profiles.append(
            {
                "profile_id": run["profile_id"],
                "baseline_top_three": len(expected_top),
                "canonical_top_three_retained": len(expected_top & discovered)
                if "discovery_candidates" in run
                else None,
                "assisted_top_three_retained": len(expected_top & assisted),
                "baseline_viable_pool": len(expected_pool),
                "full_pool_retained": len(expected_pool & set(full_pool))
                if full_pool is not None
                else None,
                "full_pool_unexpected_ids": sorted(set(full_pool) - expected_pool)
                if full_pool is not None
                else None,
                "raw_candidates": len(raw),
                "assisted_unique_candidates": len(assisted),
                "raw_canonical_overlap": len(raw & discovered),
                "deterministic_assistance_needed": bool(assisted - raw),
                "assistance_only_response": bool(assisted) and not raw,
                "assisted_without_confirmed_failure": any(
                    item["status"] != "ineligible" for item in assisted_candidates(run)
                ),
            }
        )
    pool_observed = [x for x in profiles if x["full_pool_retained"] is not None]
    top_observed = [
        x for x in profiles if x["canonical_top_three_retained"] is not None
    ]
    pool_expected = sum(x["baseline_viable_pool"] for x in pool_observed)
    pool_retained = sum(x["full_pool_retained"] for x in pool_observed)
    top_expected = sum(x["baseline_top_three"] for x in top_observed)
    top_retained = sum(x["canonical_top_three_retained"] for x in top_observed)
    assistance = sum(x["deterministic_assistance_needed"] for x in profiles)
    return {
        "profiles": profiles,
        "requests": len(profiles),
        "canonical_top_three_observed_requests": len(top_observed),
        "canonical_top_three_expected": top_expected,
        "canonical_top_three_retained": top_retained,
        "canonical_top_three_retention": ratio(top_retained, top_expected),
        "full_pool_observed_requests": len(pool_observed),
        "full_pool_expected": pool_expected,
        "full_pool_retained": pool_retained,
        "full_pool_retention_recall": ratio(pool_retained, pool_expected),
        "assisted_top_three_retention": ratio(
            sum(x["assisted_top_three_retained"] for x in profiles),
            sum(x["baseline_top_three"] for x in profiles),
        ),
        "deterministic_assistance_needed_requests": assistance,
        "deterministic_assistance_needed_frequency": ratio(assistance, len(profiles)),
        "assistance_only_responses": sum(
            x["assistance_only_response"] for x in profiles
        ),
        "scope": (
            "Retention against deterministic retrieval of uncertain candidates. "
            "Relevant or truly eligible candidate recall remains NOT EVALUABLE. "
            "Assistance is needed when public candidates contain IDs absent from "
            "the raw model selection. Canonical discovery presence alone is excluded."
        ),
    }


def label_agreement(cases: list[dict], predictions: dict) -> dict:
    observed = [case for case in cases if case["id"] in predictions]
    correct = sum(
        predictions.get(case["id"]) == case["expected_status"] for case in cases
    )
    return {
        "cases": len(cases),
        "assessed_cases": len(observed),
        "assessment_coverage": ratio(len(observed), len(cases)),
        "agreement_count": correct,
        "end_to_end_agreement": ratio(correct, len(cases)),
        "agreement_among_assessed": ratio(correct, len(observed)),
        "wrong_verdicts_among_assessed": len(observed) - correct,
        "missing_targets": len(cases) - len(observed),
    }


def case_assessment_metrics(cases: list[dict], runs: list[dict], field: str) -> dict:
    indexed = unique_index(runs, "case_id")
    definitions = unique_index(cases, "id")
    if not set(indexed).issubset(definitions):
        raise ValueError("Evaluation contains an unknown case ID")
    selected = [case for case in cases if case["id"] in indexed]
    predictions = {}
    for case in selected:
        matches = [
            item
            for item in indexed[case["id"]].get(field, [])
            if item["scholarship_name"] == case["scholarship_name"]
        ]
        if len(matches) > 1:
            raise ValueError("A named target must have one assessment")
        if matches:
            predictions[case["id"]] = matches[0]["status"]
    negative = [
        case
        for case in selected
        if case["label_status"] == "verified_gold"
        and case["expected_status"] == "ineligible"
    ]
    provisional = [
        case
        for case in selected
        if case["label_status"] == "provisional" and case["expected_status"] is not None
    ]
    return {
        "requested_cases": len(selected),
        "all_documented_cases": len(cases),
        "assessed_targets": len(predictions),
        "target_assessment_coverage": ratio(len(predictions), len(selected)),
        "source_checked_negative_agreement": label_agreement(negative, predictions),
        "provisional_expectation_agreement": label_agreement(provisional, predictions),
        "unresolved_cases": sum(case["expected_status"] is None for case in selected),
        "target_verdicts": {
            status: sum(value == status for value in predictions.values())
            for status in ("eligible", "ineligible", "needs_verification")
        },
        "scope": (
            "Agreement with frozen AI-authored source-checked or provisional labels. "
            "Independent human review is pending. This is not validated gold accuracy."
        ),
    }


def round_metrics(runs: list[dict]) -> dict:
    rounds = [event for run in runs for event in run.get("rounds", [])]
    estimates = [event["estimated_input_tokens"] for event in rounds]
    measured = [
        event["prompt_tokens"] for event in rounds if event.get("prompt_tokens")
    ]
    return {
        "model_rounds": len(rounds),
        "mean_rounds_per_request": ratio(len(rounds), len(runs)),
        "maximum_rounds_per_request": max(
            (len(run.get("rounds", [])) for run in runs), default=0
        ),
        "maximum_estimated_input_tokens": max(estimates, default=None),
        "maximum_reported_prompt_tokens": max(measured, default=None),
        "context_budget_stops": sum(
            any(
                "context budget" in warning.lower()
                for warning in run.get("warnings", [])
            )
            for run in runs
        ),
        "invalid_schema_rounds": sum(
            event.get("final_validation") == "invalid_schema" for event in rounds
        ),
        "unassessed_selection_rounds": sum(
            event.get("final_validation") == "unassessed_ids" for event in rounds
        ),
        "outside_named_target_rounds": sum(
            event.get("final_validation") == "outside_named_target" for event in rounds
        ),
        "invalid_explanation_reference_rounds": sum(
            event.get("final_validation") == "invalid_explanation_reference"
            for event in rounds
        ),
        "mean_round_seconds": statistics.mean(event["seconds"] for event in rounds)
        if rounds
        else None,
    }


def experiment_summary(result: dict, cases: list[dict], examples: list[dict]) -> dict:
    agent = result["agent"]
    # Handled model errors still count as failed model attempts.
    observed = [
        run | {"error": run.get("error") or run.get("model_error")} for run in agent
    ]
    assisted = [run | {"recommendations": assisted_candidates(run)} for run in observed]
    audited = result.get("agent_cases", result.get("diagnostic_cases", []))
    citations = {}
    for name, field in (
        ("raw_model", "recommendations"),
        ("canonical_discovery", "discovery_candidates"),
        ("legacy_fallback", "fallback_recommendations"),
    ):
        citations[name] = citation_metrics(output_facts(agent, field), examples)
        citations[name].update(
            target_status=NOT_EVALUABLE,
            target_achieved=None,
            scope="Programme names and funding labels only; human claim audit pending",
        )
    return {
        "baseline_operational": operational_metrics(result["baseline"]),
        "raw_model_operational": operational_metrics(observed),
        "assisted_operational": operational_metrics(assisted),
        "handled_model_errors": sum(
            run.get("model_error") is not None for run in agent
        ),
        "unhandled_model_exceptions": sum(
            run.get("error") is not None for run in agent
        ),
        "model_error_types": {
            kind: sum(run.get("model_error") == kind for run in agent)
            for kind in ("unavailable", "timeout", "invalid_response", "busy")
        },
        "retention": retention_metrics(result["baseline"], agent),
        "model_rounds": round_metrics(agent),
        "case_model_assessments": case_assessment_metrics(
            cases, audited, "assessments"
        ),
        "case_canonical_assessments": case_assessment_metrics(
            cases, audited, "discovery_candidates"
        ),
        "case_model_rounds": round_metrics(audited),
        "case_operational": operational_metrics(
            [
                run | {"error": run.get("error") or run.get("model_error")}
                for run in audited
            ]
        ),
        "grounded_explanation_responses": sum(
            bool(run.get("model_explanations")) for run in agent
        ),
        "citations": citations,
        "extraction_probe": result.get("metrics", {}).get("extraction_probe"),
    }


def compare_experiments(
    before: dict,
    after: dict,
    cases: list[dict],
    examples: list[dict],
    *,
    fresh_before: dict | None = None,
) -> dict:
    results = [before, after] + ([fresh_before] if fresh_before is not None else [])
    validate_comparable(*results)
    before_cases = set(unique_index(before.get("agent_cases", []), "case_id"))
    after_cases = set(unique_index(after.get("agent_cases", []), "case_id"))
    if before_cases != after_cases:
        raise ValueError("Before and after case request populations differ")
    hashes, as_of = input_signature(after)
    comparisons = {
        "prior_phase_6b": experiment_summary(before, cases, examples),
        "phase_6c": experiment_summary(after, cases, examples),
    }
    if fresh_before is not None:
        comparisons["fresh_before_phase_6c"] = experiment_summary(
            fresh_before, cases, examples
        )
    return {
        "schema_version": 1,
        "as_of": as_of,
        "input_hashes": hashes,
        "comparisons": comparisons,
        "proposal_targets": {
            metric: {
                "status": NOT_EVALUABLE,
                "achieved": None,
                "reason": reason,
            }
            for metric, reason in {
                "eligibility_accuracy": (
                    "AI-authored labels await human review "
                    "and lack positive gold classes."
                ),
                "extraction_f1": (
                    "Short-excerpt annotations await independent human review "
                    "and broader sampling."
                ),
                "precision_at_3": (
                    "Profiles lack three independently verified eligible "
                    "and relevant positives."
                ),
                "citation_coverage": (
                    "Link presence is measured in a limited claim scope. "
                    "Complete independent support auditing is pending."
                ),
            }.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--fresh-before", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    after = read_json(arguments.after)
    if input_signature(after)[0] != file_hashes(INPUT_FILES):
        raise ValueError("Local annotations or catalogue differ from evaluated inputs")
    result = compare_experiments(
        read_json(arguments.before),
        after,
        read_json(DATA / "eligibility_cases.json")["cases"],
        read_json(DATA / "source_annotations.json")["examples"],
        fresh_before=read_json(arguments.fresh_before)
        if arguments.fresh_before
        else None,
    )
    result["source_files"] = {
        "before": arguments.before.as_posix(),
        "after": arguments.after.as_posix(),
        "fresh_before": arguments.fresh_before.as_posix()
        if arguments.fresh_before
        else None,
    }
    write_checkpoint(arguments.output, result)
    print(json.dumps(result["proposal_targets"], indent=2))


if __name__ == "__main__":
    main()
