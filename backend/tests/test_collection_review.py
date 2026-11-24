"""Fictional submissions in temporary databases only. No human pilot labels."""

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import create_database_engine, initialize_database
from backend.app.models import Scholarship
from backend.app.schemas import CatalogueRecord
from backend.collection.extraction import Claim, DraftFields, ExtractionDraft
from backend.collection.review import (
    decide,
    inspect_review,
    list_reviews,
    publish,
    stage,
)

URL = "https://www.smaccs.eu/practical/scholarships/"
OTHER_URL = "https://www.master-ediss.eu/scholarship/"
STAMP = date(2026, 11, 11)


def dossier(name="Test-only award", url=URL):
    text = (
        f"{name}. Fictional provider, Fictional destination. "
        "Partially funded. Apply by 20 March 2020."
    )
    return (
        ExtractionDraft(
            official_source_url=url,
            retrieved_on=STAMP,
            source_sha256=hashlib.sha256(text.encode()).hexdigest(),
            fields=DraftFields(
                scholarship_name=Claim(quote=name, scope="programme"),
                funding_type=Claim(quote="Partially funded", scope="funding"),
                application_deadline=Claim(
                    quote="Apply by 20 March 2020.", scope="funding"
                ),
            ),
        ),
        text,
    )


def record(**overrides):
    values = dict(
        official_source_url=URL,
        last_verified_at=STAMP,
        scholarship_name="Test-only award",
        university_or_provider="Fictional provider",
        application_cycle="2020",
        funding_type="partially_funded",
        destination_country=["Fictional destination"],
        application_deadline="2020-03-20",
    )
    return CatalogueRecord.model_validate(values | overrides)


@pytest.fixture
def paths(tmp_path):
    target = tmp_path / "catalogue.sqlite3"
    engine = create_database_engine(target)
    initialize_database(engine)
    engine.dispose()
    return tmp_path / "review.sqlite3", target


def citations(name="Test-only award"):
    return {
        "scholarship_name": [name],
        "university_or_provider": ["Fictional provider"],
        "destination_country": ["Fictional destination"],
        "funding_type": ["Partially funded"],
        "application_cycle": ["2020"],
        "application_deadline": ["Apply by 20 March 2020."],
    }


def approve(queue, key, approved=None):
    approved = approved or record()
    decide(
        queue,
        key,
        "approved",
        "test-reviewer",
        "Test decision for temporary database.",
        approved_record=approved,
        evidence=citations(approved.scholarship_name),
    )


def test_exact_restage_preserves_decisions_and_source(paths):
    queue, target = paths
    draft, text = dossier()
    first = stage(queue, draft, text, [], source_kind="manual")
    key = first["draft_id"]
    assert first["state"] == "pending_review"
    assert first["expired_deadline"] and "gpa_requirement" in first["missing_fields"]
    decide(queue, key, "needs_more_evidence", "test-reviewer", "Missing evidence")
    assert (
        stage(queue, draft, text, [], source_kind="manual")["state"]
        == "needs_more_evidence"
    )
    assert len(list_reviews(queue)) == 1
    view = inspect_review(queue, key)
    assert view["source_text"] == text
    assert view["draft"]["official_source_url"] == URL
    assert (
        view["history"][0]["decided_at"]
        and view["history"][0]["rationale"] == "Missing evidence"
    )
    with pytest.raises(ValueError):
        publish(queue, key, target)
    decide(queue, key, "rejected", "test-reviewer", "No further evidence")
    with pytest.raises(ValueError, match="final decision"):
        approve(queue, key)


def test_fixture_and_incomplete_approval_never_publish(paths):
    queue, target = paths
    draft, text = dossier()
    key = stage(queue, draft, text, [])["draft_id"]
    with pytest.raises(ValueError, match="Fixture"):
        approve(queue, key)
    with pytest.raises(ValueError):
        publish(queue, key, target)
    with pytest.raises(ValueError):
        stage(queue, draft, text + " changed", [])
    with pytest.raises(ValueError):
        stage(queue, draft, text, [], source_kind="live")
    manual = stage(queue, draft, text, [], source_kind="manual")["draft_id"]
    with pytest.raises(ValueError, match="match the staged"):
        approve(queue, manual, record(official_source_url=OTHER_URL))
    with pytest.raises(ValueError, match="predate"):
        approve(queue, manual, record(last_verified_at="2020-03-20"))
    with pytest.raises(ValueError, match="manually verified"):
        decide(queue, manual, "approved", "test-reviewer", "Unchecked")
    assert inspect_review(queue, manual)["history"] == []


