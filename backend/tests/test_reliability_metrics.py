"""Synthetic reliability metrics keep model and deterministic attribution distinct."""

from copy import deepcopy

import pytest

from backend.evaluation.reliability import (
    assisted_candidates,
    case_assessment_metrics,
    compare_experiments,
    experiment_summary,
    retention_metrics,
    round_metrics,
    validate_comparable,
)


def candidate(identifier, status="needs_verification"):
    return {
        "scholarship_id": identifier,
        "scholarship_name": f"Fictional demo {identifier}",
        "status": status,
        "ranking_reasons": [],
        "source_url": "https://example.org/demo",
    }


def run(*, recommendations=None, assessments=None, **extra):
    return {
        "profile_id": "P1",
        "seconds": 1.0,
        "status": "completed",
        "error": None,
        "recommendations": recommendations or [],
        "assessments": assessments or [],
        "trace": [],
        "rounds": [],
        **extra,
    }


def experiment():
    record = candidate(1)
    return {
        "signature": {"inputs": {"demo.json": "hash"}, "as_of": "2026-11-12"},
        "baseline": [run(recommendations=[record], assessments=[record])],
        "agent": [run()],
        "agent_cases": [],
    }


def test_retention_counts_missing_candidates_and_excludes_known_negatives():
    a, b, negative = candidate(1), candidate(2), candidate(3, "ineligible")
    result = retention_metrics(
        [run(recommendations=[a, b], assessments=[a, b, negative])],
        [run(discovery_candidates=[a], discovery_candidate_ids=[1])],
    )
    assert result["full_pool_expected"] == 2
    assert result["full_pool_retained"] == 1
    assert result["full_pool_retention_recall"] == 0.5
    assert result["canonical_top_three_retention"] == 0.5
    assert result["assistance_only_responses"] == 1


def test_absent_discovery_measurement_is_unavailable_and_empty_pool_has_no_recall():
    before = retention_metrics([run()], [run()])
    assert before["full_pool_observed_requests"] == 0
    assert before["full_pool_retention_recall"] is None
    assert before["canonical_top_three_retention"] is None
    empty = retention_metrics(
        [run()], [run(discovery_candidates=[], discovery_candidate_ids=[])]
    )
    assert empty["full_pool_observed_requests"] == 1
    assert empty["full_pool_expected"] == 0
    assert empty["full_pool_retention_recall"] is None


def test_discovery_presence_is_not_counted_as_needed_assistance_when_model_retains_it():
    record = candidate(1)
    response = run(
        recommendations=[record],
        discovery_candidates=[record],
        discovery_candidate_ids=[1],
    )
    result = retention_metrics(
        [run(recommendations=[record], assessments=[record])], [response]
    )
    assert len(assisted_candidates(response)) == 1
    assert result["deterministic_assistance_needed_requests"] == 0
    assert result["profiles"][0]["raw_canonical_overlap"] == 1


def test_partial_model_selection_still_needs_retention_assistance():
    a, b = candidate(1), candidate(2)
    result = retention_metrics(
        [run(recommendations=[a, b], assessments=[a, b])],
        [
            run(
                recommendations=[a],
                discovery_candidates=[a, b],
                discovery_candidate_ids=[1, 2],
            )
        ],
    )
    assert result["deterministic_assistance_needed_requests"] == 1
    assert result["assistance_only_responses"] == 0
    assert result["profiles"][0]["assisted_unique_candidates"] == 2


@pytest.mark.parametrize("changed", ["hash", "date", "population"])
def test_comparison_rejects_changed_inputs_dates_or_populations(changed):
    before, after = experiment(), experiment()
    if changed == "hash":
        after["signature"]["inputs"]["demo.json"] = "changed"
    elif changed == "date":
        after["signature"]["as_of"] = "2026-11-13"
    else:
        after["agent"][0]["profile_id"] = "P2"
    with pytest.raises(ValueError):
        validate_comparable(before, after)


def test_fresh_before_signature_is_accepted_without_rewriting_original():
    prior = experiment()
    fresh = deepcopy(prior)
    signature = fresh.pop("signature")
    fresh.update(input_hashes=signature["inputs"], as_of=signature["as_of"])
    result = compare_experiments(prior, experiment(), [], [], fresh_before=fresh)
    assert "fresh_before_phase_6c" in result["comparisons"]
    assert "signature" not in fresh


def test_partial_after_case_population_cannot_inflate_coverage():
    prior = experiment()
    after = experiment()
    prior["agent_cases"] = [run(case_id="C1")]
    with pytest.raises(ValueError, match="case request populations"):
        compare_experiments(prior, after, [], [])


