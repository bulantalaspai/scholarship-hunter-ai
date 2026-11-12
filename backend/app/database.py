"""File-based SQLite connections shared by the API and import command."""

import os
from collections.abc import Iterator
from pathlib import Path
from sqlite3 import Connection

from fastapi import Request
from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.orm import Session

from backend.app.models import Base

DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "scholarships.sqlite3"
)


def create_database_engine(database_path: str | Path | None = None) -> Engine:
    raw_path = str(
        database_path
        if database_path is not None
        else os.environ.get("SCHOLARSHIP_DATABASE_PATH", DEFAULT_DATABASE_PATH)
    )
    if not raw_path.strip() or "://" in raw_path or raw_path.startswith(("\\\\", "//")):
        raise ValueError("Use a local SQLite file path, not a URL or network share")
    path = Path(raw_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(path)),
        connect_args={"check_same_thread": False, "timeout": 10, "autocommit": False},
    )

    @event.listens_for(engine, "connect")
    def register_casefold(connection: Connection, _connection_record: object) -> None:
        connection.autocommit = True
        connection.execute("PRAGMA foreign_keys=ON")
        connection.autocommit = False
        connection.create_function(
            "casefold",
            1,
            lambda value: value.casefold() if value is not None else None,
            deterministic=True,
        )

    return engine


def initialize_database(engine: Engine) -> None:
    """Create missing tables without deleting records or importing sample data."""
    Base.metadata.create_all(engine)


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.database_engine) as session:
        yield session
