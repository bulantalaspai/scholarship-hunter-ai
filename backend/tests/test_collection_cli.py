"""Operator entry points keep dry runs and collection outside the active catalogue."""

import json
import sqlite3
from contextlib import closing
from datetime import date

from backend.app.database import create_database_engine, initialize_database
from backend.app.import_catalogue import import_catalogue, load_catalogue
from backend.collection import __main__ as cli

URL = "https://www.smaccs.eu/practical/scholarships/"


def test_dry_runs_use_no_model_and_create_no_staging_database(
    tmp_path, capsys, monkeypatch
):
    def unexpected_model(*args, **kwargs):
        raise AssertionError("Dry run reached extraction")

    monkeypatch.setattr(cli, "extract", unexpected_model)
    stage_path = tmp_path / "review.sqlite3"
    base = ["--stage-db", str(stage_path)]
    assert cli.main([*base, "pilot", "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert len(plan["items"]) == 6
    assert plan["live_pages_attempted"] == plan["live_pages_retrieved"] == 0
    assert cli.main([*base, "collect", URL, "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["live_fetch_blocked"] == "manual_review_required"
    assert not stage_path.exists()


def test_compare_db_reads_current_catalogue_without_updates(tmp_path):
    path = tmp_path / "catalogue.sqlite3"
    engine = create_database_engine(path)
    try:
        initialize_database(engine)
        import_catalogue(engine, load_catalogue(cli.DEFAULT_CATALOGUE))
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "UPDATE scholarships SET application_deadline=? "
                "WHERE official_source_url=?",
                ("2027-02-02", URL),
            )
        before = path.read_bytes()
        by_url = {
            str(item.official_source_url): item for item in cli.stored_records(path)
        }
        assert by_url[URL].application_deadline == date(2027, 2, 2)
        assert path.read_bytes() == before
    finally:
        engine.dispose()
