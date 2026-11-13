"""Evaluation checkpoints and measured-output boundaries stay reproducible."""

import hashlib
import json
from datetime import date
from unittest.mock import Mock

import pytest

from backend.app.agent_tools import AgentTools
from backend.app.eligibility_schemas import StudentProfile
from backend.app.ollama_client import OllamaClient, OllamaReply
from backend.evaluation import run


def test_offline_run_executes_baseline_and_marks_unrun_model_metrics(
    tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline evaluation must not contact Ollama")

    monkeypatch.setattr(run, "local_metadata", forbidden)
    monkeypatch.setattr(run, "agent_run", forbidden)
    output = tmp_path / "result.json"
    result = run.evaluate(output, real_model=False, resume=False)
    assert len(result["baseline"]) == 20
    assert result["agent"] == result["agent_cases"] == result["extraction"] == []
    assert result["metrics"]["baseline_classification"]["gold_cases"] == 30
    assert (
        result["metrics"]["baseline_classification"]["target_status"] == "NOT_EVALUABLE"
    )
    assert result["metrics"]["agent_operational"]["status"] == "NOT_EVALUABLE"
    assert result["metrics"]["extraction_probe"]["status"] == "NOT_EVALUABLE"
    assert json.loads(output.read_text(encoding="utf-8")) == result
    resumed = run.evaluate(output, real_model=False, resume=True)
    assert resumed["baseline"] == result["baseline"]
    result["signature"]["inputs"]["changed"] = "mismatch"
    run.write_checkpoint(output, result)
    with pytest.raises(ValueError, match="differ"):
        run.evaluate(output, real_model=False, resume=True)


def test_hashes_normalize_windows_newlines_and_bom(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "ROOT", tmp_path)
    path = tmp_path / "input.json"
    path.write_bytes(b"\xef\xbb\xbf{}\r\n")
    assert run.file_hashes([path]) == {
        "input.json": hashlib.sha256(b"{}\n").hexdigest()
    }


def test_operational_metrics_separate_failure_abstention_and_tool_success():
    runs = [
        {
            "seconds": 1,
            "status": "limit_reached",
            "error": None,
            "recommendations": [],
            "fallback_recommendations": [{"status": "needs_verification"}],
            "trace": [{"status": "ok"}, {"status": "blocked"}],
        },
        {
            "seconds": 3,
            "status": "error",
            "error": "OllamaUnavailable",
            "recommendations": [],
            "fallback_recommendations": [],
            "trace": [],
        },
    ]
    raw = run.operational_metrics(runs)
    assert raw["failures"] == 1 and raw["budget_stops"] == 1
    assert raw["abstention_rate"] == 1 and raw["recommendation_coverage"] == 0
    assert raw["tool_calls"] == 2 and raw["tool_success_rate"] == 0.5
    assert raw["median_latency_seconds"] == 2 and raw["p95_latency_seconds"] == 3
    assert (
        run.operational_metrics(runs, fallback=True)["recommendation_coverage"] == 0.5
    )
    assert run.operational_metrics([])["tool_success_rate"] is None


def test_citation_facts_come_from_emitted_rank_reasons():
    runs = [
        {
            "recommendations": [
                {
                    "scholarship_name": "Fictional test only",
                    "source_url": "https://example.org/fictional",
                    "ranking_reasons": [
                        "Published funding: partially_funded; award not guaranteed."
                    ],
                }
            ]
        }
    ]
    facts = run.output_facts(runs)
    assert [item["value"] for item in facts] == [
        "Fictional test only",
        "partially_funded",
    ]


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        ({"recommendation_ids": [3]}, "unassessed_ids"),
        ({"recommendation_ids": [2]}, "outside_named_target"),
        (
            {
                "recommendation_ids": [1],
                "explanations": [
                    {"scholarship_id": 1, "requirements": ["unrecognized_key"]}
                ],
            },
            "invalid_explanation_reference",
        ),
        (
            {
                "recommendation_ids": [1],
                "explanations": [
                    {"scholarship_id": 1, "requirements": ["rule_evidence"]}
                ],
            },
            "grounded",
        ),
        ({"recommendation_ids": [1], "status": "eligible"}, "invalid_schema"),
        ({"recommendation_ids": []}, "grounded"),
    ],
)
def test_observer_uses_actual_final_validation_without_mutation_or_queries(
    session, monkeypatch, selection, expected
):
    profile = StudentProfile(
        nationality="Kazakhstan",
        degree_level="bachelor",
        degree_completed=True,
        field_of_study="Computer Science",
        gpa=3.5,
        gpa_scale=4.0,
        ielts_overall=7.0,
        intended_start_year=2027,
        funding_preference="any_funding",
    )
    tools = AgentTools(session, profile, date(2026, 1, 2))
    tools.prepare("Assess Fictional Demo Engineering Award")
    tools.dispatch("search_scholarships", {}, step=1, timeout=1)
    tools.dispatch("rank_scholarships", {"scholarship_ids": [1, 2]}, step=1, timeout=1)
    assessed = dict(tools.assessed)
    discovered = dict(tools.discovered)
    reply = OllamaReply(
        model="qwen3:4b-instruct",
        done=True,
        done_reason="stop",
        prompt_eval_count=100,
        message={"content": json.dumps(selection)},
    )
    chat = Mock(return_value=reply)
    monkeypatch.setattr(OllamaClient, "chat", chat)
    execute = Mock(side_effect=AssertionError("Observer must use cached assessments"))
    get = Mock(side_effect=AssertionError("Observer must use cached assessments"))
    monkeypatch.setattr(session, "execute", execute)
    monkeypatch.setattr(session, "get", get)
    observer = run.ObservedClient(tools)
    assert observer.chat([], [], timeout=1) is reply
    event = observer.rounds[0]
    assert event["final_validation"] == expected
    if expected != "invalid_schema":
        assert event["final_ids"] == selection["recommendation_ids"]
        assert event["final_explanation_keys"] == selection.get("explanations", [])
    else:
        assert "final_ids" not in event and "final_explanation_keys" not in event
    assert tools.assessed == assessed and tools.discovered == discovered
    assert all(tools.assessed[key] is item for key, item in assessed.items())
    execute.assert_not_called()
    get.assert_not_called()
    chat.assert_called_once()
