"""Opt-in, loopback-only HTTP interface for the local review operator."""

import hmac
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi import Path as ApiPath
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    ValidationError,
)

from backend.collection import dashboard
from backend.collection.funding_evidence import (
    FundingEvidence,
    extract_funding,
    funding_conflicts,
)
from backend.collection.review import decide

TOKEN_PATTERN = r"[A-Za-z0-9_-]{32,128}"
LOOPBACK_ORIGIN = r"http://(?:127\.0\.0\.1|localhost|\[::1\]):[0-9]{1,5}"
DEFAULT_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")
MAX_BODY = 32_768
NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
MCCALL_SOURCE = (
    "https://www.mcgill.ca/gradapplicants/funding/external/mccall-macbain-scholarship"
)
MCCALL_FUNDING_FILE = (
    Path(__file__).resolve().parents[2]
    / ".local-run/collection/phase-08c/mccall-funding-evidence.json"
)


@dataclass(frozen=True)
class ReviewSettings:
    stage_path: Path
    token: str = field(repr=False)
    origins: tuple[str, ...] = DEFAULT_ORIGINS
    funding_file: Path | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(TOKEN_PATTERN, self.token):
            raise ValueError(
                "Configure a random URL-safe review key of 32–128 characters"
            )
        if not self.origins or any(
            not re.fullmatch(LOOPBACK_ORIGIN, origin)
            or not 1 <= int(origin.rsplit(":", 1)[1]) <= 65_535
            for origin in self.origins
        ):
            raise ValueError("Review origins must be explicit HTTP loopback origins")
        raw_path = str(self.stage_path)
        if raw_path.startswith(("//", "\\\\")) or "://" in raw_path:
            raise ValueError("Use an existing local review SQLite file")
        if not self.stage_path.is_file():
            raise ValueError("The review queue must be an existing SQLite file")

    @classmethod
    def from_environment(cls) -> ReviewSettings | None:
        path = os.environ.get("SCHOLARSHIP_REVIEW_STAGE")
        token = os.environ.get("SCHOLARSHIP_REVIEW_TOKEN")
        if not path and not token:
            return None
        if not path or not token:
            raise ValueError(
                "Configure SCHOLARSHIP_REVIEW_STAGE and SCHOLARSHIP_REVIEW_TOKEN"
            )
        configured = os.environ.get("SCHOLARSHIP_REVIEW_ORIGINS")
        return cls(
            stage_path=Path(path),
            token=token,
            origins=(
                tuple(origin.strip() for origin in configured.split(","))
                if configured is not None
                else DEFAULT_ORIGINS
            ),
            funding_file=MCCALL_FUNDING_FILE if MCCALL_FUNDING_FILE.is_file() else None,
        )


class Attestation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    reviewer: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    rationale: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]


class FieldDecision(Attestation):
    decision: Literal["accepted", "rejected", "unresolved"]
    value: JsonValue = None
    evidence: list[Annotated[str, Field(min_length=1, max_length=400)]] = Field(
        default_factory=list, max_length=8
    )


class DraftDecision(Attestation):
    decision: Literal["rejected", "needs_more_evidence"]


class Confirmed(Attestation):
    confirm: Literal[True]


DraftId = Annotated[str, ApiPath(pattern=r"^[a-f0-9]{64}$")]
FieldKey = Annotated[str, ApiPath(pattern=r"^[a-z_]{1,64}$")]


def _error(status: int, message: str) -> HTTPException:
    return HTTPException(status, message, headers=NO_STORE)


