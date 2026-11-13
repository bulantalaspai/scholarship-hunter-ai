"""Evaluation counts with explicit unknowns and denominators.

Annotations are supplied independently of predictions. Missing gold classes and
unreviewed source support remain visible in the returned evaluation status.
"""

import json
from collections import Counter
from urllib.parse import urlsplit

STATUSES = ("eligible", "ineligible", "needs_verification")
NOT_EVALUABLE = "NOT_EVALUABLE"


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _unique_ids(items: list[dict]) -> None:
    identifiers = [item["id"] for item in items]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Evaluation IDs must be unique")


def classification_metrics(cases: list[dict], predictions: dict) -> dict:
    """Score verified gold only, counting absent predictions as incorrect."""
    _unique_ids(cases)
    gold = [
        case
        for case in cases
        if case["label_status"] == "verified_gold"
        and case.get("expected_status") in STATUSES
    ]
    confusion = {
        expected: {**dict.fromkeys(STATUSES, 0), "missing_or_invalid": 0}
        for expected in STATUSES
    }
    correct = predicted = 0
    for case in gold:
        actual = predictions.get(case["id"])
        if actual not in STATUSES:
            actual = "missing_or_invalid"
        else:
            predicted += 1
        expected = case["expected_status"]
        confusion[expected][actual] += 1
        correct += actual == expected
    class_counts = Counter(case["expected_status"] for case in gold)
    complete_classes = all(class_counts[status] for status in STATUSES)
    return {
        "cases": len(cases),
        "gold_cases": len(gold),
        "excluded_cases": len(cases) - len(gold),
        "predicted_gold_cases": predicted,
        "correct": correct,
        "accuracy": _ratio(correct, len(gold)),
        "prediction_coverage": _ratio(predicted, len(gold)),
        "class_counts": {status: class_counts[status] for status in STATUSES},
        "confusion_matrix": confusion,
        "status": "MEASURED" if gold else NOT_EVALUABLE,
        "target_status": "EVALUABLE" if complete_classes else NOT_EVALUABLE,
        "target_achieved": correct / len(gold) >= 0.90 if complete_classes else None,
        "reason": (
            "Gold-subset accuracy is reported with its class coverage."
            if complete_classes
            else "A three-class accuracy claim requires verified gold examples "
            "for eligible, ineligible and needs_verification."
        ),
    }


def _value_key(value: object) -> tuple:
    # JSON numbers compare by value, while boolean assertions remain distinct.
    if isinstance(value, bool):
        return "boolean", value
    if isinstance(value, int | float):
        return "number", value
    if isinstance(value, str):
        return "string", value
    return "other", json.dumps(value, sort_keys=True, ensure_ascii=False)


def _assertions(fields: dict) -> set[tuple]:
    return {
        (name, _value_key(value)) for name, value in fields.items() if value is not None
    }


def extraction_metrics(examples: list[dict], predictions: dict) -> dict:
    """Micro-average exact (slot, value) pairs in source-checked excerpts.

    A wrong value produces both a false positive and a false negative. All
    unsupported non-null slots count as false positives, including extra keys.
    """
    _unique_ids(examples)
    checked = [
        example
        for example in examples
        if example.get("annotation_status") == "source_checked"
    ]
    tp = fp = fn = predicted = 0
    for example in checked:
        expected = _assertions(example["expected_fields"])
        result = predictions.get(example["id"])
        predicted += isinstance(result, dict)
        observed = _assertions(result) if isinstance(result, dict) else set()
        tp += len(expected & observed)
        fp += len(observed - expected)
        fn += len(expected - observed)
    evaluable = bool(tp + fn)
    f1 = _ratio(2 * tp, 2 * tp + fp + fn)
    return {
        "examples": len(checked),
        "excluded_examples": len(examples) - len(checked),
        "predicted_examples": predicted,
        "gold_assertions": tp + fn,
        "predicted_assertions": tp + fp,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        "f1": f1 if evaluable else None,
        "status": "MEASURED" if evaluable else NOT_EVALUABLE,
        "target_status": "EVALUABLE" if evaluable else NOT_EVALUABLE,
        "target_achieved": f1 >= 0.85 if evaluable else None,
        "reason": (
            "Exact source-excerpt slot annotations; independent human review "
            "and broader source sampling remain necessary."
        ),
    }