def test_publication_and_receipt_are_atomic_and_retry_safe(paths):
    queue, target = paths
    key = stage(queue, *dossier(), [], source_kind="manual")["draft_id"]
    approve(queue, key)
    with closing(sqlite3.connect(queue)) as conn, conn:
        conn.execute("""CREATE TRIGGER fail_receipt
           BEFORE UPDATE OF published_id ON drafts
           BEGIN SELECT RAISE(ABORT,'simulated receipt failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        publish(queue, key, target)
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT count(*) FROM scholarships").fetchone() == (0,)
    with closing(sqlite3.connect(queue)) as conn, conn:
        conn.execute("DROP TRIGGER fail_receipt")
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: publish(queue, key, target), range(2))) == [1, 1]
    view = inspect_review(queue, key)
    assert [item["action"] for item in view["history"]] == ["approved", "published"]
    assert view["history"][0]["evidence"] == citations()
    assert view["published_id"] == 1
    engine = create_database_engine(target)
    try:
        with Session(engine) as session:
            obj = session.scalars(select(Scholarship)).one()
            assert obj.id == 1 and obj.destination_country == ["Fictional destination"]
            assert obj.application_deadline == date(2020, 3, 20)
            assert obj.eligible_nationalities is None and obj.minimum_gpa is None
    finally:
        engine.dispose()
    with pytest.raises(ValueError, match="immutable"):
        decide(queue, key, "rejected", "test-reviewer", "Late decision")


def test_aliases_shared_urls_and_different_calls_are_flagged_not_merged(paths):
    queue, target = paths
    known = record(
        scholarship_name="SMACCs Erasmus Mundus Joint Master (EMJM) Scholarships",
        application_cycle="2019",
        application_deadline="2019-02-01",
        funding_type="fully_funded",
        tuition_coverage="Fictional coverage",
        living_stipend="Fictional stipend",
    )
    engine = create_database_engine(target)
    try:
        with Session(engine) as session, session.begin():
            session.add(Scholarship(**known.database_values()))
    finally:
        engine.dispose()
    key = stage(queue, *dossier("SMACCs", OTHER_URL), [known], source_kind="manual")
    assert len(key["duplicate_candidates"]) == 1
    assert {x["field"] for x in key["conflicts"]} == {
        "funding_type",
        "application_deadline",
    }
    assert any(x["field"] == "scholarship_name" for x in key["wording_checks"])
    reviewed = record(scholarship_name="SMACCs", official_source_url=OTHER_URL)
    with pytest.raises(ValueError, match="duplicate"):
        approve(queue, key["draft_id"], reviewed)
    # New active records may appear after the source snapshot was checked.
    unchecked = stage(
        queue, *dossier("Different title: SMACCs", OTHER_URL), [], source_kind="manual"
    )
    assert unchecked["related_draft_ids"] == [key["draft_id"]]
    approve(queue, unchecked["draft_id"], reviewed)
    with pytest.raises(ValueError, match="duplicate"):
        publish(queue, unchecked["draft_id"], target)
    other = stage(queue, *dossier("A different call"), [known], source_kind="manual")
    assert other["duplicate_candidates"][0]["identity_key"] == known.identity_key
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute(
            "SELECT id,application_cycle FROM scholarships"
        ).fetchall() == [(1, "2019")]
    with pytest.raises(ValueError, match="dedicated"):
        list_reviews(target)


@pytest.mark.parametrize(
    "change",
    [
        None,
        {"funding_type": []},
        {"funding_type": ["   "]},
        {"funding_type": ["Unsupported quotation"]},
        {"unexpected": ["Test-only award"]},
        {"funding_type": "Partially funded"},
    ],
)
def test_blank_untraced_or_extra_approval_evidence_is_rejected(paths, change):
    queue, target = paths
    key = stage(queue, *dossier(), [], source_kind="manual")["draft_id"]
    evidence = citations()
    if change is None:
        del evidence["funding_type"]
    else:
        evidence.update(change)
    with pytest.raises(ValueError, match="Evidence keys|source span"):
        decide(
            queue,
            key,
            "approved",
            "test-reviewer",
            "Fixture rationale",
            approved_record=record(),
            evidence=evidence,
        )
    assert inspect_review(queue, key)["history"] == []
    with pytest.raises(ValueError):
        publish(queue, key, target)
