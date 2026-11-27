"""Human field review and transactional publication gates for the local dashboard."""

import json
import re
import sqlite3
from collections.abc import Collection, Sequence
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter

from backend.app.official_pages import PublicPageError
from backend.app.programme_resolution import normalize_name
from backend.app.schemas import CatalogueRecord, FundingType
from backend.collection import review
from backend.collection.extraction import DraftFields, ExtractionDraft
from backend.collection.field_evidence import explicit_deadline, supports
from backend.collection.funding_evidence import funding_conflicts
from backend.collection.sources import get_source

Decision = Literal["accepted", "rejected", "unresolved"]
ReviewValue = str | list[str] | int | float
REQUIRED_FIELDS = (
    "scholarship_name",
    "university_or_provider",
    "destination_country",
    "degree_level",
)
CATALOGUE_FIELDS = frozenset(CatalogueRecord.model_fields) - {
    "official_source_url",
    "last_verified_at",
    "eligibility_rules",
}
REVIEW_FIELDS = CATALOGUE_FIELDS | DraftFields.model_fields.keys()
_CAST = {
    field: TypeAdapter(CatalogueRecord.model_fields[field].rebuild_annotation())
    for field in CATALOGUE_FIELDS
}
_FUNDING_FIELDS = {
    "funding_amount",
    "funding_type",
    "living_stipend",
    "tuition_coverage",
}
_ASSESSMENT_FIELD = {
    "minimum_gpa": "gpa_requirement",
    "gpa_scale": "gpa_requirement",
    "minimum_ielts": "language_requirement",
    "living_stipend": "funding_amount",
}
_DEGREES = {
    "master": r"\b(?:master(?:[’']s|s)?|MSc|MPhil|MA|MBA)\b",
    "bachelor": r"\bbachelor(?:[’']s|s)?\b",
    "doctorate": r"\b(?:PhD|DPhil|doctorate|doctoral)\b",
}
_LITERAL_FIELDS = {
    "additional_requirements",
    "living_stipend",
    "notes",
    "tuition_coverage",
}
_CONDITIONAL = re.compile(
    r"\b(?:alternatively|could|either|except|if|may|not|only|unless|waived)\b", re.I
)


