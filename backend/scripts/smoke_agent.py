"""Opt-in live Ollama smoke test with synthetic input and a disposable database.

Run from the repository root: python -m backend.scripts.smoke_agent
Requires development dependencies. Does not pull models or alter application data.
"""

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from backend.app.agent_api import get_ollama_client
from backend.app.database import create_database_engine, initialize_database
from backend.app.import_catalogue import import_catalogue, load_catalogue
from backend.app.main import create_app
from backend.app.ollama_client import OllamaClient


class ObservedClient(OllamaClient):
    def __init__(self):
        self.rounds = []

    def chat(self, messages, tools, *, timeout):
        started = time.monotonic()
        reply = super().chat(messages, tools, timeout=timeout)
        self.rounds.append(
            {
                "seconds": round(time.monotonic() - started, 2),
                "prompt_tokens": reply.prompt_eval_count,
                "requested_tools": [
                    call.function.name for call in reply.message.tool_calls
                ],
            }
        )
        return reply


def main():
    observer = ObservedClient()
    with TemporaryDirectory(prefix="scholarship-agent-smoke-") as temporary:
        database = Path(temporary) / "smoke.sqlite3"
        engine = create_database_engine(database)
        initialize_database(engine)
        import_catalogue(
            engine,
            load_catalogue(
                Path(__file__).resolve().parents[1]
                / "data"
                / "curated_scholarships.json"
            ),
        )
        engine.dispose()
        app = create_app(database)
        app.dependency_overrides[get_ollama_client] = lambda: observer
        started = time.monotonic()
        with TestClient(app) as client:
            response = client.post(
                "/api/agent/recommend",
                json={
                    "profile": {
                        "nationality": "Kazakhstan",
                        "degree_level": "bachelor",
                        "degree_completed": True,
                        "field_of_study": "Computer Science",
                        "gpa": 3.5,
                        "gpa_scale": 4.0,
                        "ielts_overall": 7.0,
                        "intended_start_year": 2027,
                        "funding_preference": "fully_funded",
                    },
                    "goal": "Find funded master's candidates related to my field.",
                },
            )
        report = {
            "synthetic_profile": True,
            "http_status": response.status_code,
            "seconds": round(time.monotonic() - started, 2),
            "model_rounds": observer.rounds,
            "response": response.json(),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if (
            response.status_code != 200
            or response.json().get("status") == "model_error"
        ):
            raise SystemExit(1)
        if response.json()["status"] == "limit_reached":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
