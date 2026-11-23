"""Test request scoping on the source-backed catalogue with scripted replies."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.agent import busy_response, run_agent
from backend.app.agent_api import get_ollama_client
from backend.app.agent_schemas import AgentRequest
from backend.app.agent_tools import AgentTools
from backend.app.eligibility_api import evaluation_date
from backend.app.import_catalogue import import_catalogue, load_catalogue
from backend.app.main import create_app
from backend.app.ollama_client import OllamaTimeout
from backend.tests.test_agent import ScriptedModel, calls, final

TODAY = date(2026, 11, 23)
PROFILE = {
    "nationality": "Kazakhstan",
    "degree_level": "bachelor",
    "degree_completed": True,
    "field_of_study": "Computer Science",
    "gpa": 3.5,
    "gpa_scale": 4,
    "ielts_overall": 7,
    "intended_start_year": 2027,
    "funding_preference": "any_funding",
}


@pytest.fixture
def reviewed_engine(engine):
    source = Path(__file__).parents[1] / "data" / "curated_scholarships.json"
    import_catalogue(engine, load_catalogue(source))
    return engine


def request_for(destination):
    return AgentRequest(
        profile=PROFILE,
        goal=f"Find master's scholarships in {destination} for a student from "
        "Kazakhstan, including partial funding options.",
    )


def ids(results):
    return [item.assessment.scholarship_id for item in results]


@pytest.mark.parametrize(
    ("destination", "checked_id", "excluded_id"),
    [("Germany", 18, 2), ("Japan", 15, 2), ("Europe", 18, 20)],
)
def test_same_profile_uses_verified_request_scope(
    reviewed_engine, destination, checked_id, excluded_id
):
    request = request_for(destination)
    model = ScriptedModel(
        calls(("search_scholarships", {"country": destination})),
        calls(("rank_scholarships", {"scholarship_ids": [checked_id]})),
        final([checked_id]),
    )
    with Session(reviewed_engine) as session:
        tools = AgentTools(session, request.profile, TODAY)
        result = run_agent(request, tools, model, today=TODAY)
        assert (
            tools.assessed[checked_id].assessment
            == result.recommendations[0].assessment
        )
    assert ids(result.recommendations) == [checked_id]
    assert result.recommendations[0].assessment.status == "needs_verification"
    assert excluded_id not in result.discovery_candidate_ids
    assert result.fallback_recommendations == []
    search_result = next(
        json.loads(item["content"])
        for item in model.requests[1][0]
        if item["role"] == "tool"
    )
    assert search_result["request_scoped"] is True
    assert search_result["candidates"][0]["fit"]["funding"] == "confirmed"
    checks = {item.scholarship_id: item.checks for item in result.request_matches}
    assert set(checks) == {checked_id, *ids(result.discovery_candidates)}
    assert all(items[0].status == "confirmed" for items in checks.values())
    assert checks[checked_id][0].label == destination
    assert checks[checked_id][1].status == "confirmed"


def test_model_cannot_widen_request_scope_on_a_miss(reviewed_engine):
    request = request_for("Japan")
    model = ScriptedModel(
        calls(("search_scholarships", {"country": "Germany"})),
        calls(("rank_scholarships", {"scholarship_ids": [2, 18]})),
        final([2]),
        final([]),
    )
    with Session(reviewed_engine) as session:
        result = run_agent(
            request, AgentTools(session, request.profile, TODAY), model, today=TODAY
        )
    assert result.status == "no_matches" and result.recommendations == []
    assert result.tool_trace[0].summary == "Found 0 records; returned 0 candidates."
    assert result.tool_trace[1].status == "blocked"
    assert any("grounding validation" in warning for warning in result.warnings)
    assert ids(result.fallback_recommendations) == ids(result.discovery_candidates)
    assert ids(result.fallback_recommendations)[0] == 15
    assert {2, 18}.isdisjoint(result.discovery_candidate_ids)


def test_required_funding_limits_outage_and_busy_results(reviewed_engine):
    request = AgentRequest(
        profile=PROFILE,
        goal="Find only partially funded master's scholarships in Germany.",
    )
    with Session(reviewed_engine) as session:
        result = run_agent(
            request,
            AgentTools(session, request.profile, TODAY),
            ScriptedModel(OllamaTimeout()),
            today=TODAY,
        )
        busy = busy_response(
            request, AgentTools(session, request.profile, TODAY), TODAY
        )
    assert result.model_error == "timeout" and busy.model_error == "busy"
    for response in (result, busy):
        assert set(response.discovery_candidate_ids) == {1, 18}
        assert set(ids(response.fallback_recommendations)) == {1, 18}
        assert all(
            check.mode == "required" and check.status == "confirmed"
            for match in response.request_matches
            for check in match.checks
        )


def test_no_verified_destination_returns_no_match_without_model(reviewed_engine):
    request = request_for("Canada")
    model = Mock()
    with TestClient(create_app(reviewed_engine.url.database)) as client:
        client.app.dependency_overrides[evaluation_date] = lambda: TODAY
        client.app.dependency_overrides[get_ollama_client] = lambda: model
        response = client.post(
            "/api/agent/recommend", json=request.model_dump(mode="json")
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "no_matches"
    assert data["discovery_candidate_ids"] == data["fallback_recommendations"] == []
    assert data["recommendations"] == data["request_matches"] == []
    assert data["request_preferences"][0] == {
        "kind": "destination",
        "label": "Canada",
        "mode": "required",
    }
    assert "Canada" in data["message"]
    model.chat.assert_not_called()


def test_soft_preference_reports_a_nonmatch_for_explicit_named_target(reviewed_engine):
    request = AgentRequest(
        profile=PROFILE, goal="Assess SMACCs for my profile. Prefer partial funding."
    )
    model = ScriptedModel(
        calls(("check_eligibility", {"scholarship_id": 2})), final([2])
    )
    with Session(reviewed_engine) as session:
        result = run_agent(
            request, AgentTools(session, request.profile, TODAY), model, today=TODAY
        )
    assert ids(result.recommendations) == result.discovery_candidate_ids == [2]
    assert result.discovery_scope == "named_target"
    check = result.request_matches[0].checks[0]
    assert (check.mode, check.status) == ("preferred", "unmatched")
    assert "fully funded" in check.evidence.lower()


def test_request_preference_does_not_override_profile_assessment(reviewed_engine):
    request = AgentRequest(
        profile={**PROFILE, "funding_preference": "fully_funded"},
        goal=request_for("Germany").goal,
    )
    with Session(reviewed_engine) as session:
        result = busy_response(
            request, AgentTools(session, request.profile, TODAY), TODAY
        )
    assert {1, 18}.isdisjoint(result.discovery_candidate_ids)
    assert result.discovery_candidates
    assert any(
        check.kind == "funding" and check.status == "unmatched"
        for item in result.request_matches
        for check in item.checks
    )


def test_scoped_last_step_reserves_context_for_final_selection(reviewed_engine):
    request = request_for("Germany")
    model = ScriptedModel(
        calls(("rank_scholarships", {"scholarship_ids": [18, 1, 6]})),
        calls(("check_eligibility", {"scholarship_id": 18})),
        calls(("check_eligibility", {"scholarship_id": 1})),
        final([18, 1]),
    )
    with Session(reviewed_engine) as session:
        result = run_agent(
            request, AgentTools(session, request.profile, TODAY), model, today=TODAY
        )
    assert result.steps == 4 and result.tool_calls == 3
    assert all(len(request_tools) == 4 for _, request_tools, _ in model.requests[:3])
    assert model.requests[-1][1] == []
    assert ids(result.recommendations) == [18, 1]
