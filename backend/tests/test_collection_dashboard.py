"""Exercise review and publication using fictional excerpts and temporary files."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, date, datetime
from sqlite3 import connect

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import create_database_engine, initialize_database
from backend.app.models import Scholarship
from backend.collection import dashboard, review, sources
from backend.collection.extraction import Claim, DraftFields, ExtractionDraft

URL = "https://www.smaccs.eu/practical/scholarships/"
NAME = "North Ridge Graduate Scholarship"
PROVIDER = "This award is administered by North Ridge University."
DESTINATION = "Applicants study in Canada."
DEGREE = "Approved master’s courses are eligible."
STIPEND = "The living stipend is CAD 2,300 per month during academic terms."
TEXT = "\n".join((NAME, PROVIDER, DESTINATION, DEGREE, STIPEND))
REVIEWER = "test-reviewer"
RATIONALE = "Fictional publication exercise."
REQUIRED = {
    "scholarship_name": (NAME, NAME),
    "university_or_provider": ("North Ridge University", PROVIDER),
    "destination_country": (["Canada"], DESTINATION),
    "degree_level": ("master", DEGREE),
}


def staged(path, *, text=TEXT, kind="manual"):
    draft = ExtractionDraft(
        official_source_url=URL,
        retrieved_on=min(date.today(), datetime.now(UTC).date()),
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        fields=DraftFields(
            scholarship_name=Claim(quote=NAME, scope="programme"),
        ),
    )
    return review.stage(path, draft, text, [], source_kind=kind)["draft_id"]


@pytest.fixture
def setup_review(tmp_path):
    catalogue = tmp_path / "catalogue.sqlite3"
    engine = create_database_engine(catalogue)
    initialize_database(engine)
    engine.dispose()
    queue = tmp_path / "review.sqlite3"
    return queue, staged(queue), catalogue


def accept_required(queue, draft_id):
    for field, (value, span) in REQUIRED.items():
        dashboard.save_field(
            queue,
            draft_id,
            field,
            "accepted",
            REVIEWER,
            RATIONALE,
            value=value,
            evidence=[span],
        )


def test_field_review_appends_history_without_changing_draft_state(setup_review):
    queue, draft_id, _ = setup_review
    assert dashboard.list_dashboard(queue)[0]["name"] == NAME
    original = dashboard.inspect_dashboard(queue, draft_id)
    assert original["field_history"] == [] and original["source_text"] == TEXT

    first = dashboard.save_field(
        queue, draft_id, "destination_country", "unresolved", REVIEWER, "Check campus"
    )
    assert datetime.fromisoformat(first["decided_at"]).tzinfo == UTC
    second = dashboard.save_field(
        queue,
        draft_id,
        "destination_country",
        "accepted",
        REVIEWER,
        RATIONALE,
        value=["Canada"],
        evidence=[DESTINATION],
    )
    view = dashboard.inspect_dashboard(queue, draft_id)
    assert view["state"] == "pending_review" and view["history"] == []
    assert view["field_history"] == [first, second]
    assert view["field_reviews"]["destination_country"] == second


@pytest.mark.parametrize(
    ("field", "value", "span", "error"),
    [
        ("scholarship_name", NAME, "Invented span", "exact source"),
        ("university_or_provider", "Canada", DESTINATION, "explicitly support"),
        ("destination_country", ["United Kingdom"], DESTINATION, "does not match"),
        ("degree_level", "doctoral", DEGREE, "does not match"),
        ("funding_amount", "CAD 2,300", STIPEND, "does not match"),
        ("living_stipend", "CAD 2,300 per month", STIPEND, "does not match"),
    ],
)
def test_false_or_misattributed_evidence_is_rejected(
    setup_review, field, value, span, error
):
    queue, draft_id, _ = setup_review
    with pytest.raises(ValueError, match=error):
        dashboard.save_field(
            queue,
            draft_id,
            field,
            "accepted",
            REVIEWER,
            RATIONALE,
            value=value,
            evidence=[span],
        )
    assert dashboard.inspect_dashboard(queue, draft_id)["field_history"] == []


def test_required_fields_and_audit_cannot_be_bypassed(setup_review):
    queue, draft_id, target = setup_review
    with pytest.raises(ValueError, match="Accept required fields"):
        dashboard.approve(queue, draft_id, REVIEWER, RATIONALE)
    with pytest.raises(ValueError, match="Explicit human approval"):
        dashboard.publish_reviewed(queue, draft_id, target, REVIEWER, RATIONALE)

    accept_required(queue, draft_id)
    dashboard.save_field(
        queue, draft_id, "eligible_nationalities", "unresolved", REVIEWER, RATIONALE
    )
    dashboard.approve(queue, draft_id, REVIEWER, RATIONALE)
    approved = dashboard.inspect_dashboard(queue, draft_id)
    assert approved["dashboard_approved"]
    assert approved["published_id"] is None
    with pytest.raises(ValueError, match="locked"):
        dashboard.save_field(
            queue, draft_id, "destination_country", "rejected", REVIEWER, RATIONALE
        )
    with pytest.raises(ValueError, match="through the dashboard"):
        review.publish(queue, draft_id, target)

    def publish_once(_):
        return dashboard.publish_reviewed(queue, draft_id, target, REVIEWER, RATIONALE)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(publish_once, range(2))) == [1, 1]
    published = dashboard.inspect_dashboard(queue, draft_id)
    assert published["published_id"] == 1
    assert [item["action"] for item in published["history"]] == [
        "approved",
        "published",
    ]
    assert published["history"][-1]["reviewer"] == REVIEWER
    assert published["history"][-1]["rationale"] == RATIONALE
    engine = create_database_engine(target)
    try:
        with Session(engine) as session:
            record = session.scalars(select(Scholarship)).one()
            assert record.degree_level == "master"
            assert record.eligible_nationalities is None and record.minimum_gpa is None
    finally:
        engine.dispose()


def test_conflict_blocks_stipend_and_rechecks_before_publication(setup_review):
    queue, draft_id, target = setup_review
    accept_required(queue, draft_id)
    conflict = {"funding_amount"}
    assert dashboard.inspect_dashboard(queue, draft_id, blocked_fields=conflict)[
        "blocked_fields"
    ] == ["funding_amount", "living_stipend"]
    with pytest.raises(ValueError, match="must remain unresolved"):
        dashboard.save_field(
            queue,
            draft_id,
            "living_stipend",
            "accepted",
            REVIEWER,
            RATIONALE,
            value=STIPEND,
            evidence=[STIPEND],
            blocked_fields=conflict,
        )
    dashboard.save_field(
        queue,
        draft_id,
        "living_stipend",
        "accepted",
        REVIEWER,
        RATIONALE,
        value=STIPEND,
        evidence=[STIPEND],
    )
    with pytest.raises(ValueError, match="now has conflicting evidence"):
        dashboard.approve(queue, draft_id, REVIEWER, RATIONALE, blocked_fields=conflict)
    dashboard.approve(queue, draft_id, REVIEWER, RATIONALE)
    with pytest.raises(ValueError, match="now has conflicting evidence"):
        dashboard.publish_reviewed(
            queue, draft_id, target, REVIEWER, RATIONALE, blocked_fields=conflict
        )
    assert dashboard.inspect_dashboard(queue, draft_id)["published_id"] is None


def test_fixture_cannot_be_approved(setup_review):
    queue, _, _ = setup_review
    draft_id = staged(queue, kind="fixture")
    accept_required(queue, draft_id)
    with pytest.raises(ValueError, match="Fixture material"):
        dashboard.approve(queue, draft_id, REVIEWER, RATIONALE)


def test_numeric_gpa_does_not_discard_conditional_scope(setup_review):
    queue, _, _ = setup_review
    conditional = "Applicants in Canada must have a minimum GPA of 3.5 on a 4.0 scale."
    span = "If applying from Canada, the minimum GPA is 3.5 on a 4.0 scale."
    draft_id = staged(queue, text=TEXT + "\n" + conditional + "\n" + span)
    with pytest.raises(ValueError, match="does not match"):
        dashboard.save_field(
            queue,
            draft_id,
            "minimum_gpa",
            "accepted",
            REVIEWER,
            RATIONALE,
            value=3.5,
            evidence=[span],
        )
    claim = dashboard.save_field(
        queue,
        draft_id,
        "gpa_requirement",
        "accepted",
        REVIEWER,
        RATIONALE,
        value=span,
        evidence=[span],
    )
    assert claim["value"] == span


def test_publication_rejects_an_approved_snapshot_that_no_longer_matches(setup_review):
    queue, draft_id, target = setup_review
    accept_required(queue, draft_id)
    dashboard.approve(queue, draft_id, REVIEWER, RATIONALE)

    # Simulate an inconsistent local queue apart from the HTTP/CLI entry points.
    with closing(connect(queue)) as db, db:
        db.execute(
            "UPDATE field_decisions SET decision='rejected',value=NULL,evidence='[]' "
            "WHERE draft_id=? AND field='destination_country'",
            (draft_id,),
        )
    with pytest.raises(ValueError, match="Accept required fields"):
        dashboard.publish_reviewed(queue, draft_id, target, REVIEWER, RATIONALE)
    assert dashboard.inspect_dashboard(queue, draft_id)["published_id"] is None


def test_removal_from_source_registry_blocks_approval_and_publication(
    setup_review, tmp_path, monkeypatch
):
    queue, draft_id, target = setup_review
    accept_required(queue, draft_id)
    empty_registry = tmp_path / "empty-registry.json"
    empty_registry.write_text("[]", encoding="utf-8")
    with monkeypatch.context() as patch:
        patch.setattr(sources, "REGISTRY", empty_registry)
        with pytest.raises(ValueError, match="no longer registered"):
            dashboard.approve(queue, draft_id, REVIEWER, RATIONALE)

    dashboard.approve(queue, draft_id, REVIEWER, RATIONALE)
    monkeypatch.setattr(sources, "REGISTRY", empty_registry)
    with pytest.raises(ValueError, match="no longer registered"):
        dashboard.publish_reviewed(queue, draft_id, target, REVIEWER, RATIONALE)
    assert dashboard.inspect_dashboard(queue, draft_id)["published_id"] is None


def test_catalogue_duplicates_are_rechecked_on_insert(setup_review):
    queue, first_id, target = setup_review
    second_id = staged(queue, text=TEXT + "\nUpdated cover note.")
    for draft_id in (first_id, second_id):
        accept_required(queue, draft_id)
        dashboard.approve(queue, draft_id, REVIEWER, RATIONALE)
    assert dashboard.publish_reviewed(queue, first_id, target, REVIEWER, RATIONALE) == 1
    with pytest.raises(ValueError, match="duplicate"):
        dashboard.publish_reviewed(queue, second_id, target, REVIEWER, RATIONALE)
    assert dashboard.inspect_dashboard(queue, second_id)["published_id"] is None
