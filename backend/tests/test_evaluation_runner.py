"""Evaluation checkpoints and measured-output boundaries stay reproducible."""

import hashlib
import json

import pytest

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
