"""Literal stipend observations with explicit currency, scope, and provenance."""

import re
from datetime import date
from decimal import Decimal
from itertools import combinations
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PaymentPeriod = Literal["month", "year", "term", "one_time"]
PaymentScope = Literal["academic_terms", "summer", "academic_year"]
AmountQualifier = Literal["exact", "up_to", "at_least"]
ConflictStatus = Literal[
    "distinct_cycles", "same_cycle_conflict", "unresolved_time_scope"
]

_SPACE = r"[ \t\u00a0\u202f]"
_CURRENCY_CODES = (
    "USD|CAD|EUR|GBP|AUD|NZD|HKD|SGD|CHF|TRY|TL|INR|JPY|CNY|RMB|"
    "KRW|KZT|CZK|DKK|NOK|SEK|PLN|HUF|AED|QAR|SAR|MYR|THB|IDR"
)
_SYMBOLS = {
    "US$": "USD",
    "CA$": "CAD",
    "C$": "CAD",
    "AU$": "AUD",
    "A$": "AUD",
    "NZ$": "NZD",
    "HK$": "HKD",
    "S$": "SGD",
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "₩": "KRW",
    "₸": "KZT",
    "$": None,
    "¥": None,
}
_CURRENCY = "|".join(re.escape(symbol) for symbol in _SYMBOLS) + "|" + _CURRENCY_CODES
_PREFIX_PERIOD = r"monthly|annual|yearly|one[- ]time"
_STIPEND = (
    r"(?:living )?stipend|(?:living|maintenance|subsistence) allowance"
    r"|maintenance grant"
)
_PERIOD = (
    r"(?:(?:per|each|a|every) (?:calendar )?(?:month|year|academic term|term)"
    r"|per annum|monthly|annually|yearly|/(?:month|year|term))"
)
_SCOPE = (
    r"(?:(?:only )?(?:during|in) (?:the )?)(?:academic terms?|"
    r"academic year|summer (?:months?|terms?))"
)
_STIPEND_EVIDENCE = re.compile(
    rf"\b(?:(?P<label_period>{_PREFIX_PERIOD}){_SPACE}+)?"
    rf"(?:{_STIPEND}){_SPACE}*(?:(?:of|is){_SPACE}+|:{_SPACE}*)?"
    rf"(?:(?P<qualifier>up to|at least){_SPACE}+)?"
    rf"(?:(?P<prefix>{_CURRENCY}){_SPACE}*)?"
    rf"(?P<amount>[0-9]+(?:[.,\u00a0\u202f ][0-9]+)*)"
    rf"(?:{_SPACE}*(?P<suffix>{_CURRENCY_CODES})\b)?"
    rf"(?:{_SPACE}*(?P<period>{_PERIOD})\b)?"
    rf"(?:{_SPACE}+(?P<scope>{_SCOPE})\b)?",
    re.IGNORECASE,
)
_NONFACT = re.compile(
    r"\b(?:no|not|never|without|instead of|rather than|example|illustration)\b"
    r"|\bfor instance\b",
    re.IGNORECASE,
)
_AFTER_NONFACT = re.compile(
    r"^\s*(?:(?:is|was|will be|would be)\s+not\b|"
    r"(?:or|to)\s+(?:\w{3}\s+)?[0-9$€£¥₹₩₸]|"
    r"[-–−]\s*(?:\w{3}\s+)?[0-9$€£¥₹₩₸]|[.,][0-9]|\+)",
    re.IGNORECASE,
)


class FundingEvidence(BaseModel):
    """A source observation. Temporal metadata is supplied by the reviewer."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    amount: Annotated[Decimal, Field(gt=0, max_digits=16, decimal_places=2)]
    currency: str | None
    period: PaymentPeriod | None
    payment_scope: PaymentScope | None
    qualifier: AmountQualifier
    quote: Annotated[str, Field(min_length=1, max_length=400)]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]
    source_url: str
    publication_year: Annotated[int, Field(ge=1900, le=9999)] | None = None
    cycle: Annotated[str, Field(min_length=1, pattern=r"\S", max_length=80)] | None = (
        None
    )
    retrieved_on: date | None = None

    @field_validator("source_url")
    @classmethod
    def require_https_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
            or any(char.isspace() or char == "\\" for char in value)
        ):
            raise ValueError("source URL must be HTTPS without credentials or fragment")
        return value

    @model_validator(mode="after")
    def check_span(self):
        if self.end - self.start != len(self.quote):
            raise ValueError("funding quote must match span length")
        return self


class FundingConflict(BaseModel):
    """Two precisely comparable observations. Neither replaces the other."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    left: FundingEvidence
    right: FundingEvidence
    status: ConflictStatus


