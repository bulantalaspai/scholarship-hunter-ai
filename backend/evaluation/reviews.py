"""Prepare assigned review sheets and validate actual human review attestations."""

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from backend.evaluation.extract import EXTRACTION_KEYS
from backend.evaluation.metrics import _value_key
from backend.evaluation.run import (
    CATALOGUE,
    DATA,
    INPUT_FILES,
    ROOT,
    file_hashes,
    read_json,
    write_checkpoint,
)

PACKAGE = ROOT / "evaluation" / "human_review"
EVIDENCE = PACKAGE / "evidence.json"
REVIEWERS = ("Talaspay Bulan", "Sayat Nuradil", "Tursbekov Darkhan")
SHEET_NAMES = ("talaspay_bulan.csv", "sayat_nuradil.csv", "tursbekov_darkhan.csv")
DECISION_FIELDS = (
    "reviewer_decision",
    "reviewed_value",
    "rationale",
    "review_date",
    "review_evidence_url",
    "review_evidence_excerpt_or_section",
    "evidence_access_date",
)
COLUMNS = (
    "item_id",
    "category",
    "case_id",
    "profile_id",
    "student_profile",
    "scholarship",
    "proposed_label",
    "official_evidence",
    "evidence_reference",
    "source_verification_date",
    "reviewer",
    "manifest_sha256",
    *DECISION_FIELDS,
)
VERDICTS = {"eligible", "ineligible", "needs_verification"}
NUMERIC_FIELDS = {
    "minimum_ielts_overall",
    "minimum_ielts_component",
    "minimum_gpa",
    "gpa_scale",
    "stipend_amount",
}


class ReviewValidationError(ValueError):
    """Invalid review data must never supply partially accepted metric labels."""


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def manifest_hash(manifest: dict) -> str:
    return hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()


def _evidence_ids(rationale: str, examples: list[dict], scholarship: str) -> list[str]:
    identifiers = re.findall(r"E-[A-Z-]+", rationale)
    mapped = {
        "E-DAAD-TUITION": "S08",
        "E-DAAD-UNRESOLVED": "S08",
    }
    identifiers = [mapped.get(identifier, identifier) for identifier in identifiers]
    if not identifiers:
        identifiers = [
            item["id"] for item in examples if item["scholarship_name"] == scholarship
        ]
    return list(dict.fromkeys(identifiers))


