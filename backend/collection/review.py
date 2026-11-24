"""Local, append-audited review queue. Only explicit human decisions can publish."""

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from backend.app.programme_resolution import load_aliases, normalize_name
from backend.app.schemas import CatalogueRecord
from backend.collection.extraction import ExtractionDraft
from backend.collection.sources import get_source


@contextmanager
def _queue(path: Path) -> Iterator[sqlite3.Connection]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        tables = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if tables - {"drafts", "decisions"}:
            raise ValueError("Choose a dedicated collection staging database")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, source_text TEXT NOT NULL,
            draft TEXT NOT NULL, comparison TEXT NOT NULL, created_at TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending_review', approved_record TEXT,
            published_id INTEGER, published_catalogue TEXT)""")
        db.execute("""CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES drafts(id),
            action TEXT NOT NULL, reviewer TEXT NOT NULL, rationale TEXT NOT NULL,
            decided_at TEXT NOT NULL, approved_record TEXT, evidence TEXT)""")
        if "evidence" not in {
            c["name"] for c in db.execute("PRAGMA table_info(decisions)")
        }:
            db.execute("ALTER TABLE decisions ADD COLUMN evidence TEXT")
        yield db
        db.commit()
    finally:
        db.close()  # rolls back any unfinished transaction


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row(db: sqlite3.Connection, draft_id: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown collection draft")
    return row


def _summary(row: sqlite3.Row) -> dict:
    return {
        **json.loads(row["comparison"]),
        "draft_id": row["id"],
        "source_kind": row["kind"],
        "state": row["state"],
        "published_id": row["published_id"],
    }


def list_reviews(staging_path: Path) -> list[dict]:
    with _queue(staging_path) as db:
        return [
            _summary(row)
            for row in db.execute("SELECT * FROM drafts ORDER BY created_at,id")
        ]


def inspect_review(staging_path: Path, draft_id: str) -> dict:
    with _queue(staging_path) as db:
        row = _row(db, draft_id)
        history = [
            dict(item)
            for item in db.execute(
                "SELECT action,reviewer,rationale,decided_at,approved_record,evidence "
                "FROM decisions WHERE draft_id=? ORDER BY id",
                (draft_id,),
            )
        ]
        for entry in history:
            if entry["approved_record"]:
                entry["approved_record"] = json.loads(entry["approved_record"])
            if entry["evidence"]:
                entry["evidence"] = json.loads(entry["evidence"])
        return {
            **_summary(row),
            "created_at": row["created_at"],
            "source_text": row["source_text"],
            "draft": json.loads(row["draft"]),
            "history": history,
        }


def _matches(name: str, url: str, stored_name: str, stored_url: str) -> bool:
    if url == stored_url or normalize_name(stored_name) == normalize_name(name):
        return True
    return any(
        str(entry.official_source_url) == stored_url
        and normalize_name(stored_name) == normalize_name(entry.scholarship_name)
        and normalize_name(name) in {normalize_name(alias) for alias in entry.aliases}
        for entry in load_aliases().programmes
    )


def _deadline(quote: str) -> date | None:
    # Ambiguous numeric dates and ranges need human interpretation.
    dates = re.findall(
        r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2} [A-Za-z]+ \d{4}|[A-Za-z]+ \d{1,2},? \d{4})\b",
        quote,
    )
    if len(dates) != 1:
        return None
    for pattern in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(dates[0].replace(",", ""), pattern).date()
        except ValueError:
            continue
    return None


def _comparison(draft: ExtractionDraft, catalogue: Sequence[CatalogueRecord]) -> dict:
    # A disagreement is a review flag: literal excerpts can differ in wording,
    # coverage, call year, or award type without establishing a factual change.
    claims = {
        field: claim.quote
        for field in type(draft.fields).model_fields
        if (claim := getattr(draft.fields, field)) is not None
    }
    url = str(draft.official_source_url)
    duplicates = []
    conflicts = []
    wording_checks = []
    deadline = _deadline(claims.get("application_deadline", ""))
    for record in catalogue:
        if not _matches(
            claims.get("scholarship_name", ""),
            url,
            record.scholarship_name,
            str(record.official_source_url),
        ):
            continue
        duplicates.append(
            {
                "identity_key": record.identity_key,
                "name": record.scholarship_name,
                "cycle": record.application_cycle,
                "funding_type": record.funding_type.value,
            }
        )
        for field, quote in claims.items():
            known = getattr(record, field, None)
            if field == "funding_type" and record.funding_type == "unknown":
                continue
            if known is None:
                continue
            values = known if isinstance(known, list) else [known]
            if all(
                normalize_name(str(value)) in normalize_name(quote) for value in values
            ):
                continue
            # Only directly comparable, explicit values count as discrepancies.
            # Cross-scope deadlines and paraphrases need human review.
            discrepancy = (
                field == "funding_type"
                and draft.fields.funding_type.scope == "funding"
                and normalize_name(quote) in {"fully funded", "partially funded"}
            ) or (
                field == "application_deadline"
                and deadline is not None
                and draft.fields.application_deadline.scope == "funding"
                and deadline != record.application_deadline
            )
            (conflicts if discrepancy else wording_checks).append(
                {
                    "identity_key": record.identity_key,
                    "field": field,
                    "catalogue": record.model_dump(mode="json")[field],
                    "excerpt": quote,
                }
            )
    return {
        "duplicate_candidates": duplicates,
        "conflicts": conflicts,
        "wording_checks": wording_checks,
        "expired_deadline": deadline < datetime.now(UTC).date() if deadline else None,
        "missing_fields": [
            field for field in type(draft.fields).model_fields if field not in claims
        ],
    }


def stage(
    staging_path: Path,
    draft: ExtractionDraft,
    source_text: str,
    catalogue: Sequence[CatalogueRecord],
    *,
    source_kind: str = "fixture",
) -> dict:
    if source_kind not in {"fixture", "manual", "live"}:
        raise ValueError("Unknown source kind")
    source = get_source(str(draft.official_source_url))
    if source_kind == "live" and not source.allows_https_today():
        raise ValueError("Live collection requires reviewed permissions")
    draft.validate_source(source_text)
    payload = json.dumps(
        draft.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
    )
    draft_id = hashlib.sha256((source_kind + "\n" + payload).encode()).hexdigest()
    comparison = _comparison(draft, catalogue)
    with _queue(staging_path) as db:
        previous = db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if previous is not None:
            return _summary(previous)
        comparison["related_draft_ids"] = []
        for row in db.execute("SELECT id,draft FROM drafts"):
            other = ExtractionDraft.model_validate_json(row["draft"])
            same_name = (
                draft.fields.scholarship_name
                and other.fields.scholarship_name
                and _matches(
                    draft.fields.scholarship_name.quote,
                    draft.official_source_url,
                    other.fields.scholarship_name.quote,
                    other.official_source_url,
                )
            )
            if same_name or other.official_source_url == draft.official_source_url:
                comparison["related_draft_ids"].append(row["id"])
        db.execute(
            """INSERT INTO drafts(id,kind,source_text,draft,comparison,created_at)
                   VALUES(?,?,?,?,?,?)""",
            (
                draft_id,
                source_kind,
                source_text,
                payload,
                json.dumps(comparison),
                _now(),
            ),
        )
        return _summary(_row(db, draft_id))


def _check_evidence(record: CatalogueRecord, text: str, evidence: dict | None) -> None:
    required = {
        key
        for key, value in record.model_dump(
            exclude={"official_source_url", "last_verified_at", "eligibility_rules"},
            exclude_none=True,
            mode="json",
        ).items()
        if key != "funding_type" or value != "unknown"
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        raise ValueError("Evidence keys must match every populated catalogue fact")
    for spans in evidence.values():
        if (
            not isinstance(spans, list)
            or not spans
            or any(
                not isinstance(span, str) or not span.strip() or span not in text
                for span in spans
            )
        ):
            raise ValueError(
                "Each reviewed fact needs a literal supporting source span"
            )


def decide(
    staging_path: Path,
    draft_id: str,
    decision: str,
    reviewer: str,
    rationale: str,
    *,
    approved_record: CatalogueRecord | None = None,
    evidence: dict[str, list[str]] | None = None,
) -> None:
    if decision not in {"approved", "rejected", "needs_more_evidence"}:
        raise ValueError("Unknown review decision")
    if not 1 <= len(reviewer.strip()) <= 100 or not 1 <= len(rationale.strip()) <= 2000:
        raise ValueError(
            "Provide a reviewer identifier and a concise evidence rationale"
        )
    if (approved_record is not None) != (decision == "approved"):
        raise ValueError("Only approval requires a manually verified catalogue record")
    if decision != "approved" and evidence is not None:
        raise ValueError("Field evidence belongs to a human approval decision")
    with _queue(staging_path) as db:
        row = _row(db, draft_id)
        if row["published_id"] is not None:
            raise ValueError("Published decisions are immutable")
        if row["state"] in {"approved", "rejected"}:
            raise ValueError(
                "A final decision already exists; stage a revised submission"
            )
        payload = None
        if approved_record is not None:
            draft = ExtractionDraft.model_validate_json(row["draft"])
            if row["kind"] == "fixture":
                raise ValueError("Fixture material cannot be approved for publication")
            if json.loads(row["comparison"])["duplicate_candidates"]:
                raise ValueError(
                    "Possible catalogue duplicate requires separate reconciliation"
                )
            if approved_record.eligibility_rules is not None:
                raise ValueError("Structured eligibility rules require separate review")
            if str(approved_record.official_source_url) != str(
                draft.official_source_url
            ):
                raise ValueError("Reviewed source must match the staged source")
            if approved_record.last_verified_at < draft.retrieved_on:
                raise ValueError("Verification cannot predate retrieval")
            _check_evidence(approved_record, row["source_text"], evidence)
            payload = approved_record.model_dump_json()
        db.execute(
            "UPDATE drafts SET state=?,approved_record=? WHERE id=?",
            (decision, payload, draft_id),
        )
        db.execute(
            """INSERT INTO decisions(draft_id,action,reviewer,rationale,
                   decided_at,approved_record,evidence)
                   VALUES(?,?,?,?,?,?,?)""",
            (
                draft_id,
                decision,
                reviewer.strip(),
                rationale.strip(),
                _now(),
                payload,
                json.dumps(evidence, ensure_ascii=False) if evidence else None,
            ),
        )


def publish(staging_path: Path, draft_id: str, catalogue_path: Path) -> int:
    """Insert the approved record and its receipt in one SQLite transaction."""
    target = Path(catalogue_path).resolve(strict=True)
    if target == Path(staging_path).resolve():
        raise ValueError("Staging and catalogue must be separate databases")
    with _queue(staging_path) as db:
        row = _row(db, draft_id)
        if (
            row["state"] != "approved"
            or not row["approved_record"]
            or row["kind"] == "fixture"
        ):
            raise ValueError(
                "Explicit human approval of original source material is required"
            )
        record = CatalogueRecord.model_validate_json(row["approved_record"])
        approval = db.execute(
            "SELECT approved_record,evidence FROM decisions "
            "WHERE draft_id=? AND action='approved' ORDER BY id DESC LIMIT 1",
            (draft_id,),
        ).fetchone()
        if not approval or approval["approved_record"] != row["approved_record"]:
            raise ValueError("Approved record differs from the audit trail")
        _check_evidence(
            record, row["source_text"], json.loads(approval["evidence"] or "null")
        )
        get_source(str(record.official_source_url))
        db.execute("ATTACH DATABASE ? AS catalogue", (str(target),))
        for schema in ("main", "catalogue"):
            if db.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0] not in {
                "delete",
                "truncate",
                "persist",
            }:
                raise ValueError(
                    "Publication requires rollback journals for atomic writes"
                )
        if row["published_id"] is not None:
            existing = db.execute(
                "SELECT identity_key FROM catalogue.scholarships WHERE id=?",
                (row["published_id"],),
            ).fetchone()
            if (
                row["published_catalogue"] != str(target)
                or not existing
                or existing[0] != record.identity_key
            ):
                raise ValueError(
                    "Publication receipt differs from the target catalogue"
                )
            return row["published_id"]
        for old in db.execute(
            "SELECT scholarship_name,official_source_url FROM catalogue.scholarships"
        ):
            if _matches(
                record.scholarship_name, str(record.official_source_url), old[0], old[1]
            ):
                raise ValueError("Possible duplicate programme, annual call or award.")
        values = record.database_values()
        columns = list(values)
        parameters = [
            json.dumps(v)
            if isinstance(v, list)
            else v.isoformat()
            if isinstance(v, date)
            else v
            for v in values.values()
        ]
        cursor = db.execute(
            f"INSERT INTO catalogue.scholarships ({','.join(columns)}) "
            f"VALUES ({','.join('?' for _ in columns)})",
            parameters,
        )
        published_id = cursor.lastrowid
        db.execute(
            "UPDATE drafts SET published_id=?,published_catalogue=? WHERE id=?",
            (published_id, str(target), draft_id),
        )
        db.execute(
            """INSERT INTO decisions(draft_id,action,reviewer,rationale,decided_at)
                   VALUES(?,'published','collector','Inserted approved record',?)""",
            (draft_id, _now()),
        )
        return published_id
