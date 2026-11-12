"""Application startup, local catalogue, and the original typed health check."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from backend.app.agent_api import router as agent_router
from backend.app.database import create_database_engine, initialize_database
from backend.app.eligibility_api import router as eligibility_router
from backend.app.scholarships import router


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["scholarship-hunter-ai"]


def health() -> HealthResponse:
    """Report API availability without invoking a model or querying the catalogue."""
    return HealthResponse(status="ok", service="scholarship-hunter-ai")


def create_app(database_path: str | Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = create_database_engine(database_path)
        try:
            initialize_database(engine)
            application.state.database_engine = engine
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="Scholarship Hunter AI", version="0.5.0", lifespan=lifespan
    )
    application.add_api_route(
        "/api/health", health, response_model=HealthResponse, tags=["Health"]
    )
    application.include_router(router)
    application.include_router(eligibility_router)
    application.include_router(agent_router)
    return application


app = create_app()
