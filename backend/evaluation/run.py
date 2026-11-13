"""Reproduce the fixed-date evaluation with synthetic inputs and local inference.

python -m backend.evaluation.run --real-model --output evaluation/results/local.json
Use --resume to continue a checkpoint with identical data and implementation.
"""

import argparse
import hashlib
import http.client
import json
import math
import platform
import statistics
import subprocess
import time
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agent import estimated_input_tokens, run_agent
from backend.app.agent_schemas import MODEL, AgentRequest, FinalSelection
from backend.app.agent_tools import AgentTools
from backend.app.database import create_database_engine, initialize_database
from backend.app.eligibility_api import match_profile
from backend.app.eligibility_schemas import MatchRequest, RankedProgramme
from backend.app.import_catalogue import import_catalogue, load_catalogue
from backend.app.models import Scholarship
from backend.app.ollama_client import (
    OllamaClient,
    OllamaProtocolError,
    OllamaTimeout,
    OllamaUnavailable,
)
from backend.app.schemas import ScholarshipRead
from backend.evaluation.extract import run_extraction_example
from backend.evaluation.metrics import (
    citation_metrics,
    classification_metrics,
    extraction_metrics,
    precision_at_3,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "evaluation" / "data"
CATALOGUE = ROOT / "backend" / "data" / "curated_scholarships.json"
INPUT_FILES = [CATALOGUE, *sorted(DATA.glob("*.json"))]
IMPLEMENTATION_FILES = sorted((ROOT / "backend" / "app").glob("*.py")) + [
    Path(__file__),
    Path(__file__).with_name("extract.py"),
    Path(__file__).with_name("metrics.py"),
    Path(__file__).with_name("reliability.py"),
]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_hashes(paths: list[Path]) -> dict:
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(
            path.read_text(encoding="utf-8-sig").encode("utf-8")
        ).hexdigest()
        for path in paths
    }


def write_checkpoint(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def local_metadata() -> dict:
    result = {}
    for key, endpoint in (("version", "/api/version"), ("tags", "/api/tags")):
        connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=3)
        try:
            connection.request("GET", endpoint)
            response = connection.getresponse()
            body = response.read(65_537)
            if response.status != 200 or len(body) > 65_536:
                raise ValueError("Invalid local metadata")
            result[key] = json.loads(body)
        except OSError, ValueError, http.client.HTTPException:
            result[key] = None
        finally:
            connection.close()
    return result


class ObservedTools(AgentTools):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executions = []

    def dispatch(self, *args, **kwargs):
        data, event = super().dispatch(*args, **kwargs)
        self.executions.append(event.model_dump(mode="json"))
        return data, event


class ObservedClient(OllamaClient):
    def __init__(self, agent_tools: AgentTools):
        self.agent_tools = agent_tools
        self.rounds = []

    def chat(self, messages, tools, *, timeout):
        started = time.perf_counter()
        event = {
            "estimated_input_tokens": estimated_input_tokens(messages, tools),
            "prompt_tokens": None,
            "requested_tools": [],
            "final_validation": None,
        }
        self.rounds.append(event)
        try:
            reply = super().chat(messages, tools, timeout=timeout)
            event["prompt_tokens"] = reply.prompt_eval_count
            event["requested_tools"] = [
                call.function.name for call in reply.message.tool_calls
            ]
            if not reply.message.tool_calls:
                try:
                    final = FinalSelection.model_validate_json(reply.message.content)
                except ValidationError:
                    event["final_validation"] = "invalid_schema"
                else:
                    event["final_ids"] = final.recommendation_ids
                    event["final_explanation_keys"] = [
                        item.model_dump(mode="json") for item in final.explanations
                    ]
                    discovery = self.agent_tools.discovery
                    if any(
                        identifier not in self.agent_tools.assessed
                        for identifier in final.recommendation_ids
                    ):
                        event["final_validation"] = "unassessed_ids"
                    elif (
                        discovery
                        and discovery.named_target
                        and not set(final.recommendation_ids).issubset(
                            discovery.candidate_ids
                        )
                    ):
                        event["final_validation"] = "outside_named_target"
                    else:
                        try:
                            self.agent_tools.grounded_explanations(final)
                        except ValueError:
                            event["final_validation"] = "invalid_explanation_reference"
                        else:
                            event["final_validation"] = "grounded"
            return reply
        finally:
            event["seconds"] = round(time.perf_counter() - started, 6)


