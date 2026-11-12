import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_list_has_consistent_envelope_and_pagination_defaults(client):
    response = client.get("/api/scholarships")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"items", "total", "page", "page_size"}
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert [record["id"] for record in data["items"]] == [1, 2, 3]
    assert "identity_key" not in data["items"][0]


@pytest.mark.parametrize(
    ("query", "expected_ids"),
    [
        ({"country": "Germany"}, [1]),
        ({"country": "  finLAND  "}, [1]),
        ({"country": "France"}, [2]),
        ({"field": "computer"}, [1]),
        ({"field": "ÉCONOMIE"}, [2]),
        ({"funding_type": "fully_funded"}, [1]),
        ({"funding_type": "partially_funded"}, [2]),
        ({"funding_type": "unknown"}, [3]),
        (
            {
                "country": "Germany",
                "field": "engineering",
                "funding_type": "fully_funded",
            },
            [1],
        ),
        ({"country": "France", "field": "engineering"}, []),
    ],
)
def test_filters_are_composable_and_match_array_entries(client, query, expected_ids):
    response = client.get("/api/scholarships", params=query)
    assert response.status_code == 200
    data = response.json()
    assert [record["id"] for record in data["items"]] == expected_ids
    assert data["total"] == len(expected_ids)


@pytest.mark.parametrize(
    "query",
    [
        {"country": "No such country"},
        {"field": "%"},
        {"field": "_"},
        {"country": "Germany' OR 1=1 --"},
        {"field": "'; DROP TABLE scholarships; --"},
    ],
)
def test_empty_results_and_literal_filtering_are_safe(client, query):
    response = client.get("/api/scholarships", params=query)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}
    assert client.get("/api/scholarships").json()["total"] == 3


def test_pagination_is_stable_and_reports_total_before_pagination(client):
    first = client.get("/api/scholarships", params={"page": 1, "page_size": 1}).json()
    second = client.get("/api/scholarships", params={"page": 2, "page_size": 1}).json()
    beyond = client.get("/api/scholarships", params={"page": 4, "page_size": 1}).json()
    assert [item["id"] for item in first["items"]] == [1]
    assert [item["id"] for item in second["items"]] == [2]
    assert beyond == {"items": [], "total": 3, "page": 4, "page_size": 1}
    assert first["total"] == second["total"] == 3


def test_new_database_returns_empty_list_without_seeding(tmp_path):
    with TestClient(create_app(tmp_path / "empty.sqlite3")) as client:
        response = client.get("/api/scholarships")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


@pytest.mark.parametrize(
    "query",
    [
        {"page": 0},
        {"page": -1},
        {"page": "abc"},
        {"page": 1.5},
        {"page": 1_000_001},
        {"page_size": 0},
        {"page_size": 101},
        {"page_size": "abc"},
        {"country": ""},
        {"country": "   "},
        {"country": "x" * 101},
        {"field": ""},
        {"field": "   "},
        {"field": "x" * 101},
        {"funding_type": "free"},
        {"funding_type": "FULLY_FUNDED"},
        {"unknown_filter": "value"},
    ],
)
def test_invalid_query_parameters_return_422(client, query):
    response = client.get("/api/scholarships", params=query)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_detail_contains_sources_dates_and_requirement_values(client):
    response = client.get("/api/scholarships/1")
    assert response.status_code == 200
    data = response.json()
    assert data["scholarship_name"] == "Fictional Demo Engineering Award"
    assert data["destination_country"] == ["Germany", "Finland"]
    assert data["minimum_gpa"] == 3.0
    assert data["gpa_scale"] == 4.0
    assert data["minimum_ielts"] == 6.5
    assert data["last_verified_at"] == "2026-01-01"
    assert data["application_deadline"] == "2027-01-01"
    assert data["official_source_url"] == "https://example.org/fictional-engineering"


def test_detail_does_not_interpret_missing_requirements_as_unrestricted(client):
    data = client.get("/api/scholarships/3").json()
    for name in (
        "minimum_gpa",
        "gpa_scale",
        "minimum_ielts",
        "eligible_nationalities",
        "eligible_study_fields",
        "destination_country",
        "application_deadline",
        "additional_requirements",
        "tuition_coverage",
        "living_stipend",
    ):
        assert name in data and data[name] is None
    assert data["funding_type"] == "unknown"


def test_missing_scholarship_returns_standard_404(client):
    response = client.get("/api/scholarships/999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Scholarship not found"}


@pytest.mark.parametrize("identifier", ["0", "-1", "abc", "1.5", str(2**63)])
def test_invalid_scholarship_identifiers_return_422(client, identifier):
    response = client.get(f"/api/scholarships/{identifier}")
    assert response.status_code == 422


def test_read_endpoints_do_not_allow_writes(client):
    assert client.post("/api/scholarships", json={}).status_code == 405
    assert client.delete("/api/scholarships/1").status_code == 405
