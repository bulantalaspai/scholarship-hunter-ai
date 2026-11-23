"""Conservative, source-indexed programme names for local catalogue retrieval."""

import json
import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from backend.app.schemas import ScholarshipRead, ShortText

ALIASES_PATH = Path(__file__).resolve().parents[1] / "data/programme_aliases.json"
FUZZY_THRESHOLD = 0.90
FUZZY_MARGIN = 0.08
MAX_RESOLVED_PROGRAMMES = 3
PositiveId = Annotated[int, Field(gt=0, strict=True)]
QUERY_WORDS = {
    "a",
    "about",
    "all",
    "and",
    "application",
    "applications",
    "assess",
    "at",
    "award",
    "awards",
    "best",
    "candidate",
    "candidates",
    "check",
    "compare",
    "details",
    "eligibility",
    "evaluate",
    "find",
    "for",
    "from",
    "fully",
    "funded",
    "funding",
    "in",
    "international",
    "master",
    "masters",
    "me",
    "of",
    "opportunities",
    "or",
    "partially",
    "please",
    "program",
    "programme",
    "programmes",
    "programs",
    "recommend",
    "requirements",
    "s",
    "scholarship",
    "scholarships",
    "show",
    "the",
    "to",
}


def normalize_name(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"[^\W_]+", normalized))


class ProgrammeOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scholarship_id: PositiveId
    scholarship_name: ShortText
    official_source_url: HttpUrl
    last_verified_at: date


class ProgrammeResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["not_requested", "matched", "ambiguous", "not_found"]
    query: ShortText | None = None
    method: Literal["exact", "alias", "fuzzy"] | None = None
    candidate_ids: list[PositiveId] = Field(default_factory=list)
    options: list[ProgrammeOption] = Field(default_factory=list)
    message: str

    @model_validator(mode="after")
    def consistent_options(self) -> Self:
        option_ids = [item.scholarship_id for item in self.options]
        if self.candidate_ids != option_ids or len(set(option_ids)) != len(option_ids):
            raise ValueError("Resolution IDs must match unique programme options")
        if self.status in {"not_requested", "not_found"}:
            if self.candidate_ids or self.method is not None:
                raise ValueError("Unresolved lookups cannot select programme IDs")
        elif not self.candidate_ids or self.method is None:
            raise ValueError("Resolved lookups require programme options and a method")
        if (
            self.status == "matched"
            and len(self.candidate_ids) > MAX_RESOLVED_PROGRAMMES
        ):
            raise ValueError("At most three explicit programmes can be resolved")
        if self.status == "ambiguous" and len(self.candidate_ids) < 2:
            raise ValueError("Ambiguity requires multiple programme options")
        return self


class AliasEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scholarship_name: ShortText
    aliases: list[ShortText] = Field(min_length=1, max_length=30)
    official_source_url: HttpUrl
    catalogue_verified_at: date
    basis: Literal["catalogue_name", "catalogue_name_and_provider"]

    @model_validator(mode="after")
    def distinct_aliases(self) -> Self:
        values = [normalize_name(value) for value in self.aliases]
        if not normalize_name(self.scholarship_name):
            raise ValueError("Alias programme identity requires letters or numbers")
        if not all(values) or len(set(values)) != len(values):
            raise ValueError("Aliases must have distinct nonempty normalized names")
        if any(value in {"ai", "cs", "emjm"} for value in values):
            raise ValueError("Generic subject and award abbreviations are excluded")
        return self


class AliasDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    description: str
    programmes: list[AliasEntry]

    @model_validator(mode="after")
    def distinct_programmes(self) -> Self:
        names = [normalize_name(item.scholarship_name) for item in self.programmes]
        if len(set(names)) != len(names):
            raise ValueError("Alias programme identities must be unique")
        return self


@lru_cache(maxsize=1)
def load_aliases() -> AliasDocument:
    """Invalid or missing curated alias data fails visibly at its source."""
    return AliasDocument.model_validate(
        json.loads(ALIASES_PATH.read_text(encoding="utf-8-sig"))
    )


def _alias_index(records: list[ScholarshipRead]) -> dict[str, set[int]]:
    by_name: dict[str, list[ScholarshipRead]] = {}
    for record in records:
        by_name.setdefault(normalize_name(record.scholarship_name), []).append(record)
    index: dict[str, set[int]] = {}
    for entry in load_aliases().programmes:
        for record in by_name.get(normalize_name(entry.scholarship_name), []):
            if (
                entry.official_source_url != record.official_source_url
                or entry.catalogue_verified_at > record.last_verified_at
            ):
                raise ValueError(
                    "Programme alias source metadata differs from catalogue"
                )
            for alias in entry.aliases:
                index.setdefault(normalize_name(alias), set()).add(record.id)
    return index


def _named_query(text: str) -> str | None:
    """Extract bounded explicit names without treating broad discovery as a name."""
    quoted = re.search(r'["“]([^"”]+)["”]', text)
    if quoted:
        return quoted.group(1).strip()
    prefix = re.match(
        r"^\s*(?:assess|evaluate|check(?:\s+eligibility\s+(?:for|of))?|"
        r"tell\s+me\s+about|show\s+details\s+(?:for|of|about)|look\s+up|"
        r"find\s+(?:the\s+)?(?:programme|program|scholarship)\s+(?:named|called))\s+",
        text,
        flags=re.IGNORECASE,
    )
    if prefix is None:
        return None
    return _trim_query(text[prefix.end() :])


