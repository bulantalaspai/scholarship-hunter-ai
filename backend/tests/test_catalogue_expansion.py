"""Expanded, real curated data remain compatible with the existing local services."""

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agent import run_agent
from backend.app.agent_schemas import AgentRequest
from backend.app.agent_tools import AgentTools
from backend.app.catalogue_quality import (
    EvidenceManifest,
    build_quality_report,
    main,
)
from backend.app.eligibility import catalogue_fingerprint
from backend.app.eligibility_api import evaluation_date
from backend.app.import_catalogue import import_catalogue, load_catalogue
from backend.app.main import create_app
from backend.app.models import Scholarship
from backend.app.official_pages import PublicPageError, approved_url
from backend.app.ollama_client import OllamaReply
from backend.app.schemas import CatalogueImport, ScholarshipRead

DATA = Path(__file__).parents[1] / "data"
TODAY = date(2026, 11, 12)
# Preserve every Phase 2 fact and its source date, not merely the display names.
ORIGINAL_FACTS = {
    "Study Scholarships - Master Studies for All Academic Disciplines": (
        "644ec9bb4e98bc9809dc40fe619fc0415eae7c5970de77510afbb889a6ac6585"
    ),
    "SMACCs Erasmus Mundus Joint Master (EMJM) Scholarships": (
        "308cc9ee169e85becd80910d83c689f909ad364fc52216b6c3d49785da2df0e1"
    ),
}
PROFILE = {
    "nationality": "Kazakhstan",
    "degree_level": "bachelor",
    "degree_completed": True,
    "field_of_study": "Computer Science",
    "gpa": 3.5,
    "gpa_scale": 4.0,
    "ielts_overall": 7.0,
    "intended_start_year": 2027,
    "funding_preference": "any_funding",
}


@pytest.fixture
def curated():
    return load_catalogue(DATA / "curated_scholarships.json")


@pytest.fixture
def expanded_api(engine, curated):
    import_catalogue(engine, curated)
    app = create_app(engine.url.database)
    app.dependency_overrides[evaluation_date] = lambda: TODAY
    with TestClient(app) as client:
        yield client


def test_existing_reviewed_facts_and_source_metadata_are_unchanged(curated):
    by_name = {record.scholarship_name: record for record in curated.scholarships}
    for name, fingerprint in ORIGINAL_FACTS.items():
        assert catalogue_fingerprint(by_name[name]) == fingerprint
    assert len({record.identity_key for record in curated.scholarships}) == len(
        curated.scholarships
    )


def test_all_curated_primary_sources_are_allowlisted_without_arbitrary_queries(curated):
    for record in curated.scholarships:
        source = str(record.official_source_url)
        assert approved_url(source) == source
        modified = source + ("&" if "?" in source else "?") + "unapproved_probe=blocked"
        with pytest.raises(PublicPageError, match="url_not_approved"):
            approved_url(modified)


def test_expansion_import_preserves_existing_ids_and_is_idempotent(engine, curated):
    original = curated.model_copy(
        update={
            "scholarships": [
                record
                for record in curated.scholarships
                if record.scholarship_name in ORIGINAL_FACTS
            ]
        }
    )
    assert import_catalogue(engine, original).created == 2
    with Session(engine) as session:
        before = {
            row.identity_key: (row.id, ScholarshipRead.model_validate(row).model_dump())
            for row in session.scalars(select(Scholarship))
        }
    imported = import_catalogue(engine, curated)
    assert imported.unchanged == 2 and imported.updated == 0
    assert imported.created == len(curated.scholarships) - 2
    with Session(engine) as session:
        after = {
            row.identity_key: (row.id, ScholarshipRead.model_validate(row).model_dump())
            for row in session.scalars(select(Scholarship))
        }
    assert all(after[key] == value for key, value in before.items())
    repeated = import_catalogue(engine, curated)
    assert repeated.unchanged == len(curated.scholarships)
    assert repeated.created == repeated.updated == repeated.skipped_older == 0


