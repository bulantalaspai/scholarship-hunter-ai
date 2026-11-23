"""Interpret explicit recommendation preferences and check catalogue evidence."""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.schemas import FundingType, ScholarshipRead

PreferenceKind = Literal["destination", "funding"]
PreferenceMode = Literal["required", "preferred"]
PreferenceStatus = Literal["confirmed", "unmatched", "unverified"]


class RequestPreference(BaseModel):
    kind: PreferenceKind
    label: str
    mode: PreferenceMode
    values: tuple[str, ...] = Field(default=(), exclude=True)
    all_destinations: bool = Field(default=False, exclude=True)


class PreferenceCheck(BaseModel):
    kind: PreferenceKind
    label: str
    mode: PreferenceMode
    status: PreferenceStatus
    evidence: str


# Geographical Europe follows UN M49. EU membership is evaluated separately.
EU = frozenset(
    "austria belgium bulgaria croatia cyprus czechia denmark estonia finland france "
    "germany greece hungary ireland italy latvia lithuania luxembourg malta "
    "netherlands poland portugal romania slovakia slovenia spain sweden".split()
)
EUROPE = (EU - {"cyprus"}) | frozenset(
    {
        "albania",
        "andorra",
        "belarus",
        "bosnia and herzegovina",
        "faroe islands",
        "gibraltar",
        "guernsey",
        "iceland",
        "isle of man",
        "jersey",
        "liechtenstein",
        "moldova",
        "monaco",
        "montenegro",
        "north macedonia",
        "norway",
        "russia",
        "san marino",
        "serbia",
        "svalbard and jan mayen",
        "switzerland",
        "ukraine",
        "united kingdom",
        "vatican city",
        "åland islands",
    }
)
REGIONS = {"europe": EUROPE, "european union": EU}
COUNTRY_ALIASES = {
    "czech republic": "czechia",
    "deutschland": "germany",
    "eu": "european union",
    "republic of korea": "south korea",
    "republic of moldova": "moldova",
    "russian federation": "russia",
    "türkiye": "turkey",
    "uk": "united kingdom",
    "united kingdom of great britain and northern ireland": "united kingdom",
    "united states of america": "united states",
    "us": "united states",
    "usa": "united states",
}
COMMON_DESTINATIONS = {
    "australia",
    "brazil",
    "canada",
    "china",
    "india",
    "indonesia",
    "japan",
    "kazakhstan",
    "malaysia",
    "mexico",
    "new zealand",
    "singapore",
    "south africa",
    "south korea",
    "thailand",
    "turkey",
    "united arab emirates",
    "united states",
}
ADJECTIVE_DESTINATIONS = {
    "european union": "european union",
    "european": "europe",
    "german": "germany",
    "japanese": "japan",
}
SOFT_DESTINATION_WORDS = r"\b(?:prefer(?:ably)?|ideally|prioriti[sz]e|open to)\b"
DESTINATION_MARKER = re.compile(
    r"\bdestination\s*[:=]\s*|"
    rf"{SOFT_DESTINATION_WORDS}\s+(?:(?:study\s+)?in\s+)?|"
    r"\b(?:based in|located in|to study in|only in|across|throughout|within|in)\s+"
)
SOFT_DESTINATION = re.compile(SOFT_DESTINATION_WORDS)
SOFT_DESTINATION_PREFIX = re.compile(rf"{SOFT_DESTINATION_WORDS}\s+$")
SOFT_SUFFIX = re.compile(
    r"\s+(?:preferred|(?:is\s+)?(?:fine|ok(?:ay)?|acceptable|allowed|welcome)|"
    r"if possible|if available)\b"
)
FOLLOWING_DESTINATION = re.compile(
    r"(?:\s*,\s*(?:(?:or|and)\s+)?|\s+(?:or|and)\s+)(?:in\s+)?"
)
NON_DESTINATION_CONTEXT = re.compile(
    r"\b(?:students?|applicants?|citizens?|residents?|live|living|reside|residing)"
    r"\s+(?:(?:currently|based)\s+)*$"
)
SOFT_FUNDING = re.compile(
    r"\b(?:prefer(?:red|ably)?|ideally|prioriti[sz]e|open to|include|including|"
    r"also (?:accept|consider)|consider(?:ing)?)\s+(?:some\s+)?$"
)
FUNDING_PATTERN = re.compile(
    r"\b(?:"
    r"(?P<full>full(?:y)?[ -]+(?:funded|funding)|"
    r"full(?:y)?(?=\s+(?:and|or)\s+partial(?:ly)?[ -]+(?:funded|funding)))|"
    r"(?P<partial>partial(?:ly)?[ -]+(?:funded|funding)|"
    r"partial(?:ly)?(?=\s+(?:and|or)\s+full(?:y)?[ -]+(?:funded|funding)))"
    r")\b"
)
FUNDING_TYPES = {
    "full": FundingType.FULLY_FUNDED,
    "partial": FundingType.PARTIALLY_FUNDED,
}
FUNDING_LABELS = {
    FundingType.FULLY_FUNDED: "Fully funded",
    FundingType.PARTIALLY_FUNDED: "Partially funded",
}


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.translate(str.maketrans({"’": "'", "–": "-", "—": "-"}))
    return " ".join(value.split())


