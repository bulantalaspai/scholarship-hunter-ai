"""Validate and transactionally import manually curated JSON. No network access."""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.database import create_database_engine, initialize_database
from backend.app.models import Scholarship
from backend.app.schemas import CatalogueImport, ImportResult


def load_catalogue(path: Path) -> CatalogueImport:
    return CatalogueImport.model_validate_json(path.read_text(encoding="utf-8-sig"))


def import_catalogue(
    engine: Engine, catalogue: CatalogueImport, *, allow_demo: bool = False
) -> ImportResult:
    if catalogue.data_kind != "curated" and not allow_demo:
        raise ValueError(
            "Fictional demo data is for isolated tests, not the application catalogue"
        )

    unique = {}
    for record in catalogue.scholarships:
        key = record.identity_key
        if key in unique and unique[key].database_values() != record.database_values():
            raise ValueError("Conflicting duplicate records in the same import")
        unique[key] = record

    result = ImportResult()
    with Session(engine) as session, session.begin():
        for key, record in unique.items():
            values = record.database_values()
            current = session.scalar(
                select(Scholarship).where(Scholarship.identity_key == key)
            )
            if current is not None:
                if current.last_verified_at > record.last_verified_at:
                    result.skipped_older += 1
                    continue
                if all(
                    getattr(current, field) == value for field, value in values.items()
                ):
                    result.unchanged += 1
                    continue
                result.updated += 1
            else:
                result.created += 1

            statement = insert(Scholarship).values(**values)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[Scholarship.identity_key],
                    set_={
                        field: value
                        for field, value in values.items()
                        if field != "identity_key"
                    },
                    where=Scholarship.last_verified_at
                    <= statement.excluded.last_verified_at,
                )
            )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-path",
        type=Path,
        help="Local SQLite file (default: backend/data/scholarships.sqlite3)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create missing tables; never delete records")
    import_parser = commands.add_parser(
        "import", help="Validate and import a curated JSON file"
    )
    import_parser.add_argument("file", type=Path)
    args = parser.parse_args(argv)

    engine = None
    try:
        catalogue = load_catalogue(args.file) if args.command == "import" else None
        if catalogue is not None and catalogue.data_kind != "curated":
            raise ValueError("Fictional demo data cannot be imported by this command")
        engine = create_database_engine(args.database_path)
        initialize_database(engine)
        if catalogue is not None:
            print(import_catalogue(engine, catalogue).model_dump_json())
        else:
            print("SQLite catalogue initialized; no records deleted or imported.")
    except (OSError, ValueError, ValidationError, SQLAlchemyError) as error:
        print(f"Catalogue command failed: {error}", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