def test_expanded_api_pagination_and_detail_cover_every_record(expanded_api, curated):
    count = len(curated.scholarships)
    seen = []
    for page in range(1, (count + 6) // 7 + 1):
        response = expanded_api.get(
            "/api/scholarships", params={"page": page, "page_size": 7}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == count
        seen.extend(item["id"] for item in data["items"])
        for item in data["items"]:
            detail = expanded_api.get(f"/api/scholarships/{item['id']}")
            assert detail.status_code == 200 and detail.json() == item
    assert seen == list(range(1, count + 1))
    empty = expanded_api.get(
        "/api/scholarships", params={"page": count + 1, "page_size": 7}
    ).json()
    assert empty["items"] == [] and empty["total"] == count


@pytest.mark.parametrize(
    "filters",
    [
        {"country": "Germany"},
        {"field": "computer"},
        {"funding_type": "fully_funded"},
        {"country": "Finland", "field": "engineering", "funding_type": "fully_funded"},
    ],
)
def test_expanded_catalogue_supported_filters_match_curated_values(
    expanded_api, curated, filters
):
    def matches(record):
        return (
            (
                "country" not in filters
                or filters["country"].casefold()
                in [value.casefold() for value in record.destination_country or []]
            )
            and (
                "field" not in filters
                or any(
                    filters["field"].casefold() in value.casefold()
                    for value in record.eligible_study_fields or []
                )
            )
            and (
                "funding_type" not in filters
                or record.funding_type.value == filters["funding_type"]
            )
        )

    expected = [
        index
        for index, record in enumerate(curated.scholarships, start=1)
        if matches(record)
    ]
    response = expanded_api.get(
        "/api/scholarships", params=filters | {"page_size": 100}
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == expected
    assert response.json()["total"] == len(expected)


def test_expanded_matches_preserve_unknowns_and_global_counts(expanded_api, curated):
    response = expanded_api.post(
        "/api/eligibility/matches", json={"profile": PROFILE, "page_size": 100}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == sum(data["counts"].values()) == len(curated.scholarships)
    # No complete rules are invented from the expanded source notes.
    assert data["eligible"] == []
    assessments = [
        item["assessment"]
        for group in ("needs_verification", "ineligible")
        for item in data[group]
    ]
    assert len(assessments) == len(curated.scholarships)
    for assessment in assessments:
        assert assessment["unknown_requirements"]
        detail = expanded_api.post(
            "/api/eligibility/check",
            json={"profile": PROFILE, "scholarship_id": assessment["scholarship_id"]},
        )
        assert detail.json() == assessment


def test_agent_search_check_and_rank_use_expanded_database(engine, curated):
    import_catalogue(engine, curated)
    candidate_ids = list(range(1, min(3, len(curated.scholarships)) + 1))

    class Model:
        def __init__(self):
            self.round = 0

        def chat(self, messages, tools, *, timeout):
            self.round += 1
            if self.round == 1:
                functions = [("search_scholarships", {})]
            elif self.round == 2:
                search = json.loads(messages[-1]["content"])
                assert search["total"] == len(curated.scholarships)
                assert len(search["candidates"]) <= 3
                functions = [
                    ("rank_scholarships", {"scholarship_ids": candidate_ids}),
                ]
            else:
                functions = []
            return OllamaReply(
                model="qwen3:4b-instruct",
                done=True,
                done_reason="stop",
                prompt_eval_count=1500,
                message={
                    "content": json.dumps({"recommendation_ids": candidate_ids})
                    if not functions
                    else "",
                    "tool_calls": [
                        {"function": {"name": name, "arguments": arguments}}
                        for name, arguments in functions
                    ],
                },
            )

    request = AgentRequest(profile=PROFILE)
    with Session(engine) as session:
        tools = AgentTools(session, request.profile, TODAY)
        result = run_agent(request, tools, Model(), today=TODAY)
        # Avoid repeating an assessment in the 4096-token model history. Check
        # the individual tool independently against the same discovered record.
        check, event = tools.dispatch(
            "check_eligibility", {"scholarship_id": candidate_ids[0]}, step=1, timeout=1
        )
    assert event.status == "ok" and check["status"] != "eligible"
    assert result.steps == 3 and result.tool_calls == 2
    assert result.status == "needs_verification"
    assert len(result.recommendations) == len(candidate_ids)
    assert all(item.status == "ok" for item in result.tool_trace)
    assert all(item.assessment.status != "eligible" for item in result.recommendations)


def test_quality_report_counts_nulls_without_treating_them_as_waivers(catalogue):
    report = build_quality_report(catalogue, as_of=date(2026, 1, 2))
    assert report["total_records"] == report["source_metadata_complete_records"] == 3
    assert report["source_review_documented_records"] is None
    assert report["funding_counts"] == {
        "fully_funded": 1,
        "partially_funded": 1,
        "unknown": 1,
    }
    assert report["missing_field_counts"]["minimum_gpa"] == 2
    assert report["records_requiring_further_eligibility_verification"] == 3
    assert report["fully_reviewed_current_rule_records"] == 0
    assert report["duplicate_identity_keys"] == []


def test_quality_report_distinguishes_duplicates_from_separate_cycles(catalogue):
    values = catalogue.model_dump()
    first = values["scholarships"][0]
    values["scholarships"].extend([first.copy(), first | {"application_cycle": "2028"}])
    report = build_quality_report(
        CatalogueImport.model_validate(values), as_of=date(2026, 1, 2)
    )
    assert report["total_records"] == 5 and report["unique_identity_records"] == 4
    assert report["duplicate_identity_keys"][0]["occurrences"] == 2
    assert len(report["programme_provider_multiple_cycles"]) == 1


def test_quality_provenance_requires_matching_primary_source(catalogue):
    evidence = EvidenceManifest(
        records=[
            {
                "scholarship_name": catalogue.scholarships[0].scholarship_name,
                "sources": [
                    {
                        "url": str(catalogue.scholarships[0].official_source_url),
                        "claims": "Fictional test evidence only.",
                    }
                ],
            }
        ]
    )
    report = build_quality_report(catalogue, as_of=date(2026, 1, 2), evidence=evidence)
    assert report["source_review_documented_records"] == 1
    assert len(report["records_without_documented_source_review"]) == 2


def test_quality_cli_generates_reproducible_json(curated, capsys):
    assert main([str(DATA / "curated_scholarships.json"), "--as-of", "2026-11-12"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == build_quality_report(curated, as_of=TODAY)


def test_checked_in_quality_snapshot_and_source_reviews_match_catalogue(curated):
    evidence = EvidenceManifest.model_validate_json(
        (DATA / "catalogue_evidence.json").read_text(encoding="utf-8")
    )
    snapshot = json.loads((DATA / "QUALITY_REPORT.json").read_text(encoding="utf-8"))
    assert snapshot == build_quality_report(
        curated, as_of=date.fromisoformat(snapshot["as_of"]), evidence=evidence
    )
    assert snapshot["source_review_documented_records"] == len(curated.scholarships)
    assert snapshot["duplicate_identity_keys"] == []
    assert snapshot["duplicate_evidence_names"] == []
    assert snapshot["unused_evidence_names"] == []
    assert sum(snapshot["deadline_counts"].values()) == len(curated.scholarships)


def test_empty_quality_report_does_not_invent_verified_records():
    empty = CatalogueImport(schema_version=1, data_kind="curated", scholarships=[])
    report = build_quality_report(empty, as_of=TODAY)
    assert report["total_records"] == report["source_metadata_complete_records"] == 0
    assert report["earliest_verification_date"] is None
    assert report["latest_verification_date"] is None
    assert report["records"] == []


def test_quality_cli_rejects_invalid_evidence_without_partial_output(tmp_path, capsys):
    path = tmp_path / "invalid-evidence.json"
    path.write_text('{"records": [{"scholarship_name": "missing sources"}]}')
    assert main(["--evidence", str(path)]) == 1
    output = capsys.readouterr()
    assert output.out == "" and "validate" in output.err