def build_manifest() -> dict:
    """Build reproducible provisional items without running any matching service."""
    profiles = read_json(DATA / "profiles.json")["profiles"]
    by_profile = {item["id"]: item["profile"] for item in profiles}
    cases_document = read_json(DATA / "eligibility_cases.json")
    sources = read_json(DATA / "source_annotations.json")["examples"]
    catalogue = read_json(CATALOGUE)["scholarships"]
    by_name = {item["scholarship_name"]: item for item in catalogue}
    source_evidence = read_json(ROOT / "backend/data/catalogue_evidence.json")[
        "records"
    ]
    additional_sources = {
        item["scholarship_name"]: [source["url"] for source in item["sources"]]
        for item in source_evidence
    }
    registry = read_json(EVIDENCE)["evidence"]
    items = []

    def add(category: str, identifier: str, scholarship: str, value, **metadata):
        record = by_name[scholarship]
        profile_id = metadata.get("profile_id")
        references = metadata.pop("evidence_ids", [])
        if any(reference not in registry for reference in references):
            raise ReviewValidationError("An annotation evidence reference is missing")
        urls = list(
            dict.fromkeys(metadata.pop("source_urls", [record["official_source_url"]]))
        )
        official_urls = list(
            dict.fromkeys(
                urls + [record["official_source_url"]] + additional_sources[scholarship]
            )
        )
        index = len(items)
        items.append(
            {
                "id": identifier,
                "category": category,
                "case_id": None,
                "profile_id": profile_id,
                "student_profile": by_profile.get(profile_id),
                "scholarship_name": scholarship,
                "example_id": None,
                "field": None,
                "claim_value": None,
                "proposed_value": value,
                "annotation_origin": "ai_generated_provisional",
                "evidence_references": references,
                "evidence_verified_at": sorted(
                    {registry[reference]["verified_at"] for reference in references}
                ),
                "catalogue_verified_at": record["last_verified_at"],
                "source_url": urls[0],
                "source_urls": urls,
                "permitted_evidence_hosts": sorted(
                    {urlsplit(url).hostname for url in official_urls}
                ),
                "assigned_reviewers": [
                    REVIEWERS[index % len(REVIEWERS)],
                    REVIEWERS[(index + 1) % len(REVIEWERS)],
                ],
                **metadata,
            }
        )

    for index, case in enumerate(cases_document["cases"]):
        add(
            "eligibility",
            f"E-{case['id']}",
            case["scholarship_name"],
            case["expected_status"],
            case_id=case["id"],
            profile_id=case["profile_id"],
            legacy_label_status=case["label_status"],
            rationale=case["rationale"],
            evidence_ids=_evidence_ids(
                case["rationale"], sources, case["scholarship_name"]
            ),
            source_urls=case["source_urls"],
            source_references=[
                f"evaluation/data/eligibility_cases.json#/cases/{index}"
            ],
        )
    for index, example in enumerate(sources):
        for field in EXTRACTION_KEYS:
            add(
                "extraction",
                f"X-{example['id']}-{field}",
                example["scholarship_name"],
                example["expected_fields"].get(field),
                case_id=example["id"],
                example_id=example["id"],
                field=field,
                legacy_label_status=example["annotation_status"],
                source_urls=[example["source_url"]],
                evidence_ids=[example["id"]],
                source_references=[
                    f"evaluation/data/source_annotations.json#/examples/{index}"
                ],
            )
    judgments = read_json(DATA / "relevance_judgments.json")["judgments"]
    for index, judgment in enumerate(judgments):
        add(
            "relevance",
            f"R-{index + 1:03}",
            judgment["scholarship_name"],
            judgment["relevant"],
            case_id=f"R-{index + 1:03}",
            profile_id=judgment["profile_id"],
            legacy_label_status=judgment["label_status"],
            rationale=judgment["rationale"],
            evidence_ids=_evidence_ids(
                judgment["rationale"], sources, judgment["scholarship_name"]
            ),
            source_urls=judgment["source_urls"],
            source_references=[
                f"evaluation/data/relevance_judgments.json#/judgments/{index}"
            ],
        )
    for index, example in enumerate(sources):
        for claim_index, claim in enumerate(example["claims"]):
            add(
                "citation",
                f"C-{example['id']}-{claim_index + 1}",
                example["scholarship_name"],
                claim["support"],
                case_id=example["id"],
                example_id=example["id"],
                field=claim["field"],
                claim_value=claim["value"],
                rationale=claim["rationale"],
                legacy_label_status=example["annotation_status"],
                evidence_ids=[example["id"]],
                source_urls=[example["source_url"]],
                source_references=[
                    "evaluation/data/source_annotations.json"
                    f"#/examples/{index}/claims/{claim_index}"
                ],
            )
    return {
        "schema_version": 1,
        "as_of": cases_document["as_of"],
        "synthetic_profiles": True,
        "annotation_origin": "AI-generated proposals awaiting actual human review",
        "input_hashes": file_hashes(INPUT_FILES),
        "review_source_hashes": file_hashes(
            [
                DATA / "README.md",
                ROOT / "backend/data/catalogue_evidence.json",
                EVIDENCE,
            ]
        ),
        "reviewers": list(REVIEWERS),
        "protocol": "Two assigned independent reviewers per item; agreement required",
        "items": items,
    }


def sheet_row(item: dict, reviewer: str, checksum: str) -> dict[str, str]:
    return {
        "item_id": item["id"],
        "category": item["category"],
        "case_id": item["case_id"] or "",
        "profile_id": item["profile_id"] or "",
        "student_profile": canonical_json(item["student_profile"])
        if item["student_profile"]
        else "",
        "scholarship": item["scholarship_name"],
        "proposed_label": canonical_json(item["proposed_value"]),
        "official_evidence": " | ".join(item["source_urls"]),
        "evidence_reference": " | ".join(
            f"evidence.json#/evidence/{reference}"
            for reference in item["evidence_references"]
        ),
        "source_verification_date": " | ".join(item["evidence_verified_at"]),
        "reviewer": reviewer,
        "manifest_sha256": checksum,
        **dict.fromkeys(DECISION_FIELDS, ""),
    }


