"""The agent is optional: startup and non-AI endpoints never contact Ollama."""

import threading
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.app.agent import run_agent
from backend.app.agent_schemas import AgentRequest, AgentResponse
from backend.app.agent_tools import AgentTools
from backend.app.eligibility_api import EvaluationDate
from backend.app.ollama_client import (
    OllamaClient,
    OllamaProtocolError,
    OllamaTimeout,
    OllamaUnavailable,
)
from backend.app.scholarships import DatabaseSession

router = APIRouter(prefix="/api/agent", tags=["Local AI agent"])
_agent_gate = threading.BoundedSemaphore(1)


def get_ollama_client() -> OllamaClient:
    return OllamaClient()


@router.post("/recommend", response_model=AgentResponse)
def recommend(
    request: AgentRequest,
    session: DatabaseSession,
    today: EvaluationDate,
    client: Annotated[OllamaClient, Depends(get_ollama_client)],
) -> AgentResponse:
    if not _agent_gate.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail=(
                "The local AI agent is busy. Use deterministic matching or try again."
            ),
        )
    try:
        return run_agent(
            request, AgentTools(session, request.profile, today), client, today=today
        )
    except OllamaUnavailable:
        raise HTTPException(
            status_code=503,
            detail=(
                "Local Ollama or qwen3:4b-instruct is unavailable. The non-AI "
                "catalogue and matching endpoints remain available."
            ),
        ) from None
    except OllamaTimeout:
        raise HTTPException(
            status_code=504,
            detail=(
                "Local AI inference exceeded its time budget. Use deterministic "
                "matching or try a narrower goal."
            ),
        ) from None
    except OllamaProtocolError:
        raise HTTPException(
            status_code=502,
            detail=(
                "Local Ollama returned an invalid, oversized, truncated or "
                "over-context response; no model claims were shown."
            ),
        ) from None
    finally:
        _agent_gate.release()
