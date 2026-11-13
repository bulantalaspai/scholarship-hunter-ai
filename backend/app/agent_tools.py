"""Validated, allowlisted tools around existing deterministic catalogue services."""

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agent_schemas import (
    CheckArguments,
    FetchArguments,
    FinalSelection,
    GroundedExplanation,
    RankArguments,
    SearchArguments,
    ToolTrace,
)
from backend.app.candidate_discovery import DiscoveryResult, discover_candidates
from backend.app.eligibility import rank_programmes
from backend.app.eligibility_schemas import (
    EligibilityResult,
    RankedProgramme,
    StudentProfile,
)
from backend.app.models import Scholarship, ScholarshipEligibilityPolicy
from backend.app.official_pages import (
    OfficialPage,
    PublicPageError,
    fetch_official_page,
)
from backend.app.programme_resolution import resolve_programme
from backend.app.schemas import ScholarshipQuery, ScholarshipRead
from backend.app.scholarships import query_scholarships


def tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


ID_SCHEMA = {"type": "integer", "minimum": 1}
TOOL_DEFINITIONS = [
    tool(
        "search_scholarships",
        "Search SQLite for up to 3 IDs and official sources.",
        {
            "programme_name": {
                "type": "string",
                "maxLength": 300,
                "description": "Full name or documented programme alias. Optional.",
            },
            "country": {
                "type": "string",
                "maxLength": 100,
                "description": "Destination only. Omit if unspecified.",
            },
            "field": {
                "type": "string",
                "maxLength": 100,
                "description": "Study-field substring. Optional.",
            },
            "funding_type": {
                "type": "string",
                "enum": ["fully_funded", "partially_funded", "unknown"],
            },
        },
        [],
    ),
    tool(
        "fetch_official_page",
        "Read an approved candidate URL as untrusted evidence.",
        {
            "url": {"type": "string", "maxLength": 2048},
        },
        ["url"],
    ),
    tool(
        "check_eligibility",
        "Assess a discovered ID with deterministic rules and the original profile.",
        {
            "scholarship_id": ID_SCHEMA,
        },
        ["scholarship_id"],
    ),
    tool(
        "rank_scholarships",
        "Assess and rank up to 3 discovered IDs. Preserves classifications.",
        {
            "scholarship_ids": {
                "type": "array",
                "items": ID_SCHEMA,
                "minItems": 1,
                "maxItems": 3,
                "uniqueItems": True,
            },
        },
        ["scholarship_ids"],
    ),
]


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: dict
    summary: str = Field(max_length=200)


