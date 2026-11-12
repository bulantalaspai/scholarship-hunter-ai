"""Metric regressions use explicit synthetic annotations, never official facts."""

import pytest

from backend.evaluation.metrics import (
    citation_metrics,
    classification_metrics,
    extraction_metrics,
    precision_at_3,
)


def case(identifier, expected, label_status="verified_gold"):
    return {"id": identifier, "expected_status": expected, "label_status": label_status}


def example(identifier, fields, annotation_status="source_checked"):
    return {
        "id": identifier,
        "expected_fields": fields,
        "annotation_status": annotation_status,
    }


def test_classification_excludes_provisional_and_unresolved_labels():
    result = classification_metrics(
        [
            case("C1", "ineligible"),
            case("C2", "needs_verification", "provisional"),
            case("C3", None, "unresolved"),
        ],
        {"C1": "ineligible", "C2": "needs_verification", "C3": "eligible"},
    )
    assert result["accuracy"] == 1
    assert result["gold_cases"] == result["correct"] == 1
    assert result["excluded_cases"] == 2
    assert result["class_counts"]["eligible"] == 0
    assert result["target_status"] == "NOT_EVALUABLE"
    assert result["target_achieved"] is None


def test_missing_prediction_is_in_gold_denominator_and_confusion_matrix():
    result = classification_metrics(
        [case("C1", "eligible"), case("C2", "ineligible")],
        {"C1": "eligible"},
    )
    assert result["accuracy"] == result["prediction_coverage"] == 0.5
    assert result["confusion_matrix"]["ineligible"]["missing_or_invalid"] == 1


def test_three_class_accuracy_scores_needs_verification_and_failures():
    result = classification_metrics(
        [
            case("C1", "eligible"),
            case("C2", "ineligible"),
            case("C3", "needs_verification"),
        ],
        {"C1": "needs_verification", "C2": "ineligible", "C3": "needs_verification"},
    )
    assert result["accuracy"] == pytest.approx(2 / 3)
    assert result["confusion_matrix"]["eligible"]["needs_verification"] == 1
    assert result["target_status"] == "EVALUABLE"
    assert result["target_achieved"] is False


def test_classification_without_gold_has_no_accuracy_value():
    result = classification_metrics([case("C1", None, "unresolved")], {})
    assert result["accuracy"] is result["prediction_coverage"] is None
    assert result["status"] == "NOT_EVALUABLE"


def test_duplicate_case_ids_cannot_inflate_sample_size():
    with pytest.raises(ValueError, match="unique"):
        classification_metrics([case("C1", "eligible"), case("C1", "eligible")], {})


def test_extraction_wrong_values_count_false_positive_and_false_negative():
    result = extraction_metrics(
        [example("E1", {"minimum_ielts_overall": 6.5, "tuition_covered": True})],
        {
            "E1": {
                "minimum_ielts_overall": 7.0,
                "tuition_covered": True,
                "minimum_gpa": 3.0,
            }
        },
    )
    assert (result["tp"], result["fp"], result["fn"]) == (1, 2, 1)
    assert result["precision"] == pytest.approx(1 / 3)
    assert result["recall"] == 0.5
    assert result["f1"] == 0.4


def test_null_slots_are_not_positive_claims_but_false_is():
    result = extraction_metrics(
        [example("E1", {"minimum_gpa": None, "tuition_covered": False})],
        {"E1": {"minimum_gpa": None, "tuition_covered": False}},
    )
    assert result["gold_assertions"] == result["predicted_assertions"] == 1
    assert result["tp"] == 1 and result["f1"] == 1


def test_unknown_strings_are_unsupported_non_null_assertions():
    result = extraction_metrics(
        [example("E1", {"minimum_ielts_overall": 6.5, "minimum_gpa": None})],
        {"E1": {"minimum_ielts_overall": "unknown", "minimum_gpa": "unknown"}},
    )
    assert (result["tp"], result["fp"], result["fn"]) == (0, 2, 1)
    assert result["precision"] == result["recall"] == result["f1"] == 0


def test_boolean_and_number_are_distinct_extraction_values():
    result = extraction_metrics(
        [example("E1", {"tuition_covered": True, "stipend_amount": 1400})],
        {"E1": {"tuition_covered": 1, "stipend_amount": 1400.0}},
    )
    assert (result["tp"], result["fp"], result["fn"]) == (1, 1, 1)


def test_malformed_extraction_counts_all_expected_assertions_as_missed():
    result = extraction_metrics(
        [example("E1", {"minimum_ielts_overall": 6.5})], {"E1": "not JSON"}
    )
    assert result["precision"] is None
    assert result["recall"] == result["f1"] == 0
    assert result["predicted_examples"] == 0 and result["fn"] == 1


def test_unchecked_annotations_do_not_produce_a_perfect_extraction_score():
    result = extraction_metrics(
        [example("E1", {"minimum_ielts_overall": 6.5}, "provisional")],
        {"E1": {"minimum_ielts_overall": 6.5}},
    )
    assert result["examples"] == 0 and result["excluded_examples"] == 1
    assert result["precision"] is result["recall"] is result["f1"] is None
    assert result["target_status"] == "NOT_EVALUABLE"