def recommendation_summary(item: RankedProgramme) -> dict:
    assessment = item.assessment
    return {
        "scholarship_id": assessment.scholarship_id,
        "scholarship_name": assessment.scholarship_name,
        "status": assessment.status.value,
        "failed_requirements": assessment.failed_requirements,
        "unknown_requirements": assessment.unknown_requirements,
        "ranking_reasons": item.ranking_reasons,
        "source_url": str(assessment.official_source_url),
        "last_verified_at": assessment.last_verified_at.isoformat(),
    }


def baseline_run(item: dict, session: Session, today: date) -> dict:
    request = MatchRequest(profile=item["profile"], page_size=100)
    started = time.perf_counter()
    matched = match_profile(request, session, today)
    ranked = matched.eligible + matched.needs_verification + matched.ineligible
    return {
        "profile_id": item["id"],
        "seconds": round(time.perf_counter() - started, 6),
        "status": "completed",
        "error": None,
        "recommendations": [
            recommendation_summary(candidate)
            for candidate in ranked
            if candidate.assessment.status != "ineligible"
        ][:3],
        "assessments": [recommendation_summary(candidate) for candidate in ranked],
        "trace": [],
    }


def agent_run(item: dict, goal: str, session: Session, today: date) -> dict:
    request = AgentRequest(profile=item["profile"], goal=goal)
    tools = ObservedTools(session, request.profile, today)
    client = ObservedClient(tools)
    started = time.perf_counter()
    output = {
        "profile_id": item["id"],
        "status": "error",
        "error": None,
        "recommendations": [],
        "fallback_recommendations": [],
        "discovery_candidates": [],
        "discovery_candidate_ids": [],
        "discovery_scope": None,
        "model_error": None,
        "model_explanations": [],
        "warnings": [],
    }
    try:
        result = run_agent(request, tools, client, today=today)
        output.update(
            status=result.status,
            recommendations=[recommendation_summary(x) for x in result.recommendations],
            fallback_recommendations=[
                recommendation_summary(x) for x in result.fallback_recommendations
            ],
            warnings=result.warnings,
            discovery_candidates=[
                recommendation_summary(x) for x in result.discovery_candidates
            ],
            discovery_candidate_ids=result.discovery_candidate_ids,
            discovery_scope=result.discovery_scope,
            model_error=result.model_error,
            model_explanations=[
                item.model_dump(mode="json") for item in result.model_explanations
            ],
        )
    except (OllamaUnavailable, OllamaTimeout, OllamaProtocolError) as error:
        output["error"] = type(error).__name__
    output.update(
        seconds=round(time.perf_counter() - started, 6),
        rounds=client.rounds,
        trace=tools.executions,
        assessments=[recommendation_summary(x) for x in tools.assessed.values()],
    )
    return output


def operational_metrics(runs: list[dict], *, fallback: bool = False) -> dict:
    field = "fallback_recommendations" if fallback else "recommendations"
    latencies = sorted(run["seconds"] for run in runs)
    calls = [event for run in runs for event in run["trace"]]
    success = sum(event["status"] == "ok" for event in calls)
    coverage = sum(bool(run.get(field)) for run in runs)
    failures = sum(run.get("error") is not None for run in runs)
    return {
        "requests": len(runs),
        "candidate_responses": coverage,
        "recommendation_coverage": coverage / len(runs) if runs else None,
        "responses_with_nonfailed_candidates": sum(
            any(item["status"] != "ineligible" for item in run.get(field, []))
            for run in runs
        ),
        "returned_ineligible_candidates": sum(
            item["status"] == "ineligible"
            for run in runs
            for item in run.get(field, [])
        ),
        "failures": failures,
        "failure_rate": failures / len(runs) if runs else None,
        "abstentions": len(runs) - coverage,
        "abstention_rate": (len(runs) - coverage) / len(runs) if runs else None,
        "budget_stops": sum(run["status"] == "limit_reached" for run in runs),
        "mean_latency_seconds": statistics.mean(latencies) if latencies else None,
        "median_latency_seconds": statistics.median(latencies) if latencies else None,
        "p95_latency_seconds": latencies[math.ceil(len(latencies) * 0.95) - 1]
        if latencies
        else None,
        "tool_calls": len(calls),
        "successful_tool_calls": success,
        "tool_success_rate": success / len(calls) if calls else None,
        "tool_outcomes": {
            status: sum(event["status"] == status for event in calls)
            for status in (
                "ok",
                "invalid_arguments",
                "blocked",
                "error",
                "unknown_tool",
            )
        },
    }


