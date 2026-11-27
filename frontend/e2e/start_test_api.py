"""Run browser tests against a temporary catalogue and synthetic review queue."""

import hashlib
import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from backend.app.database import create_database_engine, initialize_database
from backend.app.eligibility_api import evaluation_date
from backend.app.import_catalogue import import_catalogue, load_catalogue
from backend.app.main import create_app
from backend.app.review_api import ReviewSettings
from backend.app.schemas import CatalogueRecord
from backend.collection.extraction import Claim, DraftFields, ExtractionDraft
from backend.collection.funding_evidence import extract_funding
from backend.collection.review import stage

TEST_REVIEW_KEY = "browser-test-only-local-review-key-not-a-secret"
RETRIEVED_ON = date(2026, 11, 12)


def seed_review_queue(path: Path, catalogue: list[CatalogueRecord]) -> None:
    """Use made-up programmes and evidence; never open a real review queue."""
    candidates = (
        (
            "North Ridge Graduate Scholarship",
            "North Ridge University",
            "https://www.ox.ac.uk/admissions/graduate/fees-and-funding/funding/clarendon",
            False,
        ),
        (
            "Lakeview Graduate Scholarship",
            "Lakeview University",
            "https://www.cambridgetrust.org/scholarship/"
            "university-of-central-asia-cambridge-scholarship/",
            True,
        ),
    )
    for name, provider, url, conflict in candidates:
        claims = DraftFields(
            scholarship_name=Claim(quote=name, scope="programme"),
            university_or_provider=Claim(
                quote=f"This award is administered by {provider}.", scope="programme"
            ),
            destination_country=Claim(
                quote="Applicants study in Canada.", scope="programme"
            ),
            degree_level=Claim(
                quote="Approved master’s courses are eligible.", scope="programme"
            ),
            application_deadline=Claim(
                quote="Application deadline: 14 March 2030.", scope="funding"
            ),
            language_requirement=Claim(
                quote="An IELTS score of 6.5 or TOEFL equivalent is accepted.",
                scope="admission",
            ),
        )
        lines = [
            claim["quote"] for claim in claims.model_dump(exclude_none=True).values()
        ]
        if conflict:
            lines.extend(
                [
                    "Living stipend: CAD 2,500 per month during academic terms.",
                    "Living stipend: CAD 3,100 per month during academic terms.",
                ]
            )
        excerpt = "\n".join(lines)
        draft = ExtractionDraft(
            official_source_url=url,
            retrieved_on=RETRIEVED_ON,
            source_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
            fields=claims,
            evidence_version=2,
            ambiguous_fields=("funding_amount",) if conflict else (),
            funding_observations=extract_funding(
                excerpt, url, retrieved_on=RETRIEVED_ON
            ),
        )
        stage(path, draft, excerpt, catalogue, source_kind="manual")


def main() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    source_file = repository_root / "backend" / "data" / "curated_scholarships.json"
    with TemporaryDirectory(prefix="scholarship-browser-tests-") as directory:
        database_path = Path(directory) / "catalogue.sqlite3"
        review_path = Path(directory) / "review.sqlite3"
        catalogue = load_catalogue(source_file)
        engine = create_database_engine(database_path)
        try:
            initialize_database(engine)
            import_catalogue(engine, catalogue)
        finally:
            engine.dispose()
        seed_review_queue(review_path, catalogue.scholarships)
        os.environ["SCHOLARSHIP_DATABASE_PATH"] = str(database_path)
        application = create_app(
            database_path,
            review_settings=ReviewSettings(
                stage_path=review_path,
                token=TEST_REVIEW_KEY,
            ),
        )
        # This historical source snapshot must not change expected outcomes as
        # real deadlines pass. Production continues to use the server UTC date.
        application.dependency_overrides[evaluation_date] = lambda: date(2026, 11, 12)
        uvicorn.run(application, host="127.0.0.1", port=8000, proxy_headers=False)


if __name__ == "__main__":
    main()