def gold_relevance(name, relevant=True, eligibility_status="eligible"):
    return {
        "profile_id": "P01",
        "scholarship_name": name,
        "label_status": "verified_gold",
        "relevant": relevant,
        "eligibility_status": eligibility_status,
    }


def recommendation(name, status="eligible"):
    return {"scholarship_name": name, "status": status}


def test_precision_at_three_is_unevaluable_without_eligible_gold_positives():
    result = precision_at_3(
        [{"profile_id": "P01", "recommendations": [recommendation("Fictional A")]}],
        [
            gold_relevance(
                "Fictional A", relevant=False, eligibility_status="ineligible"
            )
        ],
    )
    assert result["precision_at_3"] is None
    assert result["eligible_profiles"] == result["evaluable_profiles"] == 0
    assert result["status"] == "NOT_EVALUABLE"


def test_precision_denominator_stays_three_for_a_short_list():
    names = ["Fictional A", "Fictional B", "Fictional C"]
    result = precision_at_3(
        [{"profile_id": "P01", "recommendations": [recommendation(names[0])]}],
        [gold_relevance(name) for name in names],
    )
    assert result["precision_at_3"] == pytest.approx(1 / 3)
    assert result["target_achieved"] is False


def test_unknown_classification_never_receives_positive_relevance_credit():
    names = ["Fictional A", "Fictional B", "Fictional C"]
    result = precision_at_3(
        [
            {
                "profile_id": "P01",
                "recommendations": [
                    recommendation(name, "needs_verification") for name in names
                ],
            }
        ],
        [gold_relevance(name) for name in names],
    )
    assert result["precision_at_3"] == 0
    assert result["profiles"][0]["relevant_hits"] == 0


def test_unjudged_returned_candidate_prevents_a_precision_at_three_claim():
    result = precision_at_3(
        [{"profile_id": "P01", "recommendations": [recommendation("Fictional D")]}],
        [gold_relevance(f"Fictional {letter}") for letter in "ABC"],
    )
    assert result["precision_at_3"] is None
    assert result["target_status"] == "NOT_EVALUABLE"


def test_empty_agent_selection_counts_zero_when_profile_has_three_gold_matches():
    result = precision_at_3(
        [{"profile_id": "P01", "recommendations": []}],
        [gold_relevance(f"Fictional {letter}") for letter in "ABC"],
    )
    assert result["precision_at_3"] == 0


def test_repeated_recommendation_does_not_count_as_three_hits():
    result = precision_at_3(
        [
            {
                "profile_id": "P01",
                "recommendations": [recommendation("Fictional A")] * 3,
            }
        ],
        [gold_relevance(f"Fictional {letter}") for letter in "ABC"],
    )
    assert result["precision_at_3"] == pytest.approx(1 / 3)


def citation_example(support="supported", annotation_status="source_checked"):
    return {
        "scholarship_name": "Fictional Award",
        "source_url": "https://example.org/fictional",
        "annotation_status": annotation_status,
        "claims": [
            {"field": "funding_type", "value": "fully_funded", "support": support}
        ],
    }


def citation_fact(source_url="https://example.org/fictional"):
    return {
        "scholarship_name": "Fictional Award",
        "source_url": source_url,
        "field": "funding_type",
        "value": "fully_funded",
    }


def test_citation_link_presence_does_not_imply_claim_support():
    facts = [citation_fact(), citation_fact("https://example.org/other")]
    result = citation_metrics(facts, [citation_example()])
    assert result["citation_coverage"] == 1
    assert result["audited_claims"] == result["supported_claims"] == 1
    assert result["unresolved_claims"] == 1
    assert result["target_status"] == "NOT_EVALUABLE"
    assert result["target_achieved"] is None


def test_reviewed_unsupported_citation_counts_against_support_rate():
    result = citation_metrics([citation_fact()], [citation_example("unsupported")])
    assert result["citation_coverage"] == 1
    assert result["citation_support_rate"] == 0
    assert result["unsupported_claims"] == 1
    assert result["target_status"] == "EVALUABLE"
    assert result["target_achieved"] is False


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "http://example.org",
        "javascript:alert(1)",
        "https://u:p@example.org",
        "https://example.org:bad",
    ],
)
def test_malformed_or_non_https_references_do_not_count_as_citations(url):
    result = citation_metrics([citation_fact(url)], [])
    assert result["linked_claims"] == 0
    assert result["citation_coverage"] == 0
    assert result["unresolved_claims"] == 1


def test_empty_citation_sample_has_no_perfect_score():
    result = citation_metrics([], [])
    assert result["citation_coverage"] is result["citation_support_rate"] is None
    assert result["target_status"] == "NOT_EVALUABLE"


def test_conflicting_claim_support_annotations_are_rejected():
    with pytest.raises(ValueError, match="Conflicting"):
        citation_metrics(
            [citation_fact()],
            [citation_example("supported"), citation_example("unsupported")],
        )