def _number(value: str) -> Decimal | None:
    value = value.replace("\u00a0", " ").replace("\u202f", " ")
    if re.fullmatch(r"[0-9]{1,14}(?:[.,][0-9]{1,2})?", value):
        return Decimal(value.replace(",", "."))
    if re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3}){1,3}(?:\.[0-9]{1,2})?", value):
        return Decimal(value.replace(",", ""))
    if re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{3}){1,3},[0-9]{1,2}", value):
        return Decimal(value.replace(".", "").replace(",", "."))
    if re.fullmatch(r"[0-9]{1,3}(?: [0-9]{3}){1,3}(?:[.,][0-9]{1,2})?", value):
        return Decimal(value.replace(" ", "").replace(",", "."))
    return None


def _currency(marker: str) -> str | None:
    upper = marker.upper()
    if upper in _SYMBOLS:
        return _SYMBOLS[upper]
    return {"TL": "TRY", "RMB": "CNY"}.get(upper, upper) or None


def _period(value: str) -> PaymentPeriod | None:
    if "month" in value:
        return "month"
    if any(word in value for word in ("annual", "annum", "year")):
        return "year"
    if "term" in value:
        return "term"
    if value in {"one-time", "one time"}:
        return "one_time"
    return None


def _scope(value: str) -> PaymentScope | None:
    if "summer" in value:
        return "summer"
    if "academic term" in value:
        return "academic_terms"
    if "academic year" in value:
        return "academic_year"
    return None


def extract_funding(
    text: str,
    source_url: str,
    *,
    publication_year: int | None = None,
    cycle: str | None = None,
    retrieved_on: date | None = None,
) -> tuple[FundingEvidence, ...]:
    """Extract only amounts attached to explicit stipend or maintenance clauses."""
    observations = []
    offset = 0
    for line in text.splitlines(keepends=True):
        for match in _STIPEND_EVIDENCE.finditer(line):
            start, end = match.span()
            before = re.split(r"[.;!?]", line[:start])[-1]
            if _NONFACT.search(before) or _AFTER_NONFACT.match(line[end:]):
                continue
            parts = match.groupdict("")
            if not (parts["prefix"] or parts["suffix"]):
                continue
            amount = _number(parts["amount"])
            if amount is None or amount <= 0:
                continue
            prefix = _currency(parts["prefix"])
            suffix = _currency(parts["suffix"])
            if prefix and suffix and prefix != suffix:
                continue
            if parts["prefix"] == "$" and suffix not in {
                None,
                "USD",
                "CAD",
                "AUD",
                "NZD",
                "HKD",
                "SGD",
            }:
                continue
            if parts["prefix"] == "¥" and suffix not in {None, "JPY", "CNY"}:
                continue
            label_period = _period(parts["label_period"].casefold())
            stated_period = _period(parts["period"].casefold())
            if label_period and stated_period and label_period != stated_period:
                continue
            qualifier: AmountQualifier = "exact"
            if parts["qualifier"].casefold() == "up to":
                qualifier = "up_to"
            elif parts["qualifier"].casefold() == "at least":
                qualifier = "at_least"
            observations.append(
                FundingEvidence(
                    amount=amount,
                    currency=prefix or suffix,
                    period=stated_period or label_period,
                    payment_scope=_scope(parts["scope"].casefold()),
                    qualifier=qualifier,
                    quote=match.group(),
                    start=offset + start,
                    end=offset + end,
                    source_url=source_url,
                    publication_year=publication_year,
                    cycle=cycle,
                    retrieved_on=retrieved_on,
                )
            )
        offset += len(line)
    return tuple(observations)


def funding_conflicts(
    observations: tuple[FundingEvidence, ...],
) -> tuple[FundingConflict, ...]:
    """Compare stipend amounts for a single award, preserving every observation."""
    conflicts = []
    for left, right in combinations(observations, 2):
        comparable = (
            left.currency is not None
            and left.period is not None
            and left.currency == right.currency
            and left.period == right.period
            and left.payment_scope == right.payment_scope
            and left.qualifier == right.qualifier
        )
        if not comparable or left.amount == right.amount:
            continue
        status: ConflictStatus = "unresolved_time_scope"
        if left.cycle is not None and right.cycle is not None:
            if left.cycle == right.cycle:
                status = "same_cycle_conflict"
            elif all(
                re.fullmatch(r"[0-9]{4}", cycle) for cycle in (left.cycle, right.cycle)
            ):
                # Different explicit intake years can coexist. Publication
                # dates and dates of retrieval cannot disambiguate a cycle.
                status = "distinct_cycles"
        conflicts.append(FundingConflict(left=left, right=right, status=status))
    return tuple(conflicts)
