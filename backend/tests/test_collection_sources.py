"""Collector policy, durable rate limits, and safe transport integration."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app import official_pages as pages
from backend.collection import sources

URL = "https://www.smaccs.eu/practical/scholarships/"


@pytest.fixture
def reviewed(monkeypatch, tmp_path):
    record = sources.get_source(URL).model_dump(mode="json")
    registry = tmp_path / "registry.json"
    record.update(
        collection_method="approved_https",
        terms_status="allowed",
        robots_status="allowed",
        policy_checked_on=datetime.now(UTC).date().isoformat(),
        terms_evidence="Test terms permit this exact path and interval.",
        robots_evidence="Test robots rules permit this client and path.",
    )
    registry.write_text(json.dumps([record]), encoding="utf8")
    monkeypatch.setattr(sources, "REGISTRY", registry)
    return record


def test_every_primary_source_is_registered_and_requires_manual_entry(tmp_path):
    catalogue = (
        Path(__file__).parents[1] / "data" / "curated_scholarships.json"
    ).read_text(encoding="utf8")
    db = tmp_path / "not_created.sqlite3"
    for record in json.loads(catalogue)["scholarships"]:
        url = record["official_source_url"]
        source = sources.get_source(url)
        assert source.last_verified_at.isoformat() == record["last_verified_at"]
        for dry_run in (True, False):
            with pytest.raises(pages.PublicPageError, match="manual_review_required"):
                sources.fetch_source(url, dry_run=dry_run, state_path=db)
    assert not db.exists()


@pytest.mark.parametrize(
    "url",
    [
        URL + "#fragment",
        URL.replace("https:", "http:"),
        URL.replace("www.smaccs.eu", "127.0.0.1"),
        URL.replace("www.smaccs.eu", "localhost"),
        URL.replace("www.smaccs.eu", "user@www.smaccs.eu"),
        URL + "?profile=x",
        "https://www.smaccs.eu/",
    ],
)
def test_unregistered_path_scheme_host_rejected(url):
    with pytest.raises(pages.PublicPageError, match="source_not_registered"):
        sources.get_source(url)


@pytest.mark.parametrize(
    "changes",
    [
        {"terms_status": "disallowed"},
        {"robots_status": "unclear"},
        {
            "policy_checked_on": (
                datetime.now(UTC).date() - timedelta(days=1)
            ).isoformat()
        },
        {"terms_evidence": " "},
        {"robots_evidence": None},
        {"collection_method": "manual"},
    ],
)
def test_missing_permission_evidence_never_calls_transport(
    reviewed, changes, tmp_path, monkeypatch
):
    sources.REGISTRY.write_text(json.dumps([reviewed | changes]), encoding="utf8")
    monkeypatch.setattr(sources, "fetch_official_page", lambda *a, **k: pytest.fail())
    with pytest.raises(pages.PublicPageError, match="manual_review_required"):
        sources.fetch_source(URL, state_path=tmp_path / "access.sqlite3")


def test_registry_cannot_authorize_transport_to_another_host(reviewed):
    for url in ("https://127.0.0.1/path", URL.replace("https:", "http:")):
        with pytest.raises(ValidationError):
            sources.Source.model_validate(reviewed | {"entry_urls": [url]})


def test_approved_dry_run_has_no_side_effects(reviewed, monkeypatch, tmp_path):
    db = tmp_path / "access.sqlite3"
    monkeypatch.setattr(sources, "fetch_official_page", lambda *a, **k: pytest.fail())
    assert sources.fetch_source(URL, dry_run=True, state_path=db) is None
    assert not db.exists()


@pytest.mark.parametrize("code", ["timeout", "http_error", "redirect_blocked"])
def test_failure_suspends_domain_and_logs_only_safe_outcome(
    reviewed, tmp_path, monkeypatch, code
):
    def fail(url, *, timeout, for_collection):
        assert url == URL and timeout <= 6 and for_collection is True
        raise pages.PublicPageError(code)

    monkeypatch.setattr(sources, "fetch_official_page", fail)
    db = tmp_path / "access.sqlite3"
    with pytest.raises(pages.PublicPageError, match=code):
        sources.fetch_source(URL, state_path=db)
    with pytest.raises(pages.PublicPageError, match="domain_suspended"):
        sources.fetch_source(URL, state_path=db)
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute(
            "SELECT source_url,outcome,text_sha256 FROM collection_requests"
        ).fetchall() == [(URL, code, None)]


def test_concurrent_collectors_share_durable_domain_limit(
    reviewed, tmp_path, monkeypatch
):
    first = URL
    second = "https://www.smaccs.eu/"
    sources.REGISTRY.write_text(
        json.dumps([reviewed | {"entry_urls": [first, second]}]), encoding="utf8"
    )
    page = pages.OfficialPage(
        source_url=first,
        fetched_at=datetime.now(UTC),
        untrusted_text="Test",
        truncated=False,
    )
    monkeypatch.setattr(sources, "fetch_official_page", lambda *a, **k: page)
    db = tmp_path / "access.sqlite3"

    def collect(url):
        try:
            sources.fetch_source(url, state_path=db)
        except pages.PublicPageError as e:
            return e.code
        return "retrieved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(collect, [first, second]))
    assert results.count("retrieved") == 1
    assert set(results) <= {"retrieved", "source_rate_limited", "domain_suspended"}
    assert collect(first) == "source_rate_limited"


def test_collector_does_not_follow_even_an_agent_approved_redirect(
    reviewed, tmp_path, monkeypatch
):
    connected = []

    class Redirect:
        status = 302

        def close(self):
            pass

    class Connection:
        def __init__(self, host, *args):
            connected.append(host)

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Redirect()

        def abort(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(pages, "resolve_public_address", lambda *a: (2, "8.8.8.8"))
    monkeypatch.setattr(pages, "_PinnedHTTPSConnection", Connection)
    with pytest.raises(pages.PublicPageError, match="redirect_blocked"):
        sources.fetch_source(URL, state_path=tmp_path / "access.sqlite3")
    assert connected == ["www.smaccs.eu"]


def test_even_an_approved_entry_with_private_dns_cannot_connect(
    reviewed, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        pages.socket,
        "getaddrinfo",
        lambda *a: [
            (pages.socket.AF_INET, pages.socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))
        ],
    )
    monkeypatch.setattr(pages, "_PinnedHTTPSConnection", lambda *a: pytest.fail())
    with pytest.raises(pages.PublicPageError, match="nonpublic_address"):
        sources.fetch_source(URL, state_path=tmp_path / "access.sqlite3")


@pytest.mark.parametrize(
    ("body", "headers"),
    [
        (b"<p>Verify you are human</p>", {}),
        (b"<p>Members only</p><form><input type='password'></form>", {}),
        (b"<p>Subscribe to continue</p>", {}),
        (b"<p>Loading information</p>", {"cf-mitigated": "challenge"}),
    ],
)
def test_successful_http_with_access_barrier_is_never_staged(
    reviewed,
    tmp_path,
    monkeypatch,
    body,
    headers,
):
    from unittest.mock import Mock

    from backend.tests.test_official_pages import FakeResponse

    response = FakeResponse(body, headers=headers)
    connection = Mock()
    connection.getresponse.return_value = response
    monkeypatch.setattr(pages, "resolve_public_address", lambda *a: (2, "8.8.8.8"))
    monkeypatch.setattr(pages, "_PinnedHTTPSConnection", lambda *a: connection)
    db = tmp_path / "access.sqlite3"
    with pytest.raises(pages.PublicPageError, match="access_barrier"):
        sources.fetch_source(URL, state_path=db)
    with pytest.raises(pages.PublicPageError, match="domain_suspended"):
        sources.fetch_source(URL, state_path=db)
    connection.request.assert_called_once()