def generate_package(output_dir: Path) -> dict:
    """Create blank sheets, refusing to replace completed human decisions."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in SHEET_NAMES:
        path = output_dir / name
        if path.exists():
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != list(COLUMNS):
                    raise ReviewValidationError("Existing review columns are invalid")
                for row in reader:
                    if set(row) != set(COLUMNS) or any(
                        value is None for value in row.values()
                    ):
                        raise ReviewValidationError("Existing review cells are invalid")
                    if any(row[field].strip() for field in DECISION_FIELDS):
                        raise ReviewValidationError(
                            "Generation would overwrite human input"
                        )
    manifest = build_manifest()
    checksum = manifest_hash(manifest)
    write_checkpoint(output_dir / "manifest.json", manifest)
    if output_dir.resolve() != PACKAGE.resolve():
        write_checkpoint(output_dir / "evidence.json", read_json(EVIDENCE))
    for reviewer, name in zip(REVIEWERS, SHEET_NAMES, strict=True):
        with (output_dir / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(
                sheet_row(item, reviewer, checksum)
                for item in manifest["items"]
                if reviewer in item["assigned_reviewers"]
            )
    return manifest


def _iso_date(value: str, field: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ReviewValidationError(f"Invalid ISO {field}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ReviewValidationError(f"Invalid ISO {field}") from None


def _reviewed_value(item: dict, value: object) -> None:
    category = item["category"]
    if value is None:
        return
    if category == "eligibility" and value in VERDICTS:
        return
    if category == "relevance" and type(value) is bool:
        return
    if category == "citation" and value in {"supported", "unsupported", "unresolved"}:
        return
    if category == "extraction":
        field = item["field"]
        if field in NUMERIC_FIELDS:
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                if field.startswith("minimum_ielts") and value > 9:
                    raise ReviewValidationError("IELTS label exceeds its scale")
                if field == "gpa_scale" and value == 0:
                    raise ReviewValidationError("GPA scale must be positive")
                return
        elif field in {"tuition_covered", "ielts_only_route"}:
            if type(value) is bool:
                return
        elif field == "deadline" and isinstance(value, str):
            _iso_date(value, "deadline label")
            return
        elif field == "stipend_currency" and isinstance(value, str):
            if re.fullmatch(r"[A-Z]{3}", value):
                return
        elif field == "stipend_period" and value in {"month", "year"}:
            return
    raise ReviewValidationError("Reviewed value has the wrong category or field type")


def _page_identity(url) -> tuple:
    return url.scheme, url.hostname, url.port or 443, url.path or "/", url.query


def _completed_review(item: dict, row: dict, today: date) -> dict | None:
    populated = [row[field].strip() for field in DECISION_FIELDS]
    if not any(populated):
        return None
    if not all(populated):
        raise ReviewValidationError("Completed reviews require every decision field")
    decision = row["reviewer_decision"].strip()
    if decision not in {"accept", "revise", "unresolved"}:
        raise ReviewValidationError("Unknown reviewer decision")
    try:
        value = json.loads(row["reviewed_value"])
    except ValueError:
        raise ReviewValidationError("Reviewed value must be JSON") from None
    if isinstance(value, (dict, list)):
        raise ReviewValidationError("Reviewed value must be a typed scalar")
    _reviewed_value(item, value)
    if decision == "accept" and _value_key(value) != _value_key(item["proposed_value"]):
        raise ReviewValidationError("Accept must explicitly retain the proposed value")
    if decision == "revise" and _value_key(value) == _value_key(item["proposed_value"]):
        raise ReviewValidationError("Revise must supply a changed value")
    if decision == "unresolved" and value is not None:
        raise ReviewValidationError("An unresolved decision must retain a null value")
    reviewed_at = _iso_date(row["review_date"].strip(), "review date")
    accessed_at = _iso_date(row["evidence_access_date"].strip(), "evidence access date")
    if accessed_at > reviewed_at or reviewed_at > today:
        raise ReviewValidationError("Review dates must follow access and precede today")
    try:
        url = urlsplit(row["review_evidence_url"].strip())
        valid_url = (
            url.scheme == "https"
            and url.hostname in item["permitted_evidence_hosts"]
            and url.username is None
            and url.password is None
            and url.port in (None, 443)
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        raise ReviewValidationError(
            "Review evidence must use a programme official host"
        )
    if item["category"] == "citation" and _page_identity(url) != _page_identity(
        urlsplit(item["source_url"])
    ):
        raise ReviewValidationError(
            "Citation support requires the exact cited page, with anchors allowed"
        )
    if not 1 <= len(row["rationale"].strip()) <= 4000:
        raise ReviewValidationError("A bounded rationale is required")
    if not 1 <= len(row["review_evidence_excerpt_or_section"].strip()) <= 4000:
        raise ReviewValidationError("A bounded evidence passage or section is required")
    unresolved = decision == "unresolved" or (
        value is None and item["category"] != "extraction"
    )
    return {
        "reviewer": row["reviewer"],
        "decision": decision,
        "reviewed_value": value,
        "unresolved": unresolved or value == "unresolved",
        "rationale": row["rationale"].strip(),
        "review_date": reviewed_at.isoformat(),
        "evidence_url": row["review_evidence_url"].strip(),
        "evidence_excerpt_or_section": row[
            "review_evidence_excerpt_or_section"
        ].strip(),
        "evidence_access_date": accessed_at.isoformat(),
    }


def validate_reviews(package_dir: Path, *, today: date | None = None) -> dict:
    """Validate provenance and agreement without simulating human decisions."""
    today = today or date.today()
    manifest = read_json(package_dir / "manifest.json")
    expected_manifest = build_manifest()
    if manifest != expected_manifest:
        raise ReviewValidationError("Manifest or source provenance differs from inputs")
    if read_json(package_dir / "evidence.json") != read_json(EVIDENCE):
        raise ReviewValidationError("Review evidence registry differs from provenance")
    checksum = manifest_hash(manifest)
    by_id = {item["id"]: item for item in manifest["items"]}
    reviews = {identifier: [] for identifier in by_id}
    for reviewer, filename in zip(REVIEWERS, SHEET_NAMES, strict=True):
        seen = set()
        with (package_dir / filename).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(COLUMNS):
                raise ReviewValidationError(f"Invalid review columns in {filename}")
            for row in reader:
                identifier = row.get("item_id")
                if identifier in seen or identifier not in by_id:
                    raise ReviewValidationError(
                        f"Duplicate or unknown item in {filename}"
                    )
                seen.add(identifier)
                item = by_id[identifier]
                if reviewer not in item["assigned_reviewers"]:
                    raise ReviewValidationError(f"Unassigned item in {filename}")
                expected_row = sheet_row(item, reviewer, checksum)
                if set(row) != set(COLUMNS) or any(
                    row[key] != expected_row[key]
                    for key in COLUMNS
                    if key not in DECISION_FIELDS
                ):
                    raise ReviewValidationError(
                        f"Altered immutable fields in {filename}"
                    )
                if any(value is None for value in row.values()):
                    raise ReviewValidationError(f"Missing CSV cells in {filename}")
                review = _completed_review(item, row, today)
                if review is not None:
                    reviews[identifier].append(review)
        expected_ids = {
            item["id"]
            for item in manifest["items"]
            if reviewer in item["assigned_reviewers"]
        }
        if seen != expected_ids:
            raise ReviewValidationError(f"Missing assigned items in {filename}")
    results = []
    for item in manifest["items"]:
        completed = reviews[item["id"]]
        values = {_value_key(review["reviewed_value"]) for review in completed}
        if len(values) > 1:
            status = "disagreement"
        elif any(review["unresolved"] for review in completed):
            status = "unresolved"
        elif len(completed) == 2:
            status = "reviewed"
        else:
            status = "partial" if completed else "pending"
        results.append(
            item
            | {
                "status": status,
                "reviewed_value": completed[0]["reviewed_value"]
                if status == "reviewed"
                else None,
                "reviews": completed,
                "reviewers": [review["reviewer"] for review in completed],
            }
        )
    counts = Counter(item["status"] for item in results)
    reviewed = counts["reviewed"]
    return {
        "schema_version": 1,
        "as_of": manifest["as_of"],
        "manifest_sha256": checksum,
        "input_hashes": manifest["input_hashes"],
        "review_source_hashes": manifest["review_source_hashes"],
        "summary": {
            "items": len(results),
            "completed_reviews": sum(len(item["reviews"]) for item in results),
            "human_reviewed_items": reviewed,
            **{
                status: counts[status]
                for status in (
                    "pending",
                    "partial",
                    "disagreement",
                    "unresolved",
                    "reviewed",
                )
            },
            "categories": {
                category: {
                    "items": sum(item["category"] == category for item in results),
                    "reviewed": sum(
                        item["category"] == category and item["status"] == "reviewed"
                        for item in results
                    ),
                }
                for category in ("eligibility", "extraction", "relevance", "citation")
            },
            "academic_metrics_status": "NOT_EVALUABLE"
            if reviewed == 0
            else "PARTIALLY_REVIEWED",
        },
        "items": results,
        "limitations": [
            "The script validates attestations, provenance and agreement. "
            "Human identity, "
            "independence and actual source support require external verification.",
            "Pending, partial, disputed and unresolved items supply no final labels.",
            "Reviewed extraction null denotes confirmed absence "
            "within a bounded excerpt. "
            "Other null judgments remain unresolved.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--output", type=Path, default=PACKAGE)
    validate = commands.add_parser("validate")
    validate.add_argument("--package", type=Path, default=PACKAGE)
    validate.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "generate":
            manifest = generate_package(args.output)
            summary = {
                "items": len(manifest["items"]),
                "review_assignments": len(manifest["items"]) * 2,
                "human_decisions_written": 0,
            }
        else:
            result = validate_reviews(args.package)
            if args.output:
                write_checkpoint(args.output, result)
            summary = result["summary"]
    except (ReviewValidationError, OSError, ValueError) as error:
        parser.exit(2, f"Unable to validate review data ({error})\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