def _canonical_destination(label: str) -> str:
    label = _normalized(label).removeprefix("the ")
    return COUNTRY_ALIASES.get(label, label)


def _label_destination(value: str) -> str:
    return value.title().replace(" And ", " and ").replace(" Of ", " of ")


def _destination_in(record_country: str, requested: str) -> bool:
    country = _canonical_destination(record_country)
    return country in REGIONS.get(requested, {requested})


def matches_destination(record: ScholarshipRead, label: str) -> bool:
    """Use documented destinations and the same regional vocabulary as discovery."""
    requested = _canonical_destination(label)
    return any(
        _destination_in(country, requested)
        for country in record.destination_country or []
    )


def _destination_words(records: list[ScholarshipRead]) -> re.Pattern[str]:
    known = EUROPE | EU | COMMON_DESTINATIONS | REGIONS.keys() | COUNTRY_ALIASES.keys()
    known |= {
        _normalized(country)
        for record in records
        for country in record.destination_country or []
    }
    alternatives = "|".join(
        re.escape(word) for word in sorted(known, key=lambda word: (-len(word), word))
    )
    return re.compile(rf"(?:both\s+)?(?:the\s+)?(?P<name>{alternatives})\b")


def _marked_destinations(
    goal: str, locations: re.Pattern[str]
) -> list[tuple[str, PreferenceMode]]:
    found = []
    consumed = 0
    for marker in DESTINATION_MARKER.finditer(goal):
        prefix = goal[: marker.start()]
        if (
            marker.start() < consumed
            or NON_DESTINATION_CONTEXT.search(prefix)
            or re.search(r"\b(?:not|except)\s*$", prefix)
        ):
            continue
        match = locations.match(goal, marker.end())
        soft = SOFT_DESTINATION.match(marker.group()) or (
            match and SOFT_SUFFIX.match(goal, match.end())
        )
        mode = (
            "preferred" if soft and marker.group().strip() != "only in" else "required"
        )
        if match is None:
            # These markers explicitly describe a destination even outside the
            # known vocabulary. An ordinary "in" can introduce a field of study.
            if re.match(r"(?:destination|only in|to study in)\b", marker.group()):
                tail = re.split(
                    r"[.!?,;]|\b(?:for|with|including)\b",
                    goal[marker.end() :],
                    maxsplit=1,
                )[0].strip()
                if tail:
                    found.append((_canonical_destination(tail), mode))
            continue
        while match:
            found.append((_canonical_destination(match["name"]), mode))
            consumed = match.end()
            join = FOLLOWING_DESTINATION.match(goal, consumed)
            match = locations.match(goal, join.end()) if join else None
    return found