def case_predictions(cases: list[dict], runs: list[dict]) -> dict:
    by_profile = {run["profile_id"]: run for run in runs}
    predictions = {}
    for case in cases:
        for item in by_profile.get(case["profile_id"], {}).get("assessments", []):
            if item["scholarship_name"] == case["scholarship_name"]:
                predictions[case["id"]] = item["status"]
    return predictions


def provisional_agreement(cases: list[dict], predictions: dict) -> dict:
    provisional = [
        case
        for case in cases
        if case["label_status"] == "provisional" and case["expected_status"] is not None
    ]
    correct = sum(
        predictions.get(case["id"]) == case["expected_status"] for case in provisional
    )
    return {
        "cases": len(provisional),
        "predicted_cases": sum(case["id"] in predictions for case in provisional),
        "agreement_count": correct,
        "agreement": correct / len(provisional) if provisional else None,
        "scope": "Agreement with draft expectations pending review",
        "expected_class_counts": {
            status: sum(case["expected_status"] == status for case in provisional)
            for status in ("eligible", "ineligible", "needs_verification")
        },
    }


def output_facts(runs: list[dict], field="recommendations") -> list[dict]:
    facts = []
    for run in runs:
        for item in run.get(field, []):
            name = item["scholarship_name"]
            claims = [("scholarship_name", name)]
            for reason in item["ranking_reasons"]:
                if reason.startswith("Published funding: "):
                    value = reason.removeprefix("Published funding: ").split(";", 1)[0]
                    claims.append(("funding_type", value))
            for key, value in claims:
                facts.append(
                    {
                        "scholarship_name": name,
                        "field": key,
                        "value": value,
                        "source_url": item["source_url"],
                    }
                )
    return facts


def summarize(result: dict, cases: list, relevance: list, examples: list):
    baseline = result["baseline"]
    agent = result["agent"]
    audited = result["agent_cases"]
    predictions = {}
    for run in audited:
        case = next(case for case in cases if case["id"] == run["case_id"])
        for item in run["assessments"]:
            if item["scholarship_name"] == case["scholarship_name"]:
                predictions[case["id"]] = item["status"]
    extracted = {item["example_id"]: item["fields"] for item in result["extraction"]}
    extraction = extraction_metrics(examples, extracted)
    # The measured probe uses draft source-checked annotations and short excerpts.
    extraction.update(
        target_status="NOT_EVALUABLE",
        target_achieved=None,
        scope="Evaluation-only Qwen excerpt probe with team review pending",
    )
    result["metrics"] = {
        "baseline_classification": classification_metrics(
            cases, case_predictions(cases, baseline)
        ),
        "agent_tool_classification": classification_metrics(cases, predictions),
        "baseline_provisional_agreement": provisional_agreement(
            cases, case_predictions(cases, baseline)
        ),
        "agent_provisional_agreement": provisional_agreement(cases, predictions),
        "agent_case_assessment_coverage": {
            "cases": len(cases),
            "assessed_cases": len(predictions),
            "coverage": len(predictions) / len(cases) if cases else None,
        },
        "baseline_operational": operational_metrics(baseline),
        "agent_operational": operational_metrics(agent),
        "agent_case_operational": operational_metrics(audited),
        "fallback_operational": operational_metrics(agent, fallback=True),
        "assisted_operational": operational_metrics(
            [
                run
                | {
                    "recommendations": run["recommendations"]
                    or run["fallback_recommendations"]
                }
                for run in agent
            ]
        ),
        "baseline_precision_at_3": precision_at_3(baseline, relevance),
        "agent_precision_at_3": precision_at_3(agent, relevance),
        "extraction_probe": extraction,
        "baseline_citations": citation_metrics(output_facts(baseline), examples),
        "agent_citations": citation_metrics(output_facts(agent), examples),
        "fallback_citations": citation_metrics(
            output_facts(agent, "fallback_recommendations"), examples
        ),
    }
    if not result["signature"]["real_model"]:
        for key in list(result["metrics"]):
            if key.startswith(("agent_", "fallback_", "assisted_", "extraction_")):
                result["metrics"][key] = {
                    "status": "NOT_EVALUABLE",
                    "reason": "Real model experiments were not executed",
                }
    for key in ("baseline_citations", "agent_citations", "fallback_citations"):
        result["metrics"][key].update(
            target_status="NOT_EVALUABLE",
            target_achieved=None,
            scope=(
                "Emitted programme names and published funding labels only. "
                "Independent human review and complete claim auditing are pending."
            ),
        )


