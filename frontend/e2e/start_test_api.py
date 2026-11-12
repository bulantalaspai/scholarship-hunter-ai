"""Run browser tests against a temporary, source-backed catalogue."""

import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from backend.app.database import create_database_engine, initialize_database
from backend.app.eligibility_api import evaluation_date
from backend.app.import_catalogue import import_catalogue, load_catalogue
from backend.app.main import create_app


def main() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    source_file = repository_root / "backend" / "data" / "curated_scholarships.json"
    with TemporaryDirectory(prefix="scholarship-browser-tests-") as directory:
        database_path = Path(directory) / "catalogue.sqlite3"
        engine = create_database_engine(database_path)
        try:
            initialize_database(engine)
            import_catalogue(engine, load_catalogue(source_file))
        finally:
            engine.dispose()
        os.environ["SCHOLARSHIP_DATABASE_PATH"] = str(database_path)
        application = create_app(database_path)
        # This historical source snapshot must not change expected outcomes as
        # real deadlines pass. Production continues to use the server UTC date.
        application.dependency_overrides[evaluation_date] = lambda: date(2026, 11, 12)
        uvicorn.run(application, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