def _trim_query(query: str) -> str | None:
    query = re.split(
        r"\s+for\s+(?:(?:my|this|the)\s+)?profile\b|"
        r"\.\s*(?:destination\s+includes|check\s+or\s+rank)\b",
        query,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return query.strip().rstrip(".?!").strip() or None


def _discovery_query(text: str) -> str | None:
    prefix = re.match(r"^\s*(?:find|compare|recommend|show)\s+", text, re.IGNORECASE)
    return _trim_query(text[prefix.end() :]) if prefix else None


def _occurrences(
    text: str, index: dict[str, set[int]]
) -> list[tuple[int, int, set[int]]]:
    found = []
    for name, identifiers in index.items():
        found.extend(
            (match.start(), match.end(), identifiers)
            for match in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", text)
        )
    return [
        occurrence
        for occurrence in found
        if not any(
            other[0] <= occurrence[0]
            and other[1] >= occurrence[1]
            and other[:2] != occurrence[:2]
            for other in found
        )
    ]


def _supported_qualifiers(
    text: str,
    found: list[tuple[int, int, set[int]]],
    records: list[ScholarshipRead],
) -> bool:
    remainder = text
    for start, end, _ in sorted(found, reverse=True):
        remainder = remainder[:start] + " " * (end - start) + remainder[end:]
    identifiers = set().union(*(item[2] for item in found))
    documented = set(QUERY_WORDS)
    for record in records:
        if record.id in identifiers:
            values = [
                record.scholarship_name,
                record.university_or_provider,
                record.degree_level or "",
                *(record.destination_country or []),
                *(record.eligible_study_fields or []),
            ]
            documented.update(normalize_name(" ".join(values)).split())
    return set(remainder.split()).issubset(documented)


def _occurrence_ids(
    text: str, found: list[tuple[int, int, set[int]]]
) -> tuple[set[int], bool]:
    specific = set().union(*(item[2] for item in found if len(item[2]) == 1))
    shared = [item[2] for item in found if len(item[2]) > 1]
    # A specific acronym can qualify an umbrella alias in the same phrase.
    if (
        specific
        and shared
        and all(specific.issubset(group) for group in shared)
        and not {"and", "or"}.intersection(text.split())
    ):
        return specific, False
    return set().union(*(item[2] for item in found)), bool(shared)


def _resolved(
    identifiers: set[int],
    records: list[ScholarshipRead],
    *,
    query: str,
    method: Literal["exact", "alias", "fuzzy"],
    ambiguous: bool,
) -> ProgrammeResolution:
    options = [
        ProgrammeOption(
            scholarship_id=record.id,
            scholarship_name=record.scholarship_name,
            official_source_url=record.official_source_url,
            last_verified_at=record.last_verified_at,
        )
        for record in sorted(records, key=lambda item: item.id)
        if record.id in identifiers
    ]
    ambiguous = ambiguous or len(options) > MAX_RESOLVED_PROGRAMMES
    names = ", ".join(item.scholarship_name for item in options)
    if ambiguous:
        message = "Several catalogue programmes match. Specify a full programme name."
    elif method == "fuzzy":
        message = f"Conservative spelling match interpreted the request as {names}."
    else:
        message = f"The catalogue name lookup identified {names}."
    return ProgrammeResolution(
        status="ambiguous" if ambiguous else "matched",
        query=query,
        method=method,
        candidate_ids=[item.scholarship_id for item in options],
        options=options,
        message=message,
    )


def resolve_programme(
    text: str, records: list[ScholarshipRead], *, explicit: bool = False
) -> ProgrammeResolution:
    """Resolve names conservatively and keep ambiguity distinct from discovery."""
    if len(text) > 300:
        raise ValueError("Programme lookup text must contain at most 300 characters")
    text = text.strip()
    query = (text or None) if explicit else _named_query(text)
    lookup_query = query or _discovery_query(text) or text
    normalized = normalize_name(lookup_query)
    names: dict[str, set[int]] = {}
    for record in records:
        name = normalize_name(record.scholarship_name)
        if name:
            names.setdefault(name, set()).add(record.id)
    aliases = _alias_index(records)
    unsupported_qualifiers = False
    for method, index in (("exact", names), ("alias", aliases)):
        found = _occurrences(normalized, index)
        # A common lowercase noun such as "gist" requires a lookup context.
        if method == "alias" and query is None and normalized not in index:
            if _discovery_query(text) is None:
                continue
        if found:
            if not _supported_qualifiers(normalized, found, records):
                query = lookup_query
                unsupported_qualifiers = True
                continue
            identifiers, ambiguous = _occurrence_ids(normalized, found)
            return _resolved(
                identifiers,
                records,
                query=lookup_query,
                method=method,
                ambiguous=ambiguous,
            )

    normalized_query = normalize_name(query or "")
    if (
        query
        and not unsupported_qualifiers
        and len(normalized_query) >= 12
        and len(normalized_query.split()) >= 3
    ):
        scores: dict[int, float] = {}
        for name, identifiers in [*names.items(), *aliases.items()]:
            score = SequenceMatcher(
                None, normalized_query, name, autojunk=False
            ).ratio()
            for identifier in identifiers:
                scores[identifier] = max(scores.get(identifier, 0.0), score)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        if ranked and ranked[0][1] >= FUZZY_THRESHOLD:
            close = {
                identifier
                for identifier, score in ranked
                if ranked[0][1] - score < FUZZY_MARGIN
            }
            return _resolved(
                close,
                records,
                query=query,
                method="fuzzy",
                ambiguous=len(close) > 1,
            )

    return ProgrammeResolution(
        status="not_found" if explicit or query else "not_requested",
        query=query,
        message=(
            "No catalogue programme matched that name. Check the full name or alias."
            if explicit or query
            else "The request uses general catalogue discovery."
        ),
    )