def precision_at_3(runs: list[dict], judgments: list[dict]) -> dict:
    """Require three verified eligible relevant opportunities per profile."""
    indexed = {}
    positives = Counter()
    for judgment in judgments:
        key = judgment["profile_id"], judgment["scholarship_name"]
        if key in indexed:
            raise ValueError("Relevance judgments must be unique per programme/profile")
        indexed[key] = judgment
        if (
            judgment.get("label_status") == "verified_gold"
            and judgment.get("relevant") is True
            and judgment.get("eligibility_status") == "eligible"
        ):
            positives[judgment["profile_id"]] += 1
    profiles = []
    identifiers = set()
    for run in runs:
        identifier = run["profile_id"]
        if identifier in identifiers:
            raise ValueError("Each profile must have one recommendation run")
        identifiers.add(identifier)
        recommendations = run["recommendations"][:3]
        known = positives[identifier] >= 3
        hits = 0
        seen = set()
        for item in recommendations:
            name = item["scholarship_name"]
            judgment = indexed.get((identifier, name), {})
            judged = judgment.get("label_status") == "verified_gold" and isinstance(
                judgment.get("relevant"), bool
            )
            known = known and judged
            hits += (
                name not in seen
                and judged
                and judgment["relevant"] is True
                and judgment.get("eligibility_status") == "eligible"
                and item.get("status") == "eligible"
            )
            seen.add(name)
        profiles.append(
            {
                "profile_id": identifier,
                "verified_eligible_relevant_opportunities": positives[identifier],
                "returned_slots": len(recommendations),
                "relevant_hits": hits,
                "precision_at_3": hits / 3 if known else None,
                "status": "MEASURED" if known else NOT_EVALUABLE,
            }
        )
    measured = [
        item["precision_at_3"] for item in profiles if item["status"] == "MEASURED"
    ]
    value = sum(measured) / len(measured) if measured else None
    complete = bool(profiles) and len(measured) == len(profiles)
    return {
        "profiles": profiles,
        "eligible_profiles": sum(positives[item] >= 3 for item in identifiers),
        "evaluable_profiles": len(measured),
        "precision_at_3": value,
        "status": "MEASURED" if measured else NOT_EVALUABLE,
        "target_status": "EVALUABLE" if complete else NOT_EVALUABLE,
        "target_achieved": value >= 0.80 if complete else None,
        "reason": (
            "Each scored profile needs three verified eligible relevant opportunities "
            "and verified relevance judgments for every returned top-three record. "
            "Missing slots count against the fixed denominator of three."
        ),
    }


def _https_reference(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # Access validates port syntax without a network request.
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def citation_metrics(facts: list[dict], annotations: list[dict]) -> dict:
    """Measure reference presence and separately audited claim/source support."""
    audited = {}
    for example in annotations:
        if example.get("annotation_status") != "source_checked":
            continue
        for claim in example.get("claims", []):
            key = (
                example["scholarship_name"],
                claim["field"],
                _value_key(claim["value"]),
                example["source_url"],
            )
            if key in audited and audited[key] != claim["support"]:
                raise ValueError("Conflicting citation support annotations")
            audited[key] = claim["support"]
    counts = Counter()
    for fact in facts:
        counts["linked"] += _https_reference(fact.get("source_url"))
        key = (
            fact["scholarship_name"],
            fact["field"],
            _value_key(fact["value"]),
            fact.get("source_url"),
        )
        counts[audited.get(key, "unresolved")] += 1
    reviewed = counts["supported"] + counts["unsupported"]
    complete = bool(facts) and reviewed == len(facts)
    return {
        "claims": len(facts),
        "linked_claims": counts["linked"],
        "audited_claims": reviewed,
        "supported_claims": counts["supported"],
        "unsupported_claims": counts["unsupported"],
        "unresolved_claims": counts["unresolved"],
        "citation_coverage": _ratio(counts["linked"], len(facts)),
        "citation_support_rate": _ratio(counts["supported"], reviewed),
        "audit_coverage": _ratio(reviewed, len(facts)),
        "status": "MEASURED" if facts else NOT_EVALUABLE,
        "target_status": "EVALUABLE" if complete else NOT_EVALUABLE,
        "target_achieved": (
            counts["linked"] == counts["supported"] == len(facts) if complete else None
        ),
        "reason": (
            "HTTPS reference presence is counted separately from source support. "
            "Unaudited claim/source pairs require further verification."
        ),
    }