def _ensure_tables(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS field_decisions (
        id INTEGER PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES drafts(id),
        field TEXT NOT NULL, decision TEXT NOT NULL,
        value TEXT, evidence TEXT NOT NULL,
        reviewer TEXT NOT NULL, rationale TEXT NOT NULL, decided_at TEXT NOT NULL,
        CHECK (decision IN ('accepted','rejected','unresolved'))
    )""")
    db.execute(
        "CREATE INDEX IF NOT EXISTS field_decisions_by_draft "
        "ON field_decisions(draft_id, id)"
    )
    db.execute("""CREATE TABLE IF NOT EXISTS dashboard_approvals (
        draft_id TEXT PRIMARY KEY REFERENCES drafts(id),
        decided_at TEXT NOT NULL
    )""")


def _table_exists(db: sqlite3.Connection, name: str) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _dashboard_approved(db: sqlite3.Connection, draft_id: str) -> bool:
    return (
        _table_exists(db, "dashboard_approvals")
        and db.execute(
            "SELECT 1 FROM dashboard_approvals WHERE draft_id=?", (draft_id,)
        ).fetchone()
        is not None
    )


def _field_history(db: sqlite3.Connection, draft_id: str) -> list[dict]:
    if not _table_exists(db, "field_decisions"):
        return []
    history = []
    for row in db.execute(
        "SELECT field,decision,value,evidence,reviewer,rationale,decided_at "
        "FROM field_decisions WHERE draft_id=? ORDER BY id",
        (draft_id,),
    ):
        entry = dict(row)
        entry["value"] = json.loads(row["value"]) if row["value"] is not None else None
        entry["evidence"] = json.loads(row["evidence"])
        history.append(entry)
    return history


def _blocked(
    row: sqlite3.Row, draft: ExtractionDraft, supplemental: Collection[str]
) -> set[str]:
    comparison = json.loads(row["comparison"])
    blocked = set(supplemental) | set(draft.ambiguous_fields)
    blocked.update(item["field"] for item in comparison["conflicts"])
    if "funding_amount" in blocked or any(
        item.status != "distinct_cycles"
        for item in funding_conflicts(draft.funding_observations)
    ):
        blocked.update({"funding_amount", "living_stipend"})
    if "gpa_requirement" in blocked:
        blocked.update({"minimum_gpa", "gpa_scale"})
    if "language_requirement" in blocked:
        blocked.add("minimum_ielts")
    return blocked & REVIEW_FIELDS


def list_dashboard(staging_path: Path) -> list[dict]:
    with review._queue(staging_path) as db:
        rows = []
        for row in db.execute("SELECT * FROM drafts ORDER BY created_at,id"):
            draft = ExtractionDraft.model_validate_json(row["draft"])
            fields = draft.fields
            rows.append(
                {
                    **review._summary(row),
                    "name": fields.scholarship_name.quote
                    if fields.scholarship_name
                    else None,
                    "provider": (
                        fields.university_or_provider.quote
                        if fields.university_or_provider
                        else None
                    ),
                    "official_source_url": draft.official_source_url,
                    "retrieved_on": draft.retrieved_on.isoformat(),
                }
            )
        return rows


def inspect_dashboard(
    staging_path: Path, draft_id: str, *, blocked_fields: Collection[str] = ()
) -> dict:
    with review._queue(staging_path) as db:
        row = review._row(db, draft_id)
        draft = ExtractionDraft.model_validate_json(row["draft"])
        history = _field_history(db, draft_id)
        return {
            **review._inspect(db, row),
            "field_reviews": {item["field"]: item for item in history},
            "field_history": history,
            "blocked_fields": sorted(_blocked(row, draft, blocked_fields)),
            "dashboard_approved": _dashboard_approved(db, draft_id),
        }


def _contains(span: str, value: str) -> bool:
    normalized = normalize_name(value)
    return bool(normalized) and f" {normalized} " in f" {normalize_name(span)} "


def _supports_field(field: str, span: str, text: str) -> bool:
    if field == "tuition_coverage":
        return bool(re.search(r"\b(?:tuition|course fees|fee waiver)\b", span, re.I))
    if field in {"notes", "additional_requirements"}:
        return True  # These must reproduce the reviewer's cited source text.
    mapped = _ASSESSMENT_FIELD.get(field, field)
    scope = "funding" if field in _FUNDING_FIELDS else "unclear"
    return supports(mapped, span, text, scope)


def _has_number(field: str, span: str, value: int | float) -> bool:
    if _CONDITIONAL.search(span):
        return False
    if field == "gpa_scale":
        matches = re.findall(r"(?:on an? |out of |/\s*)(\d+(?:[.,]\d+)?)", span, re.I)
    else:
        label = "IELTS" if field == "minimum_ielts" else "(?:CGPA|GPA)"
        matches = re.findall(
            rf"\b{label}\s*(?:score\s*)?(?:of\s*|is\s*|:\s*|at least\s*)?"
            r"(\d+(?:[.,]\d+)?)\b",
            span,
            re.I,
        )
    return {float(match.replace(",", ".")) for match in matches} == {value}


def _value_matches(field: str, value: ReviewValue, spans: Sequence[str]) -> bool:
    if field == "application_deadline":
        dates = {explicit_deadline(span) for span in spans}
        return len(dates) == 1 and dates.pop() == date.fromisoformat(str(value))
    if field in {"minimum_gpa", "gpa_scale", "minimum_ielts"}:
        return isinstance(value, (int, float)) and all(
            _has_number(field, span, value) for span in spans
        )
    if field == "degree_level":
        return not any(_CONDITIONAL.search(span) for span in spans) and {
            degree
            for degree, pattern in _DEGREES.items()
            if any(re.search(pattern, span, re.I) for span in spans)
        } == {value}
    if field == "funding_type":
        combined = " ".join(spans)
        partial = re.search(r"\bpartial(?:ly)?\b", combined, re.I) is not None
        return (value == FundingType.PARTIALLY_FUNDED and partial) or (
            value == FundingType.FULLY_FUNDED and not partial
        )
    if field in _LITERAL_FIELDS or field not in CATALOGUE_FIELDS:
        return value in spans
    values = value if isinstance(value, list) else [str(value)]
    return all(any(_contains(span, item) for span in spans) for item in values)


def _verified_value(
    field: str, value: ReviewValue, evidence: Sequence[str], text: str
) -> ReviewValue:
    if not 1 <= len(evidence) <= 8 or any(
        not isinstance(span, str)
        or not span.strip()
        or len(span) > 400
        or span not in text
        for span in evidence
    ):
        raise ValueError("Use exact source spans from the staged excerpt")
    if not all(_supports_field(field, span, text) for span in evidence):
        raise ValueError("The cited text does not explicitly support this field")
    if field in _CAST:
        value = _CAST[field].dump_python(
            _CAST[field].validate_python(value), mode="json"
        )
    if field == "degree_level":
        value = str(value).casefold()
        if value == "doctoral":
            value = "doctorate"
    if not _value_matches(field, value, evidence):
        raise ValueError("The reviewed value does not match the cited evidence")
    return value


def save_field(
    staging_path: Path,
    draft_id: str,
    field: str,
    decision: Decision,
    reviewer: str,
    rationale: str,
    *,
    value: ReviewValue | None = None,
    evidence: Sequence[str] = (),
    blocked_fields: Collection[str] = (),
) -> dict:
    review._check_reviewer(reviewer, rationale)
    if field not in REVIEW_FIELDS:
        raise ValueError("Unknown review field")
    if decision not in {"accepted", "rejected", "unresolved"}:
        raise ValueError("Unknown field decision")
    if decision != "accepted" and (value is not None or evidence):
        raise ValueError(
            "Only accepted fields carry a reviewed value and supporting spans"
        )
    if decision == "accepted" and value is None:
        raise ValueError("An accepted field requires a reviewed value")
    with review._queue(staging_path) as db:
        row = review._row(db, draft_id)
        if row["state"] not in {"pending_review", "needs_more_evidence"}:
            raise ValueError("Field decisions are locked after a final draft decision")
        draft = ExtractionDraft.model_validate_json(row["draft"])
        draft.validate_source(row["source_text"])
        if value is not None:
            if field in _blocked(row, draft, blocked_fields):
                raise ValueError(
                    "Conflicting evidence must remain unresolved or rejected"
                )
            value = _verified_value(field, value, evidence, row["source_text"])
        entry = {
            "field": field,
            "decision": decision,
            "value": value,
            "evidence": list(evidence),
            "reviewer": reviewer.strip(),
            "rationale": rationale.strip(),
            "decided_at": review._now(),
        }
        _ensure_tables(db)
        db.execute(
            "INSERT INTO field_decisions(draft_id,field,decision,value,evidence,"
            "reviewer,rationale,decided_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                draft_id,
                field,
                decision,
                json.dumps(value, ensure_ascii=False) if value is not None else None,
                json.dumps(list(evidence), ensure_ascii=False),
                entry["reviewer"],
                entry["rationale"],
                entry["decided_at"],
            ),
        )
        return entry


def _approved_material(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    verified_at: date,
    blocked_fields: Collection[str],
) -> tuple[CatalogueRecord, dict[str, list[str]]]:
    draft = ExtractionDraft.model_validate_json(row["draft"])
    text = row["source_text"]
    draft.validate_source(text)
    try:
        get_source(draft.official_source_url)
    except PublicPageError:
        raise ValueError("The staged official source is no longer registered") from None
    latest = {item["field"]: item for item in _field_history(db, row["id"])}
    accepted = {
        field: item for field, item in latest.items() if item["decision"] == "accepted"
    }
    missing = [field for field in REQUIRED_FIELDS if field not in accepted]
    if missing:
        raise ValueError(
            "Accept required fields before approval: " + ", ".join(missing)
        )
    disputed = _blocked(row, draft, blocked_fields)
    if disputed.intersection(accepted):
        raise ValueError("A field accepted earlier now has conflicting evidence")
    evidence = {
        name: item["evidence"]
        for name, item in accepted.items()
        if name in CATALOGUE_FIELDS
    }
    values = {
        name: _verified_value(name, item["value"], item["evidence"], text)
        for name, item in accepted.items()
        if name in CATALOGUE_FIELDS
    }
    if values.get("funding_type") == FundingType.FULLY_FUNDED:
        tuition = str(values.get("tuition_coverage", ""))
        if not re.search(
            r"\b(?:full tuition|(?:all|full) (?:tuition|course fees)|"
            r"(?:tuition|course fees) (?:are |is )?covered in full)\b",
            tuition,
            re.I,
        ) or re.search(r"\b(?:not|only|except|unless|may)\b", tuition, re.I):
            raise ValueError(
                "Fully funded needs explicit full tuition coverage evidence"
            )
    return CatalogueRecord.model_validate(
        {
            **values,
            "official_source_url": draft.official_source_url,
            "last_verified_at": verified_at,
        }
    ), evidence


def approve(
    staging_path: Path,
    draft_id: str,
    reviewer: str,
    rationale: str,
    *,
    blocked_fields: Collection[str] = (),
) -> None:
    review._check_reviewer(reviewer, rationale)
    with review._queue(staging_path) as db:
        row = review._row(db, draft_id)
        record, evidence = _approved_material(db, row, date.today(), blocked_fields)
        review._save_decision(
            db, row, "approved", reviewer, rationale, record, evidence
        )
        db.execute(
            "INSERT INTO dashboard_approvals(draft_id,decided_at) VALUES(?,?)",
            (draft_id, review._now()),
        )


def publish_reviewed(
    staging_path: Path,
    draft_id: str,
    catalogue_path: Path,
    reviewer: str,
    rationale: str,
    *,
    blocked_fields: Collection[str] = (),
) -> int:
    def verify(db: sqlite3.Connection, row: sqlite3.Row) -> None:
        if not _dashboard_approved(db, draft_id):
            raise ValueError("Publication requires explicit dashboard approval")
        approved = CatalogueRecord.model_validate_json(row["approved_record"])
        record, evidence = _approved_material(
            db, row, approved.last_verified_at, blocked_fields
        )
        latest = db.execute(
            "SELECT evidence FROM decisions WHERE draft_id=? AND action='approved' "
            "ORDER BY id DESC LIMIT 1",
            (draft_id,),
        ).fetchone()
        if (
            record != approved
            or not latest
            or json.loads(latest["evidence"]) != evidence
        ):
            raise ValueError(
                "Approval must match the accepted fields and their evidence"
            )

    try:
        return review.publish(
            staging_path,
            draft_id,
            catalogue_path,
            reviewer=reviewer,
            rationale=rationale,
            _verify_dashboard=verify,
        )
    except PublicPageError:
        raise ValueError("The staged official source is no longer registered") from None