class AgentTools:
    def __init__(
        self,
        session: Session,
        profile: StudentProfile,
        today: date,
        page_fetcher: Callable = fetch_official_page,
    ):
        self.session = session
        self.profile = profile.model_copy(deep=True)
        self.today = today
        self.page_fetcher = page_fetcher
        self.discovered: dict[int, ScholarshipRead] = {}
        self.assessed: dict[int, RankedProgramme] = {}
        self.pages: dict[str, OfficialPage] = {}
        self.discovery: DiscoveryResult | None = None

    def definitions(self) -> list[dict]:
        """Offer programme-name arguments only for a resolved named request."""
        definitions = deepcopy(TOOL_DEFINITIONS)
        if not self.discovery or not self.discovery.named_target:
            properties = definitions[0]["function"]["parameters"]["properties"]
            properties.pop("programme_name")
        return definitions

    def prepare(self, goal: str) -> None:
        """Retain deterministic candidates independently of model search choices."""
        self.discovery = discover_candidates(
            self.session, self.profile, self.today, goal
        )
        self.discovered.update({record.id: record for record in self.discovery.records})

    def candidate_context(self) -> dict:
        context = {
            "scope": "named_target"
            if self.discovery and self.discovery.named_target
            else "catalogue",
            "candidates": [
                {
                    "id": item.assessment.scholarship_id,
                    "name": item.assessment.scholarship_name[:60],
                    "source": str(item.assessment.official_source_url),
                }
                for item in self.discovery.candidates
            ]
            if self.discovery
            else [],
        }
        if self.discovery and self.discovery.named_target:
            context["target_ids"] = self.discovery.candidate_ids
        return context

    def _search(self, args: SearchArguments) -> ToolOutput:
        named_ids = (
            self.discovery.candidate_ids
            if self.discovery and self.discovery.named_target
            else []
        )
        resolution = None
        filters_ignored = []
        if named_ids or args.programme_name:
            records = [
                ScholarshipRead.model_validate(record)
                for record in self.session.scalars(
                    select(Scholarship).order_by(Scholarship.id)
                )
            ]
            if args.programme_name:
                resolution = resolve_programme(
                    args.programme_name, records, explicit=True
                )
                if resolution.status != "matched":
                    if named_ids and set(named_ids).issubset(resolution.candidate_ids):
                        resolution = self.discovery.resolution
                    else:
                        return ToolOutput(
                            data={
                                "total": 0,
                                "candidates": [],
                                "name_resolution": {
                                    "status": resolution.status,
                                    "message": resolution.message,
                                    "options": [
                                        {
                                            "id": option.scholarship_id,
                                            "name": option.scholarship_name[:72],
                                        }
                                        for option in resolution.options[:3]
                                    ],
                                },
                            },
                            summary=resolution.message[:200],
                        )
                if named_ids and not set(resolution.candidate_ids).issubset(named_ids):
                    raise PublicPageError("outside_named_target")
            identifiers = named_ids or resolution.candidate_ids
            items = [item for item in records if item.id in identifiers][:3]
            total = len(identifiers)
            filters_ignored = [
                key
                for key in ("country", "field", "funding_type")
                if getattr(args, key) is not None
            ]
        else:
            page = query_scholarships(
                ScholarshipQuery(
                    **args.model_dump(exclude={"programme_name"}), page=1, page_size=3
                ),
                self.session,
            )
            items = [
                ScholarshipRead.model_validate(item.model_dump()) for item in page.items
            ]
            total = page.total
        self.discovered.update({item.id: item for item in items})
        data = {
            "total": total,
            "candidates": [
                {
                    "id": item.id,
                    "name": item.scholarship_name[:72],
                    "funding": item.funding_type.value,
                    "source": str(item.official_source_url),
                    "verified": item.last_verified_at.isoformat(),
                }
                for item in items
            ],
        }
        if named_ids:
            data["target_ids"] = named_ids
        if filters_ignored:
            data["filters_ignored"] = filters_ignored
            data["filter_notice"] = (
                "Named-programme lookup takes priority over discovery filters. "
                "Eligibility checks retain failures."
            )
        if resolution:
            data["name_resolution"] = {
                "status": resolution.status,
                "method": resolution.method,
                "message": resolution.message,
            }
        return ToolOutput(
            data=data,
            summary=f"Found {total} records; returned {len(items)} candidates.",
        )

    def _rank(
        self, ids: list[int], *, record_assessment: bool = True
    ) -> list[RankedProgramme]:
        candidates = [
            (
                self.discovered[identifier],
                self.session.get(
                    ScholarshipEligibilityPolicy,
                    self.discovered[identifier].identity_key,
                ),
            )
            for identifier in ids
        ]
        ranked = rank_programmes(self.profile, candidates, today=self.today)
        validated = [
            RankedProgramme.model_validate(item.model_dump()) for item in ranked
        ]
        if record_assessment:
            self.assessed.update(
                {item.assessment.scholarship_id: item for item in validated}
            )
        return validated

    @staticmethod
    def _compact(result: EligibilityResult) -> dict:
        result = EligibilityResult.model_validate(result.model_dump())
        return {
            "id": result.scholarship_id,
            "status": result.status.value,
            "admission": result.admission_status.value,
            "funding": result.funding_status.value,
            "application": result.application_status.value,
            "failed": result.failed_requirements[:3],
            "unknown": result.unknown_requirements[:4],
            "unknown_count": len(result.unknown_requirements),
            "source": str(result.official_source_url),
            "verified": result.last_verified_at.isoformat(),
        }

    def dispatch(
        self, name: str, arguments: dict, *, step: int, timeout: float
    ) -> tuple[dict, ToolTrace]:
        trace = ToolTrace(step=step, name=name, status="ok", summary="")
        try:
            if name == "search_scholarships":
                args = SearchArguments.model_validate(arguments)
                output = self._search(args)
            elif name == "fetch_official_page":
                args = FetchArguments.model_validate(arguments)
                approved_candidates = {
                    str(item.official_source_url) for item in self.discovered.values()
                }
                if args.url not in approved_candidates:
                    raise PublicPageError("not_discovered_source")
                if args.url not in self.pages:
                    self.pages[args.url] = OfficialPage.model_validate(
                        self.page_fetcher(
                            args.url,
                            timeout=min(6.0, timeout),
                        ).model_dump()
                    )
                page = self.pages[args.url]
                trace.source_url, trace.fetched_at = page.source_url, page.fetched_at
                excerpt = page.model_dump(mode="json")
                excerpt["untrusted_text"] = page.untrusted_text[:600]
                excerpt["truncated"] = page.truncated or len(page.untrusted_text) > 600
                output = ToolOutput(
                    data=excerpt,
                    summary=(
                        "Read approved official page as untrusted text; "
                        "eligibility rules unchanged."
                    ),
                )
            elif name == "check_eligibility":
                args = CheckArguments.model_validate(arguments)
                if args.scholarship_id not in self.discovered:
                    raise PublicPageError("id_not_discovered")
                item = self._rank([args.scholarship_id])[0]
                output = ToolOutput(
                    data=self._compact(item.assessment),
                    summary=(
                        f"Deterministic eligibility: {item.assessment.status.value}."
                    ),
                )
            elif name == "rank_scholarships":
                args = RankArguments.model_validate(arguments)
                if any(
                    identifier not in self.discovered
                    for identifier in args.scholarship_ids
                ):
                    raise PublicPageError("id_not_discovered")
                ranked = self._rank(args.scholarship_ids)
                output = ToolOutput(
                    data={
                        # Sources/dates already appeared in the search results.
                        # Public assessments retain the full evidence metadata.
                        "ranked": [
                            {
                                key: value
                                for key, value in self._compact(item.assessment).items()
                                if key not in {"source", "verified"}
                            }
                            for item in ranked
                        ]
                    },
                    summary=(
                        f"Ranked {len(ranked)} candidates without changing eligibility."
                    ),
                )
            else:
                trace.status, trace.summary = (
                    "unknown_tool",
                    "Unknown tool; nothing executed.",
                )
                return {"error": "unknown_tool"}, trace
            trace.arguments = args.model_dump(mode="json", exclude_none=True)
            if len(json.dumps(output.data, ensure_ascii=False).encode("utf-8")) > 3200:
                trace.status, trace.summary = (
                    "error",
                    "Tool result exceeds the compact context budget.",
                )
                return {"error": "tool_result_too_large"}, trace
            trace.summary = output.summary
            return output.data, trace
        except ValidationError:
            trace.status, trace.summary = (
                "invalid_arguments",
                "Tool arguments or result failed validation.",
            )
            return {"error": "invalid_arguments_or_result"}, trace
        except PublicPageError as error:
            # Do not echo rejected URLs, arbitrary model arguments, or page text.
            if error.code in {"timeout", "network_error", "http_error"}:
                trace.status, trace.summary = (
                    "error",
                    "Official source unavailable; no new evidence was verified.",
                )
                return {"error": "official_source_unavailable"}, trace
            trace.status, trace.summary = (
                "blocked",
                "Tool request was blocked by source or candidate validation.",
            )
            data = {"error": "source_or_candidate_not_allowed"}
            if self.discovery and self.discovery.named_target:
                data["target_ids"] = self.discovery.candidate_ids
            return data, trace
        except TimeoutError, OSError:
            trace.status, trace.summary = (
                "error",
                "Tool evidence could not be retrieved in time.",
            )
            return {"error": "tool_unavailable"}, trace

    def final_recommendations(self, ids: list[int]) -> list[RankedProgramme]:
        # Only assessments actually obtained through model-requested tools qualify.
        if any(identifier not in self.assessed for identifier in ids):
            raise ValueError("Final IDs must have a validated tool assessment")
        if (
            self.discovery
            and self.discovery.named_target
            and not set(ids).issubset(self.discovery.candidate_ids)
        ):
            raise ValueError("Final IDs must retain the explicitly named target")
        return self._rank(ids) if ids else []

    def grounded_explanations(
        self, selection: FinalSelection
    ) -> list[GroundedExplanation]:
        """Render model-selected requirement keys using deterministic text only."""
        explanations = []
        for item in selection.explanations:
            assessment = self.assessed[item.scholarship_id].assessment
            by_key = {check.requirement: check for check in assessment.requirements}
            if not set(item.requirements).issubset(by_key):
                raise ValueError("Explanation keys must refer to assessed requirements")
            explanations.append(
                GroundedExplanation(
                    scholarship_id=item.scholarship_id,
                    requirements=[by_key[key] for key in item.requirements],
                )
            )
        return explanations

    def fallback_recommendations(self) -> list[RankedProgramme]:
        """Reassess retrieved candidates and retain unresolved classifications."""
        if self.discovery is not None:
            return [
                item
                for item in self.discovery.candidates
                if item.assessment.status == "needs_verification"
            ]
        if not self.discovered:
            return []
        return [
            item
            for item in self._rank(list(self.discovered), record_assessment=False)
            if item.assessment.status == "needs_verification"
        ][:3]