def evaluate(output: Path, *, real_model: bool, resume: bool) -> dict:
    profiles = read_json(DATA / "profiles.json")["profiles"]
    cases_document = read_json(DATA / "eligibility_cases.json")
    cases = cases_document["cases"]
    today = date.fromisoformat(cases_document["as_of"])
    relevance = read_json(DATA / "relevance_judgments.json")["judgments"]
    examples = read_json(DATA / "source_annotations.json")["examples"]
    catalogue = load_catalogue(CATALOGUE)
    metadata = local_metadata() if real_model else None
    signature = {
        "inputs": file_hashes(INPUT_FILES),
        "implementation": file_hashes(IMPLEMENTATION_FILES),
        "real_model": real_model,
        "as_of": today.isoformat(),
        "hash_encoding": "UTF-8 without BOM, universal newlines normalized to LF",
        "ollama_version": ((metadata or {}).get("version") or {}).get("version"),
        "model_digest": next(
            (
                model.get("digest")
                for model in (((metadata or {}).get("tags") or {}).get("models", []))
                if model.get("name") == MODEL
            ),
            None,
        ),
    }
    if resume and output.exists():
        result = read_json(output)
        if result["signature"] != signature:
            raise ValueError("Checkpoint inputs or implementation differ")
    else:
        result = {
            "schema_version": 1,
            "signature": signature,
            "started_at_utc": datetime.now(UTC).isoformat(),
            "python": platform.python_version(),
            "git_base_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "model": MODEL,
            "model_options": {
                "num_ctx": 4096,
                "num_predict": 384,
                "temperature": 0,
                "think": False,
                "seed": None,
            },
            "local_ollama": metadata,
            "baseline": [],
            "agent": [],
            "agent_cases": [],
            "extraction": [],
        }
    profiles_by_id = {item["id"]: item for item in profiles}
    with TemporaryDirectory(prefix="scholarship-evaluation-") as directory:
        engine = create_database_engine(Path(directory) / "catalogue.sqlite3")
        try:
            initialize_database(engine)
            import_catalogue(engine, catalogue)
            with Session(engine) as session:
                by_name = {
                    record.scholarship_name: ScholarshipRead.model_validate(record)
                    for record in session.scalars(
                        select(Scholarship).order_by(Scholarship.id)
                    )
                }
                baseline_done = {item["profile_id"] for item in result["baseline"]}
                for item in profiles:
                    if item["id"] not in baseline_done:
                        result["baseline"].append(baseline_run(item, session, today))
                write_checkpoint(output, result)
                if real_model:
                    agent_done = {item["profile_id"] for item in result["agent"]}
                    for item in profiles:
                        if item["id"] in agent_done:
                            continue
                        result["agent"].append(
                            agent_run(item, item["goal"], session, today)
                        )
                        write_checkpoint(output, result)
                        print(f"Recommendation {item['id']} completed", flush=True)
                    cases_done = {item["case_id"] for item in result["agent_cases"]}
                    for case in cases:
                        if case["id"] in cases_done:
                            continue
                        record = by_name[case["scholarship_name"]]
                        destination = (record.destination_country or ["any country"])[0]
                        goal = (
                            f"Assess {record.scholarship_name} for my profile. "
                            f"Destination includes {destination}. "
                            "Check or rank it before finishing."
                        )
                        run = agent_run(
                            profiles_by_id[case["profile_id"]], goal, session, today
                        )
                        run["case_id"] = case["id"]
                        result["agent_cases"].append(run)
                        write_checkpoint(output, result)
                        print(f"Eligibility case {case['id']} completed", flush=True)
            if real_model:
                extraction_done = {item["example_id"] for item in result["extraction"]}
                for example in examples:
                    if example["id"] in extraction_done:
                        continue
                    result["extraction"].append(
                        run_extraction_example(example, OllamaClient())
                    )
                    write_checkpoint(output, result)
                    print(f"Extraction {example['id']} completed", flush=True)
        finally:
            engine.dispose()
    summarize(result, cases, relevance, examples)
    result["completed_at_utc"] = datetime.now(UTC).isoformat()
    write_checkpoint(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-model", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "evaluation/results/local.json"
    )
    arguments = parser.parse_args()
    result = evaluate(
        arguments.output, real_model=arguments.real_model, resume=arguments.resume
    )
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