def _destination_preference(
    goal: str, records: list[ScholarshipRead]
) -> RequestPreference | None:
    found = _marked_destinations(goal, _destination_words(records))
    if not found:
        for adjective, destination in ADJECTIVE_DESTINATIONS.items():
            match = re.search(
                rf"\b{adjective}\s+(?:master'?s\s+)?(?:scholarships?|programmes?)\b",
                goal,
            )
            if match:
                soft = SOFT_DESTINATION_PREFIX.search(goal[: match.start()])
                found.append((destination, "preferred" if soft else "required"))
                break
    if not found:
        return None
    mode = "required" if any(mode == "required" for _, mode in found) else "preferred"
    values = tuple(
        dict.fromkeys(place for place, strength in found if strength == mode)
    )
    all_destinations = len(values) > 1 and bool(
        re.search(r"\b(?:in|across|within)\s+both\b", goal)
    )
    conjunction = " and " if all_destinations else " or "
    return RequestPreference(
        kind="destination",
        label=conjunction.join(_label_destination(place) for place in values),
        mode=mode,
        values=values,
        all_destinations=all_destinations,
    )


def _funding_preference(goal: str) -> RequestPreference | None:
    found = []
    for match in FUNDING_PATTERN.finditer(goal):
        preceding = goal[: match.start()]
        value = FUNDING_TYPES[match.lastgroup]
        if re.search(r"\b(?:no|not|without|exclud(?:e|ing))\s+$", preceding):
            value = next(option for option in FUNDING_LABELS if option != value)
        soft = SOFT_FUNDING.search(preceding) or SOFT_SUFFIX.match(goal, match.end())
        found.append((value, "preferred" if soft else "required"))
    if not found:
        return None
    mode = "required" if any(mode == "required" for _, mode in found) else "preferred"
    values = tuple(
        dict.fromkeys(value for value, strength in found if strength == mode)
    )
    return RequestPreference(
        kind="funding",
        label=" or ".join(FUNDING_LABELS[value] for value in values),
        mode=mode,
        values=values,
    )


def parse_preferences(
    goal: str, records: list[ScholarshipRead]
) -> list[RequestPreference]:
    """Extract conservative English destination and funding terms from a goal."""
    goal = _normalized(goal)
    return [
        preference
        for preference in (
            _destination_preference(goal, records),
            _funding_preference(goal),
        )
        if preference is not None
    ]


def _destination_evidence(
    preference: RequestPreference, record: ScholarshipRead
) -> tuple[PreferenceStatus, str]:
    countries = record.destination_country
    if not countries:
        return "unverified", "Destinations are not documented in the catalogue."
    found = tuple(
        any(_destination_in(country, value) for country in countries)
        for value in preference.values
    )
    confirmed = all(found) if preference.all_destinations else any(found)
    scope = (
        "a programme destination" if len(countries) == 1 else "programme destinations"
    )
    return (
        "confirmed" if confirmed else "unmatched",
        f"The catalogue lists {', '.join(countries)} as {scope}.",
    )


def _funding_evidence(
    preference: RequestPreference, record: ScholarshipRead
) -> tuple[PreferenceStatus, str]:
    if record.funding_type == FundingType.UNKNOWN:
        return "unverified", "The catalogue has no verified funding classification."
    confirmed = record.funding_type in preference.values
    label = FUNDING_LABELS[record.funding_type].lower()
    evidence = f"The catalogue classifies this programme as {label}."
    if not confirmed and preference.mode == "preferred":
        evidence += " This remains an option under a soft preference."
    return ("confirmed" if confirmed else "unmatched"), evidence


def check_preferences(
    preferences: list[RequestPreference], record: ScholarshipRead
) -> list[PreferenceCheck]:
    checks = []
    for preference in preferences:
        check = (
            _destination_evidence
            if preference.kind == "destination"
            else _funding_evidence
        )
        status, evidence = check(preference, record)
        checks.append(
            PreferenceCheck(**preference.model_dump(), status=status, evidence=evidence)
        )
    return checks