def test_handled_model_error_counts_as_model_failure_with_available_candidates():
    result = experiment()
    result["agent"][0].update(
        status="model_error",
        model_error="timeout",
        discovery_candidates=[candidate(1)],
        discovery_candidate_ids=[1],
    )
    summary = experiment_summary(result, [], [])
    assert summary["raw_model_operational"]["failures"] == 1
    assert summary["handled_model_errors"] == 1
    assert summary["unhandled_model_exceptions"] == 0
    assert summary["assisted_operational"]["recommendation_coverage"] == 1
    assert summary["model_error_types"]["timeout"] == 1


def test_negative_target_coverage_and_classification_are_attributed_separately():
    negative = candidate(3, "ineligible")
    case = {
        "id": "C1",
        "scholarship_name": negative["scholarship_name"],
        "expected_status": "ineligible",
        "label_status": "verified_gold",
    }
    request = run(case_id="C1", discovery_candidates=[negative])
    raw = case_assessment_metrics([case], [request], "assessments")
    canonical = case_assessment_metrics([case], [request], "discovery_candidates")
    assert raw["assessed_targets"] == 0
    assert raw["source_checked_negative_agreement"]["end_to_end_agreement"] == 0
    assert raw["source_checked_negative_agreement"]["agreement_among_assessed"] is None
    assert (
        canonical["source_checked_negative_agreement"]["agreement_among_assessed"] == 1
    )
    assert canonical["target_verdicts"]["ineligible"] == 1


def test_unknown_target_is_not_counted_as_positive_or_negative_gold():
    unknown = candidate(1)
    case = {
        "id": "C1",
        "scholarship_name": unknown["scholarship_name"],
        "expected_status": None,
        "label_status": "unresolved",
    }
    metrics = case_assessment_metrics(
        [case], [run(case_id="C1", assessments=[unknown])], "assessments"
    )
    assert metrics["unresolved_cases"] == 1
    assert metrics["source_checked_negative_agreement"]["cases"] == 0
    assert metrics["target_verdicts"]["eligible"] == 0


def test_duplicate_cases_and_profiles_cannot_inflate_sample_size():
    result = experiment()
    result["agent"].append(deepcopy(result["agent"][0]))
    with pytest.raises(ValueError, match="unique"):
        validate_comparable(result)
    with pytest.raises(ValueError, match="unique"):
        case_assessment_metrics(
            [], [run(case_id="C1"), run(case_id="C1")], "assessments"
        )


def test_empty_metrics_and_proposal_targets_do_not_create_perfect_scores():
    result = experiment()
    result.update(baseline=[], agent=[])
    summary = compare_experiments(result, result, [], [])
    assert (
        summary["comparisons"]["phase_6c"]["raw_model_operational"][
            "recommendation_coverage"
        ]
        is None
    )
    assert all(
        target["status"] == "NOT_EVALUABLE" and target["achieved"] is None
        for target in summary["proposal_targets"].values()
    )
    assert round_metrics([])["maximum_reported_prompt_tokens"] is None


def test_round_context_and_invalid_selection_metrics_use_actual_observations():
    metrics = round_metrics(
        [
            run(
                rounds=[
                    {
                        "estimated_input_tokens": 2500,
                        "prompt_tokens": 1200,
                        "seconds": 0.5,
                        "final_validation": "unassessed_ids",
                    }
                ],
                warnings=["Compact context budget reached"],
            )
        ]
    )
    assert metrics["model_rounds"] == 1
    assert metrics["maximum_estimated_input_tokens"] == 2500
    assert metrics["maximum_reported_prompt_tokens"] == 1200
    assert metrics["unassessed_selection_rounds"] == 1
    assert metrics["context_budget_stops"] == 1


def test_round_metrics_distinguish_scope_and_explanation_grounding_rejections():
    validations = [
        "outside_named_target",
        "outside_named_target",
        "invalid_explanation_reference",
        "invalid_schema",
        "unassessed_ids",
        "grounded",
    ]
    metrics = round_metrics(
        [
            run(
                rounds=[
                    {
                        "estimated_input_tokens": 100,
                        "seconds": 0.1,
                        "final_validation": validation,
                    }
                    for validation in validations
                ]
            )
        ]
    )
    assert metrics["outside_named_target_rounds"] == 2
    assert metrics["invalid_explanation_reference_rounds"] == 1
    assert metrics["invalid_schema_rounds"] == 1
    assert metrics["unassessed_selection_rounds"] == 1
    assert round_metrics([])["outside_named_target_rounds"] == 0
