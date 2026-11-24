"""Exact source permissions for the offline collector. Independent of agent access."""

import re
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from backend.app.official_pages import (
    OfficialPage,
    PublicPageError,
    approved_url,
    fetch_official_page,
)

REGISTRY = Path(__file__).with_name("sources.json")
DEFAULT_STATE = REGISTRY.parents[2] / ".local-run" / "collector_access.sqlite3"


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization: str = Field(min_length=1)
    official_domain: str
    entry_urls: tuple[str, ...] = Field(min_length=1)
    collection_method: Literal["manual", "approved_https"]
    terms_status: Literal["unreviewed", "allowed", "disallowed", "unclear"]
    robots_status: Literal["unreviewed", "allowed", "disallowed", "unclear"]
    policy_checked_on: date | None
    terms_evidence: str | None
    robots_evidence: str | None
    min_interval_seconds: int = Field(strict=True, ge=60, le=86400)
    last_verified_at: date
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_entries(self):
        domain = self.official_domain
        if not re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,63}", domain):
            raise ValueError("Expected a public DNS hostname")
        if domain.endswith((".local", ".localhost", ".internal")):
            raise ValueError("Local hosts cannot be registered")
        for url in self.entry_urls:
            parts = urlsplit(url)
            if (
                parts.scheme != "https"
                or parts.netloc != domain
                or not parts.path.startswith("/")
                or any(char in url for char in "#\\")
                or any(ord(c) <= 32 or ord(c) == 127 for c in url)
                or len(url) > 2048
            ):
                raise ValueError("Expected exact HTTPS URL on the registered domain")
        return self

    def allows_https_today(self) -> bool:
        # The offline policy review covers all listed paths, request identity and
        # minimum interval. Ignore yesterday's review, even for known providers.
        return (
            self.collection_method == "approved_https"
            and self.terms_status == self.robots_status == "allowed"
            and self.policy_checked_on == datetime.now(UTC).date()
            and bool((self.terms_evidence or "").strip())
            and bool((self.robots_evidence or "").strip())
        )


def get_source(url: str) -> Source:
    registered = TypeAdapter(list[Source]).validate_json(REGISTRY.read_bytes())
    matches = [source for source in registered if url in source.entry_urls]
    if len(matches) != 1:
        raise PublicPageError("source_not_registered")
    return matches[0]


def _reserve(db: sqlite3.Connection, source: Source, url: str) -> int:
    db.execute("BEGIN IMMEDIATE")
    db.execute(
        "CREATE TABLE IF NOT EXISTS collection_access (domain TEXT PRIMARY KEY, "
        "next_allowed REAL NOT NULL, suspended INTEGER NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS collection_requests (id INTEGER PRIMARY KEY, "
        "source_url TEXT NOT NULL, attempted_at TEXT NOT NULL, outcome TEXT NOT NULL, "
        "text_sha256 TEXT)"
    )
    now = datetime.now(UTC)
    access = db.execute(
        "SELECT next_allowed, suspended FROM collection_access WHERE domain = ?",
        (source.official_domain,),
    ).fetchone()
    if access and access[1]:
        raise PublicPageError("domain_suspended")
    if access and now.timestamp() < access[0]:
        raise PublicPageError("source_rate_limited")
    # Reserve before opening the socket. Crashed requests leave a durable pause
    # requiring inspection, including crashes after receipt of a server refusal.
    db.execute(
        "INSERT INTO collection_access VALUES (?, ?, 1) "
        "ON CONFLICT(domain) DO UPDATE SET next_allowed=excluded.next_allowed, "
        "suspended=1",
        (source.official_domain, now.timestamp() + source.min_interval_seconds),
    )
    attempt = db.execute(
        "INSERT INTO collection_requests(source_url,attempted_at,outcome) "
        "VALUES (?, ?, 'attempted')",
        (url, now.isoformat()),
    ).lastrowid
    db.commit()
    return attempt


def fetch_source(
    url: str, *, dry_run: bool = False, state_path: Path = DEFAULT_STATE
) -> OfficialPage | None:
    """Fetch at most one exact, policy-approved page. Dry run checks policy offline."""
    source = get_source(url)
    if not source.allows_https_today():
        raise PublicPageError("manual_review_required")
    # This also checks the underlying safe transport's independent allowlist.
    approved_url(url)
    if dry_run:
        return None
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(state_path, timeout=3)) as db:
        attempt = _reserve(db, source, url)
        try:
            page = fetch_official_page(url, timeout=6, for_collection=True)
        except PublicPageError as error:
            # Keep a durable suspension on every failure. No retry loops and no
            # early retry after 429/503 (including Retry-After) or a CAPTCHA.
            db.execute(
                "UPDATE collection_requests SET outcome=? WHERE id=?",
                (error.code, attempt),
            )
            db.commit()
            raise
        db.execute(
            "UPDATE collection_requests SET outcome='retrieved', text_sha256=? "
            "WHERE id=?",
            (sha256(page.untrusted_text.encode()).hexdigest(), attempt),
        )
        db.execute(
            "UPDATE collection_access SET suspended=0 WHERE domain=?",
            (source.official_domain,),
        )
        db.commit()
        return page
