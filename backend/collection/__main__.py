"""Collect one approved source or run the fixed offline-source pilot."""

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.catalogue_quality import DEFAULT_CATALOGUE
from backend.app.database import create_database_engine
from backend.app.import_catalogue import load_catalogue
from backend.app.models import Scholarship
from backend.app.official_pages import PublicPageError
from backend.app.schemas import CatalogueRecord
from backend.collection.extraction import MAX_SOURCE_BYTES, ExtractionError, extract
from backend.collection.funding_evidence import funding_conflicts
from backend.collection.review import (
    decide,
    inspect_review,
    list_reviews,
    publish,
    stage,
)
from backend.collection.sources import fetch_source, get_source

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGE = ROOT / ".local-run" / "collection" / "review.sqlite3"
PILOT_IDS = ("S01", "S02", "S03", "S05", "S06", "S07")


def read_text(path: Path, limit: int) -> str:
    if not path.is_file():
        raise ValueError("A regular input file is required")
    with path.open("rb") as stream:
        body = stream.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Input file exceeds limit")
    return body.decode("utf-8-sig")


def stored_records(db_path: Path | None) -> list[CatalogueRecord]:
    if db_path is None:
        return load_catalogue(DEFAULT_CATALOGUE).scholarships
    engine = create_database_engine(db_path.resolve(strict=True))
    try:
        with Session(engine) as session:
            return [
                CatalogueRecord.model_validate(row)
                for row in session.scalars(select(Scholarship))
            ]
    finally:
        engine.dispose()


def collect_text(
    text: str,
    url: str,
    retrieved_on: date,
    staging_path: Path,
    catalogue: list[CatalogueRecord],
    source_kind: Literal["fixture", "manual", "live"],
) -> dict:
    draft = extract(text, url, retrieved_on)
    review = stage(staging_path, draft, text, catalogue, source_kind=source_kind)
    return {
        "source": url,
        "retrieved_on": retrieved_on.isoformat(),
        "draft_id": review["draft_id"],
        "state": review["state"],
        "duplicate_candidates": len(review["duplicate_candidates"]),
        "conflicts": len(review["conflicts"]),
        "wording_checks": len(review.get("wording_checks", [])),
        "expired_deadline": review["expired_deadline"],
        "missing_fields": review["missing_fields"],
        "unsupported_fields": draft.unsupported_fields,
        "ambiguous_fields": draft.ambiguous_fields,
        "funding_conflicts": len(funding_conflicts(draft.funding_observations)),
    }


