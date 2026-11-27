"""Exercise the private HTTP surface with disposable synthetic databases."""

import hashlib
from contextlib import closing
from datetime import UTC, datetime
from sqlite3 import connect

import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.app.main import create_app
from backend.app.review_api import MAX_BODY, ReviewSettings
from backend.collection.extraction import Claim, DraftFields, ExtractionDraft
from backend.collection.funding_evidence import extract_funding
from backend.collection.review import stage

ORIGIN = "http://127.0.0.1:5173"
KEY = "synthetic-review-key-for-tests-only-0000"
AUTH = {"Authorization": f"Bearer {KEY}", "Origin": ORIGIN}
SOURCE = "https://www.smaccs.eu/practical/scholarships/"
ENTRY = "/api/review/drafts"
ACTOR = {"reviewer": "Test reviewer", "rationale": "Synthetic evidence inspected."}
FACTS = {
    "scholarship_name": (
        "North Ridge Graduate Scholarship",
        "North Ridge Graduate Scholarship",
    ),
    "university_or_provider": (
        "North Ridge University",
        "This award is administered by North Ridge University.",
    ),
    "destination_country": (["Canada"], "Applicants study in Canada."),
    "degree_level": ("master", "Approved master’s courses are eligible."),
}


@pytest.fixture
def review_app(tmp_path):
    staging = tmp_path / "review.sqlite3"
    catalogue = tmp_path / "catalogue.sqlite3"
    text = "\n".join(span for _, span in FACTS.values())
    text += (
        "\nLiving stipend: CAD 800 per month during academic terms."
        "\nLiving stipend: CAD 900 per month during academic terms."
    )
    today = datetime.now(UTC).date()
    draft = ExtractionDraft(
        official_source_url=SOURCE,
        retrieved_on=today,
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        fields=DraftFields(
            scholarship_name=Claim(
                quote=FACTS["scholarship_name"][1], scope="programme"
            )
        ),
        evidence_version=2,
        funding_observations=extract_funding(text, SOURCE, retrieved_on=today),
    )
    key = stage(staging, draft, text, [], source_kind="manual")["draft_id"]
    settings = ReviewSettings(staging, KEY, origins=(ORIGIN,))
    return create_app(catalogue, review_settings=settings), f"{ENTRY}/{key}", staging


def local_client(app, *, peer="127.0.0.1"):
    return TestClient(app, base_url=ORIGIN, client=(peer, 54_000))


def test_admin_routes_are_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("SCHOLARSHIP_REVIEW_STAGE", raising=False)
    monkeypatch.delenv("SCHOLARSHIP_REVIEW_TOKEN", raising=False)
    with local_client(create_app(tmp_path / "source.sqlite3")) as client:
        assert client.get(ENTRY, headers=AUTH).status_code == 404
        assert client.get("/api/health").status_code == 200


def test_review_queue_cannot_be_used_as_catalogue(review_app):
    _, _, staging = review_app
    app = create_app(staging, review_settings=ReviewSettings(staging, KEY))
    with pytest.raises(ValueError, match="must be separate files"), local_client(app):
        pass
    with closing(connect(staging)) as db:
        assert (
            db.execute(
                "SELECT name FROM sqlite_master WHERE name='scholarships'"
            ).fetchone()
            is None
        )


def test_access_key_is_required_for_read_and_write(review_app):
    app, url, staging = review_app
    with local_client(app) as client:
        assert client.get(ENTRY).status_code == 401
        assert client.get(f"{url}?key={KEY}").status_code == 401
        assert client.post(f"{url}/approve", json=ACTOR).status_code == 401
        bad_key = {**AUTH, "Authorization": "Bearer " + "x" * 32}
        assert client.get(url, headers=bad_key).status_code == 401
        assert ENTRY not in client.get("/openapi.json").json()["paths"]
    with closing(connect(staging)) as db:
        assert db.execute("SELECT COUNT(*) FROM decisions").fetchone() == (0,)


@pytest.mark.parametrize(
    "header", [{"Host": "hostile.example:5173"}, {"Origin": "http://hostile.example"}]
)
def test_rejects_rebinding_and_cross_origin_even_with_key(review_app, header):
    app, url, _ = review_app
    with local_client(app) as client:
        assert client.get(url, headers={**AUTH, **header}).status_code == 403
        assert (
            client.get(
                url, headers={**AUTH, "Sec-Fetch-Site": "cross-site"}
            ).status_code
            == 403
        )


