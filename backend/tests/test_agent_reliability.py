"""Scripted model choices exercise real dispatch, repair and fallback boundaries."""

import json
from datetime import date
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from backend.app import agent as agent_module
from backend.app.agent import run_agent
from backend.app.agent_schemas import AgentRequest
from backend.app.agent_tools import AgentTools
from backend.app.eligibility_schemas import FundingPreference
from backend.app.import_catalogue import import_catalogue
from backend.app.ollama_client import OllamaReply, OllamaTimeout
from backend.app.schemas import CatalogueImport

TODAY = date(2026, 1, 2)


def reply(*calls, selection=None, content=""):
    return OllamaReply(
        model="qwen3:4b-instruct",
        done=True,
        done_reason="stop",
        prompt_eval_count=1000,
        message={
            "content": json.dumps({"recommendation_ids": selection})
            if selection is not None
            else content,
            "tool_calls": [
                {"function": {"name": name, "arguments": arguments}}
                for name, arguments in calls
            ],
        },
    )


class Model:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.requests = []

    def chat(self, messages, tools, *, timeout):
        self.requests.append((json.loads(json.dumps(messages)), tools, timeout))
        return next(self.replies)


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
            "funding_preference": "any_funding",
        }
    )


@pytest.fixture
def tools(engine, catalogue, request_data):
    import_catalogue(engine, catalogue, allow_demo=True)
    with Session(engine) as session:
        yield AgentTools(session, request_data.profile, TODAY)


def test_empty_model_selection_exposes_separate_deterministic_fallback(
    tools, request_data
):
    result = run_agent(
        request_data,
        tools,
        Model(reply(("search_scholarships", {})), reply(selection=[])),
        today=TODAY,
    )
    assert result.status == "no_matches" and result.recommendations == []
    assert result.steps == 2 and result.tool_calls == 1
    assert result.fallback_reason
    assert [
        item.assessment.scholarship_id for item in result.fallback_recommendations
    ] == [
        1,
        2,
        3,
    ]
    assert all(
        item.assessment.status == "needs_verification"
        and item.assessment.unknown_requirements
        for item in result.fallback_recommendations
    )
    assert tools.assessed == {}
    assert [event.name for event in result.tool_trace] == ["search_scholarships"]


def test_fallback_preserves_sources_dates_and_explanations_without_authorizing_ids(
    tools,
):
    tools.dispatch("search_scholarships", {}, step=1, timeout=1)
    fallback = tools.fallback_recommendations()
    for item in fallback:
        original = tools.discovered[item.assessment.scholarship_id]
        assert item.assessment.official_source_url == original.official_source_url
        assert item.assessment.last_verified_at == original.last_verified_at
        assert item.assessment.rules_verified_at is None
        assert item.assessment.evaluated_on == TODAY
        assert item.assessment.explanation and item.ranking_reasons
    assert tools.assessed == {}
    with pytest.raises(ValueError, match="validated tool assessment"):
        tools.final_recommendations([1])


def test_fallback_reassesses_without_replacing_existing_model_assessments(tools):
    tools.dispatch("search_scholarships", {}, step=1, timeout=1)
    tools.dispatch("check_eligibility", {"scholarship_id": 1}, step=2, timeout=1)
    before = dict(tools.assessed)
    fallback = tools.fallback_recommendations()
    assert fallback and tools.assessed == before
    assert set(tools.assessed) == {1}
    assert tools.assessed[1] is before[1]
    with pytest.raises(ValueError):
        tools.final_recommendations([2])


def test_fallback_contains_only_candidates_from_actual_model_search(
    tools, request_data
):
    result = run_agent(
        request_data,
        tools,
        Model(
            reply(("search_scholarships", {"country": "France"})), reply(selection=[])
        ),
        today=TODAY,
    )
    assert list(tools.discovered) == [2]
    assert [
        item.assessment.scholarship_id for item in result.fallback_recommendations
    ] == [2]


def test_confirmed_funding_failure_is_excluded_without_promoting_unknowns(
    tools, request_data
):
    request_data.profile.funding_preference = FundingPreference.FULLY_FUNDED
    tools = AgentTools(tools.session, request_data.profile, TODAY)
    result = run_agent(
        request_data,
        tools,
        Model(reply(("search_scholarships", {})), reply(selection=[])),
        today=TODAY,
    )
    assert [
        item.assessment.scholarship_id for item in result.fallback_recommendations
    ] == [
        1,
        3,
    ]
    failure = tools._rank([2], record_assessment=False)[0].assessment
    assert failure.status == "ineligible"
    assert "funding_preference" in failure.failed_requirements
    assert all(
        item.assessment.status == "needs_verification"
        for item in result.fallback_recommendations
    )
    assert tools.assessed == {}


@pytest.mark.parametrize("search", [None, {"country": "NoSuchDestination"}])
def test_no_candidates_produce_no_fallback(tools, request_data, search):
    replies = [reply(selection=[])]
    if search is not None:
        replies.insert(0, reply(("search_scholarships", search)))
    result = run_agent(request_data, tools, Model(*replies), today=TODAY)
    assert result.recommendations == result.fallback_recommendations == []
    assert result.fallback_reason is None


