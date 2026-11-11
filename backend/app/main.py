"""Phase 1 API: application startup and a typed health check."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Scholarship Hunter AI", version="0.1.0")


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["scholarship-hunter-ai"]


@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
def health() -> HealthResponse:
    """Report API availability; no database or model is required in Phase 1."""
    return HealthResponse(status="ok", service="scholarship-hunter-ai")
