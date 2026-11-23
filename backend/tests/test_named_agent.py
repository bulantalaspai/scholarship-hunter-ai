"""Named retrieval keeps scope and repairs bounded model responses."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.agent import run_agent
from backend.app.agent_api import get_ollama_client
from backend.app.agent_schemas import AgentRequest
from backend.app.agent_tools import AgentTools
from backend.app.eligibility_api import evaluation_date
from backend.app.import_catalogue import import_catalogue, load_catalogue
from backend.app.main import create_app
from backend.app.ollama_client import OllamaReply
from backend.tests.test_agent import ScriptedModel, calls

TODAY = date(2026, 11, 12)


@pytest.fixture
def request_data():
    return AgentRequest(
        profile={
            "nationality": "Kazakhstan",
            "degree_level": "bachelor",
            "degree_completed": True,
            "field_of_study": "Computer Science",
            "gpa": 3.5,
            "gpa_scale": 4.0,
            "ielts_overall": 7.0,
            "intended_start_year": 2027,
            "funding_preference": "fully_funded",
        }
    )


@pytest.fixture
def production_tools(engine, request_data):
    import_catalogue(
        engine,
        load_catalogue(Path(__file__).parents[1] / "data/curated_scholarships.json"),
    )
    with Session(engine) as session:
        yield AgentTools(session, request_data.profile, TODAY)


def test_named_filters_cannot_exclude_requested_partial_award(production_tools):
    production_tools.prepare("Assess DAAD Master Studies for my profile")
    data, event = production_tools.dispatch(
        "search_scholarships",
        {
            "country": "Japan",
            "field": "Computer Science",
            "funding_type": "fully_funded",
        },
        step=1,
        timeout=1,
    )
    assert event.status == "ok"
    assert [item["id"] for item in data["candidates"]] == [1]
    assert data["filters_ignored"] == ["country", "field", "funding_type"]
    assert data["filter_notice"]
    result, event = production_tools.dispatch(
        "check_eligibility", {"scholarship_id": 1}, step=2, timeout=1
    )
    assert event.status == "ok" and result["status"] == "ineligible"
    assert "funding_preference" in result["failed"]


def test_alias_search_discovers_real_target_without_overrestrictive_filters(
    production_tools,
):
    production_tools.prepare("Find scholarships")
    data, event = production_tools.dispatch(
        "search_scholarships",
        {"programme_name": "SMACCs", "country": "NoSuchCountry"},
        step=1,
        timeout=1,
    )
    assert event.status == "ok" and data["name_resolution"]["method"] == "alias"
    assert [item["id"] for item in data["candidates"]] == [2]
    assert data["filters_ignored"] == ["country"]
    assert production_tools.assessed == {}


def test_ambiguous_tool_name_returns_choices_without_authorizing_them(production_tools):
    production_tools.prepare("Find scholarships")
    before = set(production_tools.discovered)
    data, event = production_tools.dispatch(
        "search_scholarships", {"programme_name": "DAAD"}, step=1, timeout=1
    )
    assert event.status == "ok" and data["candidates"] == []
    assert data["name_resolution"]["status"] == "ambiguous"
    assert len(data["name_resolution"]["options"]) == 2
    assert set(production_tools.discovered) == before
    assert production_tools.assessed == {}


def test_name_lookup_cannot_replace_an_explicit_target(production_tools):
    production_tools.prepare("Assess MEXT for my profile")
    data, event = production_tools.dispatch(
        "search_scholarships", {"programme_name": "SMACCs"}, step=1, timeout=1
    )
    assert event.status == "blocked" and data["target_ids"] == [20]
    assert event.arguments == {}
    assert set(production_tools.discovered) == {20}


def test_explicit_user_target_disambiguates_a_broader_model_alias(production_tools):
    production_tools.prepare("Assess DAAD Master Studies for my profile")
    data, event = production_tools.dispatch(
        "search_scholarships", {"programme_name": "DAAD"}, step=1, timeout=1
    )
    assert event.status == "ok" and data["target_ids"] == [1]
    assert [item["id"] for item in data["candidates"]] == [1]
    assert data["name_resolution"]["status"] == "matched"


def test_named_search_argument_is_scoped_without_mutating_shared_tools(
    production_tools,
):
    production_tools.prepare("Find scholarships for my profile")
    general = production_tools.definitions()
    assert "programme_name" not in general[0]["function"]["parameters"]["properties"]
    production_tools.prepare("Assess MEXT for my profile")
    named = production_tools.definitions()
    assert "programme_name" in named[0]["function"]["parameters"]["properties"]
    assert "programme_name" not in general[0]["function"]["parameters"]["properties"]
    assert len(named) == len(general) == 4


@pytest.mark.parametrize(
    ("goal", "status", "resolution_status"),
    [
        ("Assess DAAD for my profile", "ambiguous_match", "ambiguous"),
        (
            "Assess Fictional Missing Programme for my profile",
            "no_matches",
            "not_found",
        ),
    ],
)
def test_unresolved_name_never_starts_inference_or_broad_fallback(
    production_tools, request_data, goal, status, resolution_status
):
    request_data.goal = goal
    model = Mock()
    result = run_agent(request_data, production_tools, model, today=TODAY)
    assert (
        result.status == status and result.name_resolution.status == resolution_status
    )
    assert (
        result.recommendations
        == result.discovery_candidates
        == result.fallback_recommendations
        == []
    )
    assert result.steps == result.tool_calls == 0
    model.chat.assert_not_called()


def test_specific_explanation_length_feedback_repairs_model_without_relaxing_limit(
    production_tools, request_data
):
    request_data.goal = "Assess MEXT for my profile"
    wrong = {
        "recommendation_ids": [20],
        "explanations": [
            {
                "scholarship_id": 20,
                "requirements": [
                    "deadline",
                    "rule_evidence",
                    "prior_degree",
                    "study_field",
                    "gpa",
                ],
            }
        ],
    }
    repaired = {
        "recommendation_ids": [20],
        "explanations": [
            {"scholarship_id": 20, "requirements": ["deadline", "rule_evidence"]}
        ],
    }
    model = ScriptedModel(
        calls(("check_eligibility", {"scholarship_id": 20})),
        OllamaReply(
            model="qwen3:4b-instruct",
            done=True,
            done_reason="stop",
            prompt_eval_count=1000,
            message={"content": json.dumps(wrong)},
        ),
        OllamaReply(
            model="qwen3:4b-instruct",
            done=True,
            done_reason="stop",
            prompt_eval_count=1000,
            message={"content": json.dumps(repaired)},
        ),
    )
    result = run_agent(request_data, production_tools, model, today=TODAY)
    assert result.steps == 3 and result.tool_calls == 1
    assert result.recommendations[0].assessment.status == "ineligible"
    feedback = [
        json.loads(item["content"])
        for item in model.requests[-1][0]
        if item["role"] == "user" and '"invalid_final_selection"' in item["content"]
    ][0]
    assert feedback["issues"] == [
        {
            "type": "too_long",
            "path": ["explanations", 0, "requirements"],
            "max_length": 4,
        }
    ]
    assert "4 unique" in feedback["instruction"]
    assert len(result.model_explanations[0].requirements) == 2


def test_endpoint_exposes_source_backed_ambiguity_choices(
    production_tools, request_data
):
    app = create_app(production_tools.session.bind.url.database)
    app.dependency_overrides[evaluation_date] = lambda: TODAY
    model = Mock()
    app.dependency_overrides[get_ollama_client] = lambda: model
    request_data.goal = "Assess DAAD for my profile"
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/recommend", json=request_data.model_dump(mode="json")
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ambiguous_match" and data["tool_calls"] == 0
        assert {
            item["scholarship_id"] for item in data["name_resolution"]["options"]
        } == {1, 18}
        assert all(
            item["official_source_url"].startswith("https://")
            and item["last_verified_at"]
            for item in data["name_resolution"]["options"]
        )
        assert client.get("/api/health").json()["status"] == "ok"
    model.chat.assert_not_called()


@pytest.mark.parametrize("extra_field", [False, True])
def test_schema_feedback_repairs_relationship_and_extra_field_errors(
    production_tools, request_data, extra_field
):
    request_data.goal = "Assess MEXT for my profile"
    explanation = {"scholarship_id": 20, "requirements": ["deadline"]}
    invalid = {"recommendation_ids": [], "explanations": [explanation]}
    if extra_field:
        invalid["recommendation_ids"] = [20]
        explanation["untrusted_extra"] = "discard this model-written claim"
    repaired = {
        "recommendation_ids": [20],
        "explanations": [{"scholarship_id": 20, "requirements": ["deadline"]}],
    }
    metadata = {
        "model": "qwen3:4b-instruct",
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 1000,
    }
    model = ScriptedModel(
        calls(("check_eligibility", {"scholarship_id": 20})),
        OllamaReply(**metadata, message={"content": json.dumps(invalid)}),
        OllamaReply(**metadata, message={"content": json.dumps(repaired)}),
    )
    result = run_agent(request_data, production_tools, model, today=TODAY)
    assert result.steps == 3
    assert result.recommendations[0].assessment.status == "ineligible"
    feedback = next(
        json.loads(message["content"])
        for message in model.requests[-1][0]
        if '"invalid_final_selection"' in message["content"]
    )
    assert "has only scholarship_id" in feedback["instruction"]
    assert "Its ID must be selected" in feedback["instruction"]
    if extra_field:
        assert feedback["issues"][0]["path"][-1] == "<extra>"
    else:
        assert feedback["issues"][0]["reason"] == (
            "Explanations must refer to selected IDs"
        )
    assert "untrusted_extra" not in json.dumps(feedback)
    assert "discard this model-written claim" not in result.model_dump_json()
