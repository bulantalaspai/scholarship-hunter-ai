from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.database import create_database_engine, initialize_database
from backend.app.import_catalogue import import_catalogue, load_catalogue
from backend.app.main import create_app
from backend.app.schemas import CatalogueImport

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "demo_scholarships.json"


@pytest.fixture(autouse=True)
def isolate_default_database(monkeypatch, tmp_path):
    # Also isolates the original health tests, which import the default app.
    monkeypatch.setenv("SCHOLARSHIP_DATABASE_PATH", str(tmp_path / "default.sqlite3"))


@pytest.fixture
def engine(tmp_path):
    database_engine = create_database_engine(tmp_path / "catalogue.sqlite3")
    initialize_database(database_engine)
    yield database_engine
    database_engine.dispose()


@pytest.fixture
def catalogue() -> CatalogueImport:
    return load_catalogue(FIXTURE_PATH)


@pytest.fixture
def seeded_engine(engine, catalogue):
    import_catalogue(engine, catalogue, allow_demo=True)
    return engine


@pytest.fixture
def client(seeded_engine):
    database_path = seeded_engine.url.database
    with TestClient(create_app(database_path)) as api_client:
        yield api_client


@pytest.fixture
def session(seeded_engine):
    with Session(seeded_engine) as database_session:
        yield database_session
