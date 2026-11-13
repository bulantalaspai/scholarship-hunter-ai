"""The agent is optional: startup and non-AI endpoints never contact Ollama."""

import threading
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.agent import busy_response, run_agent
from backend.app.agent_schemas import AgentRequest, AgentResponse
from backend.app.agent_tools import AgentTools
from backend.app.eligibility_api import EvaluationDate
from backend.app.ollama_client import OllamaClient
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
    tools = AgentTools(session, request.profile, today)
    if not _agent_gate.acquire(blocking=False):
        return busy_response(request, tools, today)
    try:
        return run_agent(request, tools, client, today=today)
    finally:
        _agent_gate.release()