def test_rejects_non_loopback_peer(review_app):
    app, url, _ = review_app
    with local_client(app, peer="192.0.2.1") as client:
        assert client.get(url, headers=AUTH).status_code == 403


def test_proxy_middleware_cannot_supply_a_loopback_peer(review_app):
    app, url, _ = review_app
    proxied = ProxyHeadersMiddleware(app, trusted_hosts="*")
    headers = {**AUTH, "X-Forwarded-For": "127.0.0.1"}
    with local_client(proxied, peer="192.0.2.1") as client:
        assert client.get(url, headers=headers).status_code == 403
        assert (
            client.post(f"{url}/publish", headers=headers, json=ACTOR).status_code
            == 403
        )


@pytest.mark.parametrize(
    "header",
    [
        "Forwarded",
        "X-Forwarded-For",
        "X-Forwarded-Host",
        "X-Forwarded-Proto",
        "X-Real-IP",
    ],
)
def test_rejects_forwarding_metadata_from_loopback(review_app, header):
    app, url, _ = review_app
    with local_client(app) as client:
        assert client.get(url, headers={**AUTH, header: "127.0.0.1"}).status_code == 403


def test_guards_confirmation_body_and_error_cache(review_app):
    app, url, _ = review_app
    with local_client(app) as client:
        locked = client.post(
            f"{url}/publish", json={**ACTOR, "confirm": False}, headers=AUTH
        )
        assert locked.status_code == 422
        assert locked.headers["cache-control"] == "no-store"
        assert (
            client.post(f"{url}/approve", data=ACTOR, headers=AUTH).status_code == 415
        )
        large = client.post(
            f"{url}/approve",
            json={**ACTOR, "confirm": True, "rationale": "y" * MAX_BODY},
            headers=AUTH,
        )
        assert large.status_code == 413
        assert client.get(f"{ENTRY}/{'b' * 64}", headers=AUTH).status_code == 404


def test_review_conflict_approval_and_publication_use_separate_actions(review_app):
    app, url, _ = review_app
    with local_client(app) as client:
        observed = client.get(url, headers=AUTH)
        assert observed.headers["cache-control"] == "no-store"
        draft = observed.json()
        assert draft["state"] == "pending_review"
        assert draft["official_source_url"] == SOURCE
        assert draft["scholarship_name"] == FACTS["scholarship_name"][0]
        assert len(draft["funding_conflicts"]) == 1
        assert "living_stipend" in draft["blocked_fields"]
        confirmed = {**ACTOR, "confirm": True}
        assert (
            client.post(f"{url}/publish", headers=AUTH, json=confirmed).status_code
            == 409
        )
        assert (
            client.post(f"{url}/approve", headers=AUTH, json=confirmed).status_code
            == 409
        )
        blocked = client.post(
            f"{url}/fields/living_stipend",
            headers=AUTH,
            json={
                **ACTOR,
                "decision": "accepted",
                "value": "CAD 900 monthly",
                "evidence": [
                    "Living stipend: CAD 900 per month during academic terms."
                ],
            },
        )
        assert blocked.status_code == 409

        for field, (value, evidence) in FACTS.items():
            saved = client.post(
                f"{url}/fields/{field}",
                headers=AUTH,
                json={
                    **ACTOR,
                    "decision": "accepted",
                    "value": value,
                    "evidence": [evidence],
                },
            )
            assert saved.status_code == 200, saved.text
        approval = client.post(f"{url}/approve", headers=AUTH, json=confirmed)
        assert approval.status_code == 200, approval.text
        assert approval.json()["state"] == "approved"
        assert client.get("/api/scholarships").json()["total"] == 0
        for _ in range(2):
            publication = client.post(f"{url}/publish", headers=AUTH, json=confirmed)
            assert publication.status_code == 200, publication.text
            assert publication.json()["published_id"] == 1
        published = client.get("/api/scholarships").json()
        assert published["total"] == 1
        assert published["items"][0]["living_stipend"] is None