def test_all_confirmed_failures_produce_no_fallback(tools, request_data):
    request_data.profile.intended_start_year = 2025
    tools = AgentTools(tools.session, request_data.profile, TODAY)
    result = run_agent(
        request_data,
        tools,
        Model(reply(("search_scholarships", {})), reply(selection=[])),
        today=TODAY,
    )
    assert result.fallback_recommendations == [] and result.fallback_reason is None
    assert all(
        item.assessment.status == "ineligible"
        for item in tools._rank(list(tools.discovered), record_assessment=False)
    )


def test_valid_model_selection_never_invokes_fallback(tools, request_data):
    fallback = Mock(wraps=tools.fallback_recommendations)
    tools.fallback_recommendations = fallback
    result = run_agent(
        request_data,
        tools,
        Model(
            reply(("search_scholarships", {"country": "Germany"})),
            reply(("check_eligibility", {"scholarship_id": 1})),
            reply(selection=[1]),
        ),
        today=TODAY,
    )
    assert result.recommendations[0].assessment.scholarship_id == 1
    assert result.fallback_recommendations == [] and result.fallback_reason is None
    fallback.assert_not_called()


def test_assessment_feedback_repairs_selection_within_four_model_steps(
    tools, request_data
):
    model = Model(
        reply(("search_scholarships", {})),
        reply(selection=[1]),
        reply(("check_eligibility", {"scholarship_id": 1})),
        reply(selection=[1]),
    )
    result = run_agent(request_data, tools, model, today=TODAY)
    assert result.steps == 4 and result.tool_calls == 2
    assert result.recommendations[0].assessment.scholarship_id == 1
    assert result.fallback_recommendations == []
    feedback = next(
        json.loads(message["content"])
        for message in model.requests[2][0]
        if message["role"] == "user"
        and '"error": "assessment_required"' in message["content"]
    )
    assert feedback["discovered_ids"] == [1, 2, 3]
    assert "rank_scholarships" in feedback["instruction"]
    assert "check_eligibility" in feedback["instruction"]
    assert any(
        "3 model steps remain" in message["content"] for message in model.requests[1][0]
    )
    assert any(
        "1 model steps remain" in message["content"]
        and "Assessed IDs: [1]" in message["content"]
        for message in model.requests[3][0]
    )
    assert [event.name for event in result.tool_trace] == [
        "search_scholarships",
        "check_eligibility",
    ]


def test_fallback_does_not_execute_or_report_a_ninth_tool(tools, request_data):
    dispatch = Mock(wraps=tools.dispatch)
    tools.dispatch = dispatch
    model = Model(reply(("search_scholarships", {}), *[("unknown_tool", {})] * 8))
    result = run_agent(request_data, tools, model, today=TODAY)
    assert result.status == "limit_reached"
    assert result.steps == 1 and result.tool_calls == dispatch.call_count == 8
    assert result.recommendations == [] and result.fallback_recommendations
    assert tools.assessed == {}
    assert len(model.requests) == 1
    assert [event.name for event in result.tool_trace].count("search_scholarships") == 1


def test_context_stop_can_offer_fallback_without_more_inference(
    tools, request_data, monkeypatch
):
    monkeypatch.setattr(
        agent_module,
        "estimated_input_tokens",
        lambda messages, _tools: 100 if len(messages) == 2 else 4000,
    )
    model = Model(reply(("search_scholarships", {})))
    result = run_agent(request_data, tools, model, today=TODAY)
    assert result.status == "limit_reached"
    assert result.steps == result.tool_calls == len(model.requests) == 1
    assert result.recommendations == [] and result.fallback_recommendations
    assert tools.assessed == {}


def test_fallback_cannot_extend_the_total_request_deadline(
    tools, request_data, monkeypatch
):
    clock = [0.0]
    monkeypatch.setattr(agent_module.time, "monotonic", lambda: clock[0])
    original = tools.fallback_recommendations

    def slow_fallback():
        result = original()
        clock[0] = agent_module.AGENT_TIMEOUT_SECONDS + 1
        return result

    monkeypatch.setattr(tools, "fallback_recommendations", slow_fallback)
    model = Model(reply(("search_scholarships", {})), reply(selection=[]))
    with pytest.raises(OllamaTimeout):
        run_agent(request_data, tools, model, today=TODAY)


def test_reviewed_eligible_fixture_is_never_relabelled_as_an_unverified_fallback(
    engine, catalogue, request_data
):
    values = catalogue.model_dump(mode="json")
    values["scholarships"][0]["eligibility_rules"] = {
        "source_urls": ["https://example.org/fictional-engineering"],
        "verified_at": TODAY.isoformat(),
        "nationality_scope": "listed_only",
        "field_scope": "listed_only",
        "accepted_prior_degrees": ["bachelor"],
        "gpa_requirement": "minimum",
        "language_requirement": "ielts_only",
        "intake_year": 2027,
        "call_open": True,
        "funding_available": True,
        "no_additional_admission_requirements": True,
        "no_additional_funding_requirements": True,
    }
    import_catalogue(engine, CatalogueImport.model_validate(values), allow_demo=True)
    with Session(engine) as session:
        tools = AgentTools(session, request_data.profile, TODAY)
        tools.dispatch("search_scholarships", {}, step=1, timeout=1)
        assert (
            tools._rank([1], record_assessment=False)[0].assessment.status == "eligible"
        )
        fallback = tools.fallback_recommendations()
        assert [item.assessment.scholarship_id for item in fallback] == [2, 3]
        assert tools.assessed == {}