def _guard(request: Request, settings: ReviewSettings) -> None:
    host = request.headers.get("host", "")
    origin = request.headers.get("origin")
    # Uvicorn can rewrite the ASGI peer before this guard runs. It retains
    # the forwarding headers, so reject those even when the peer looks local.
    if (
        request.client is None
        or request.client.host not in {"127.0.0.1", "::1"}
        or any(
            name in {"forwarded", "x-real-ip"} or name.startswith("x-forwarded-")
            for name in request.headers
        )
        or len(request.headers.getlist("host")) != 1
        or len(request.headers.getlist("origin")) > 1
        or f"http://{host}" not in settings.origins
        or (origin is not None and origin != f"http://{host}")
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise _error(403, "The review API requires a trusted local origin.")
    scheme, _, key = request.headers.get("authorization", "").partition(" ")
    if (
        len(request.headers.getlist("authorization")) != 1
        or scheme.lower() != "bearer"
        or not re.fullmatch(TOKEN_PATTERN, key)
        or not hmac.compare_digest(key, settings.token)
    ):
        raise _error(401, "Enter the local review access key.")
    if request.method == "POST":
        content_type = request.headers.get("content-type", "").partition(";")[0]
        if content_type.strip().lower() != "application/json":
            raise _error(415, "Review actions require JSON.")
        lengths = request.headers.getlist("content-length")
        if (
            len(lengths) != 1
            or not re.fullmatch(r"[0-9]{1,10}", lengths[0])
            or "transfer-encoding" in request.headers
        ):
            raise _error(411, "Review actions require a bounded request body.")
        if int(lengths[0]) > MAX_BODY:
            raise _error(413, "The review request is too large.")


def _load_funding(file: Path | None) -> tuple[FundingEvidence, ...]:
    if file is None:
        return ()
    with file.open("rb") as handle:
        data = handle.read(MAX_BODY + 1)
    if len(data) > MAX_BODY:
        raise ValueError("The local supplemental funding artifact is too large")
    artifact = json.loads(data)
    observations = tuple(
        FundingEvidence.model_validate_json(json.dumps(item))
        for item in artifact["observations"]
    )
    excerpts = {item["url"]: item["text"] for item in artifact["sources"]}
    if len(observations) > 16:
        raise ValueError("Too many local supplemental funding observations")
    if any(
        item
        not in extract_funding(
            excerpts.get(item.source_url, ""),
            item.source_url,
            publication_year=item.publication_year,
            cycle=item.cycle,
            retrieved_on=item.retrieved_on,
        )
        for item in observations
    ):
        raise ValueError(
            "Supplemental funding observations must match the local excerpt"
        )
    return observations


def review_router(settings: ReviewSettings) -> APIRouter:
    """Create routes only for explicitly enabled local installations."""
    supplemental = _load_funding(settings.funding_file)
    staging = settings.stage_path.resolve()

    class LocalReviewRoute(APIRoute):
        def get_route_handler(self):
            handle = super().get_route_handler()

            async def guarded(request: Request):
                _guard(request, settings)
                try:
                    response = await handle(request)
                except RequestValidationError as error:
                    raise _error(422, "Check the required review fields.") from error
                response.headers.update(NO_STORE)
                return response

            return guarded

    router = APIRouter(
        prefix="/api/review", route_class=LocalReviewRoute, include_in_schema=False
    )

    def detail(draft_id: str) -> dict:
        result = dashboard.inspect_dashboard(staging, draft_id)
        draft = result["draft"]
        for field_name in ("scholarship_name", "university_or_provider"):
            evidence = draft["fields"].get(field_name)
            result[field_name] = evidence["quote"] if evidence else None
        result["official_source_url"] = draft["official_source_url"]
        observations = tuple(
            FundingEvidence.model_validate_json(json.dumps(item))
            for item in draft.get("funding_observations", [])
        )
        is_mccall = draft["official_source_url"] == MCCALL_SOURCE
        related = supplemental if is_mccall else ()
        conflicts = funding_conflicts(observations + related)
        if is_mccall or any(item.status != "distinct_cycles" for item in conflicts):
            result["blocked_fields"] = sorted(
                set(result["blocked_fields"]) | {"funding_amount", "living_stipend"}
            )
        result["supplemental_funding"] = [
            item.model_dump(mode="json") for item in related
        ]
        result["funding_conflicts"] = [
            item.model_dump(mode="json") for item in conflicts
        ]
        # A known discrepancy stays blocked if the optional archive is unavailable.
        result["supplemental_funding_missing"] = is_mccall and not related
        return result

    def authorized_detail(draft_id: str) -> dict:
        try:
            return detail(draft_id)
        except ValueError as error:
            if str(error) == "Unknown collection draft":
                raise _error(404, "Draft not found.") from error
            raise _error(409, "The staged evidence could not be validated.") from error
        except sqlite3.Error as error:
            raise _error(503, "The local review queue is unavailable.") from error

    def apply_action(action, draft_id: str) -> dict:
        try:
            action()
        except ValueError as error:
            # Pydantic errors include operator input. Keep those out of responses.
            message = (
                "The reviewed record does not meet the catalogue requirements."
                if isinstance(error, ValidationError)
                else str(error)
            )
            raise _error(409, message) from error
        except (OSError, sqlite3.Error) as error:
            raise _error(503, "The local review database is unavailable.") from error
        return authorized_detail(draft_id)

    @router.get("/drafts")
    def drafts():
        try:
            return [
                {
                    **item,
                    "scholarship_name": item["name"],
                    "university_or_provider": item["provider"],
                }
                for item in dashboard.list_dashboard(staging)
            ]
        except (ValueError, sqlite3.Error) as error:
            raise _error(503, "The local review queue is unavailable.") from error

    @router.get("/drafts/{draft_id}")
    def get_draft(draft_id: DraftId):
        return authorized_detail(draft_id)

    @router.post("/drafts/{draft_id}/fields/{field_id}")
    def save_field(draft_id: DraftId, field_id: FieldKey, data: FieldDecision):
        existing = authorized_detail(draft_id)
        return apply_action(
            lambda: dashboard.save_field(
                staging,
                draft_id,
                field_id,
                data.decision,
                data.reviewer,
                data.rationale,
                value=data.value,
                evidence=tuple(data.evidence),
                blocked_fields=tuple(existing["blocked_fields"]),
            ),
            draft_id,
        )

    @router.post("/drafts/{draft_id}/decision")
    def set_decision(draft_id: DraftId, data: DraftDecision):
        authorized_detail(draft_id)
        return apply_action(
            lambda: decide(
                staging, draft_id, data.decision, data.reviewer, data.rationale
            ),
            draft_id,
        )

    @router.post("/drafts/{draft_id}/approve")
    def approve(draft_id: DraftId, data: Confirmed):
        existing = authorized_detail(draft_id)
        return apply_action(
            lambda: dashboard.approve(
                staging,
                draft_id,
                data.reviewer,
                data.rationale,
                blocked_fields=tuple(existing["blocked_fields"]),
            ),
            draft_id,
        )

    @router.post("/drafts/{draft_id}/publish")
    def publish(draft_id: DraftId, data: Confirmed, request: Request):
        existing = authorized_detail(draft_id)
        catalogue = Path(request.app.state.database_engine.url.database)
        return apply_action(
            lambda: dashboard.publish_reviewed(
                staging,
                draft_id,
                catalogue,
                data.reviewer,
                data.rationale,
                blocked_fields=tuple(existing["blocked_fields"]),
            ),
            draft_id,
        )

    return router