def pilot(staging_path: Path, dry_run: bool) -> dict:
    manifest = ROOT / "evaluation" / "data" / "source_annotations.json"
    examples = {row["id"]: row for row in json.loads(manifest.read_bytes())["examples"]}
    catalogue = load_catalogue(DEFAULT_CATALOGUE).scholarships
    rows = []
    for sample in PILOT_IDS:
        item = examples[sample]
        url = item["source_url"]
        get_source(url)
        row = {"fixture": sample, "source": url}
        if not dry_run:
            try:
                row.update(
                    collect_text(
                        item["excerpt"],
                        url,
                        date.fromisoformat(item["accessed_at"]),
                        staging_path,
                        catalogue,
                        "fixture",
                    )
                )
            except ExtractionError as error:
                row["extraction_error"] = str(error)
        rows.append(row)
    return {
        "dry_run": dry_run,
        "live_pages_attempted": 0,
        "live_pages_retrieved": 0,
        "items": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-db", type=Path, default=DEFAULT_STAGE)
    commands = parser.add_subparsers(dest="command", required=True)
    batch = commands.add_parser("pilot", help="Use six archived official excerpts")
    batch.add_argument("--dry-run", action="store_true")
    collect = commands.add_parser("collect", help="Collect one registered URL")
    collect.add_argument("url")
    collect.add_argument("--dry-run", action="store_true")
    collect.add_argument(
        "--manual-text", type=Path, help="UTF-8 official source excerpt"
    )
    collect.add_argument("--retrieved-on", type=date.fromisoformat)
    collect.add_argument(
        "--compare-db", type=Path, help="Read an existing local SQLite catalogue"
    )
    commands.add_parser("list")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("draft_id")
    review = commands.add_parser("decide", help="Record a human review")
    review.add_argument("draft_id")
    review.add_argument(
        "decision", choices=["approved", "rejected", "needs_more_evidence"]
    )
    review.add_argument("--reviewer", required=True, help="Local reviewer identifier")
    review.add_argument("--rationale", required=True)
    review.add_argument(
        "--record", type=Path, help="Reviewed single catalogue record JSON"
    )
    review.add_argument(
        "--evidence", type=Path, help="JSON mapping approved fields to source spans"
    )
    publication = commands.add_parser("publish")
    publication.add_argument("draft_id")
    publication.add_argument("--catalogue-db", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "pilot":
            result = pilot(args.stage_db, args.dry_run)
        elif args.command == "collect":
            source = get_source(args.url)
            if bool(args.manual_text) != bool(args.retrieved_on):
                parser.error(
                    "--manual-text and --retrieved-on must be supplied together"
                )
            if args.dry_run:
                result = {
                    "dry_run": True,
                    "url": args.url,
                    "policy": source.model_dump(mode="json"),
                }
                if args.manual_text:
                    result["planned_method"] = "manual"
                else:
                    try:
                        fetch_source(args.url, dry_run=True)
                        result["planned_method"] = "approved_https"
                    except PublicPageError as error:
                        result["live_fetch_blocked"] = error.code
            else:
                catalogue = stored_records(args.compare_db)
                if args.manual_text:
                    body = read_text(args.manual_text, MAX_SOURCE_BYTES)
                    when = args.retrieved_on
                    kind = "manual"
                else:
                    page = fetch_source(args.url)
                    if page is None:
                        raise RuntimeError("Live collection requires a source response")
                    body = page.untrusted_text
                    when = page.fetched_at.date()
                    kind = "live"
                result = collect_text(
                    body,
                    args.url,
                    when,
                    args.stage_db,
                    catalogue,
                    kind,
                )
        elif args.command == "list":
            result = list_reviews(args.stage_db)
        elif args.command == "inspect":
            result = inspect_review(args.stage_db, args.draft_id)
        elif args.command == "decide":
            record = (
                CatalogueRecord.model_validate_json(read_text(args.record, 65_536))
                if args.record
                else None
            )
            decide(
                args.stage_db,
                args.draft_id,
                args.decision,
                args.reviewer,
                args.rationale,
                approved_record=record,
                evidence=(
                    TypeAdapter(dict[str, list[str]]).validate_json(
                        read_text(args.evidence, 16_384), strict=True
                    )
                    if args.evidence
                    else None
                ),
            )
            result = {"draft_id": args.draft_id, "decision": args.decision}
        else:
            result = {
                "scholarship_id": publish(
                    args.stage_db, args.draft_id, args.catalogue_db
                )
            }
        print(json.dumps(result, ensure_ascii=True, default=str, indent=2))
        return int(
            args.command == "pilot"
            and any("extraction_error" in r for r in result["items"])
        )
    except (PublicPageError, ExtractionError) as error:
        print(f"Collection stopped ({error}).", file=sys.stderr)
    except ValidationError as error:
        locations = [list(e["loc"]) for e in error.errors(include_input=False)]
        print(f"Invalid input fields {json.dumps(locations)}", file=sys.stderr)
    except (ValueError, OSError, KeyError, sqlite3.Error, SQLAlchemyError) as error:
        # Avoid echoing untrusted content, paths, or SQL parameters to logs.
        print(
            f"Collection stopped ({type(error).__name__}). "
            "Check inputs and review state.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
