"""Conservative checks for field-to-source relationships in verbatim excerpts.

This recognises explicit English evidence patterns. It leaves interpretation
of ambiguous phrasing and the applicability of otherwise literal evidence to
the reviewer.
"""

import re
from collections.abc import Callable
from datetime import date, datetime

from backend.app.request_preferences import COMMON_DESTINATIONS, COUNTRY_ALIASES, EUROPE

_DEGREE = r"(?:master(?:[’']s|s)?|MSc|MPhil|MA|MBA|PhD|DPhil|doctoral|bachelor[’']?s?)"
_AWARD = r"(?:scholarships?|fellowships?|awards?|aid|grants?|fund|studentships?)"
_PLACE = r"(?:the )?[A-ZÀ-ÖØ-Þ][\w’'.-]+(?: [A-ZÀ-ÖØ-Þ][\w’'.-]+){0,4}"
_ORGANIZATION = (
    r"(?:university|government|ministry|foundation|trust|council|institute|"
    r"college|department|agency|bank|commission|consortium|association)"
)
_CURRENCY = r"(?:CAD|USD|EUR|GBP|AUD|NZD|JPY|KRW|TRY|TL|CHF|[€£¥₺₩]|C\$|US\$)"
_NUMBER = r"\d+(?:[., ]\d+)*"
_PAYMENT = r"(?:stipend|allowance|maintenance|grant|subsistence|funding|award)"
_MONEY = rf"(?:{_CURRENCY}\s*{_NUMBER}|{_NUMBER}\s*{_CURRENCY})"
_DATE = (
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)? [A-Za-z]{3,9} \d{4}|"
    r"[A-Za-z]{3,9} \d{1,2}(?:st|nd|rd|th)?,? \d{4})\b"
)
_YEAR = r"(?:19|20)\d{2}"
_CYCLE = rf"{_YEAR}(?:\s*[/–-]\s*(?:{_YEAR}|\d{{2}}))?"
_NON_EVIDENCE = re.compile(
    r"ignore (?:the|all|previous|above)\b|system prompt|pretend\b|hypothetical\b|"
    r"for illustration|illustrative only|example only|fictional example",
    re.I,
)
_OMITTED = re.compile(r"\[\s*(?:\.{3}|…)\s*\]")
_CAVEAT = re.compile(
    r"\b(?:only|except|unless|however|alternatively|excluding|"
    r"subject to|academic terms?|up to|not|required if)\b",
    re.I,
)
_FUNDING_EXAMPLE = re.compile(
    r"\b(?:examples?|illustrat(?:ion|ive)|hypothetical|estimates?|sample|"
    r"for instance)\b"
    r"|\be\.g\.",
    re.I,
)
_KNOWN_DESTINATIONS = COMMON_DESTINATIONS | EUROPE | (COUNTRY_ALIASES.keys() - {"eu"})


def _looks_like_name(phrase: str) -> bool:
    return bool(re.search(r"[A-ZÀ-ÖØ-Þ].{1,100}", phrase)) and not re.fullmatch(
        rf"(?:(?:the|this|a|an)\s+)?(?:{_AWARD}|funding|financial support)",
        phrase,
        re.I,
    )


def _name(span: str, text: str) -> bool:
    # Award names are headings or the subject of an award description.
    title = re.match(
        r"^(?P<name>[^\n]{2,120}?)\s+(?:is available|is a|provides|offers|covers)\b",
        span,
        re.I,
    )
    if title and re.search(_AWARD, title["name"], re.I):
        return _looks_like_name(title["name"])
    heading = span.splitlines()[0]
    if len(heading.split()) > 16 or heading.endswith((".", "?", "!", ":")):
        return False
    if re.match(r"^(?:apply|browse|compare|learn|see|find|about)\b", heading, re.I):
        return False
    if re.search(rf"\b{_AWARD}\b", heading, re.I) and _looks_like_name(heading):
        return heading == span
    # A route heading can omit the award noun when immediately followed by the
    # application status and eligibility description.
    return (
        heading == span
        and text.startswith(span + "\n")
        and re.fullmatch(rf"[A-Z][\w -]+ in {_PLACE}", span) is not None
        and re.search(r"^closed for applications$", text, re.I | re.M) is not None
        and re.search(rf"\beligible\b[^\n]*\b{_DEGREE}\b", text, re.I) is not None
    )


def _provider(span: str, _text: str) -> bool:
    # The presence of a place or university in a title is not evidence of who
    # funds or administers the award.
    return bool(
        re.search(
            rf"(?:\b(?:funded|offered|administered|sponsored|provided) by\s+"
            rf"|^(?:award provider|scholarship provider|provider|funding body|sponsor)"
            rf"\s*:\s*)[^.!?\n]*\b{_ORGANIZATION}\b[^.!?\n]*",
            span,
            re.I,
        )
        or re.search(
            rf"\b{_ORGANIZATION}\b[^.!?\n]{{1,85}}"
            rf"\b(?:funds|administers|sponsors|offers)\s+"
            rf"(?:(?:the|this|an?)\s+|(?-i:[A-Z])[^.!?\n]{{1,60}}\s+){_AWARD}\b",
            span,
            re.I,
        )
    )


def _destination(span: str, _text: str) -> bool:
    if re.search(r"\breturn (?:to|and)\b", span, re.I):
        return False
    matches = re.finditer(
        rf"(?:(?i:\b(?:study|studies|university|universities|courses?|degrees?|"
        rf"program(?:me)?s?) (?:in|abroad in) )|(?i:^study destination:\s*))"
        rf"(?P<place>{_PLACE})\b",
        span,
    )
    return any(
        match["place"].casefold().removeprefix("the ") in _KNOWN_DESTINATIONS
        for match in matches
    )


def _degree(span: str, _text: str) -> bool:
    if re.search(
        r"\b(?:prior|previous|already|must hold|must have completed|completed)\b",
        span,
        re.I,
    ):
        return False
    return bool(
        re.search(
            rf"\b{_DEGREE}\b[^.\n]{{0,48}}\b(?:courses?|degrees?|levels?|studies|"
            r"programmes?|programs?|eligible|applicants)\b",
            span,
            re.I,
        )
        or re.search(
            rf"(?:degree level\s*:|\b(?:for|pursue|toward) (?:your |a |an )?)"
            rf"\s*{_DEGREE}\b",
            span,
            re.I,
        )
    )


def _study_fields(span: str, _text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:eligible (?:fields|subjects)|(?:eligible|supported) subject areas)"
            r"\s*(?::|include|are(?:\s+limited\s+to)?)\s+\S"
            r"|\b(?:available|eligible|supported|offered|tenable)\b[^.\n]{0,100}"
            r"\bin (?:the )?(?:fields?|subjects?|disciplines?)\s+(?:of\s+)?\S",
            span,
            re.I,
        )
    )


def _funding_type(span: str, _text: str) -> bool:
    if re.search(r"\b(?:not|unfunded|hypothetical|may|could|example)\b", span, re.I):
        return False
    if re.search(
        rf"(?:^(?:funding type\s*:\s*)?(?:fully|partially) funded[.!]?\s*$"
        rf"|\b{_AWARD}\b[^.\n]{{0,50}}\b(?:is|are) (?:fully|partially) funded\b"
        rf"|\b(?:is an?|offers? an?|provides? an?)\s+"
        rf"(?:full|partial|fully funded|partially funded) {_AWARD}\b)",
        span,
        re.I,
    ):
        return True
    tuition = re.search(
        r"\b(?:full tuition fees?|covers? (?:all |full )?(?:course|tuition) fees?)\b",
        span,
        re.I,
    )
    living = re.search(
        r"\b(?:grant for living expenses|living stipend|subsistence allowance)\b",
        span,
        re.I,
    )
    # Full tuition and living support are separate evidence components.
    return bool(tuition and living)


def _funding_amount(span: str, _text: str) -> bool:
    return bool(
        re.search(
            rf"\b{_PAYMENT}(?:\s+(?:of|is|will be|amounts? to|at|worth|pays|provides))?"
            rf"\s*:?\s*{_MONEY}",
            span,
            re.I,
        )
    ) and not re.search(
        r"\b(?:paid by students|cost of living|budget|application fee|"
        r"example|not pay(?:able)?|cannot pay|recipients spent)\b",
        span,
        re.I,
    )


def explicit_deadline(span: str) -> date | None:
    """Parse one unambiguous calendar date in an explicit closing clause."""
    dates = tuple(re.finditer(_DATE, span))
    if len(dates) != 1:
        return None
    stated = dates[0]
    match = re.search(
        r"\b(?:application (?:deadline|closing date)|no later than|"
        r"applications? (?:close[sd]?|must be (?:received|submitted))|"
        r"(?:apply|submit your application|must submit) by)\b([^.!?\n]{1,90})",
        span,
        re.I,
    )
    if match is None or not (
        match.start(1) <= stated.start() < stated.end() <= match.end(1)
    ):
        return None
    if re.search(
        r"\b(?:tentative|provisional|varies|to be confirmed)\b", match[1], re.I
    ):
        return None
    # Reject dates that are merely one endpoint of a range or loose option,
    # including shortened ranges such as "15–20 March 2027".
    before = span[match.start(1) : stated.start()]
    after = span[stated.end() : match.end(1)]
    connector = r"(?:[-–—/]|\b(?:to|through|or)\b)"
    if re.search(rf"\d(?:st|nd|rd|th)?\s*{connector}\s*$", before, re.I) or re.match(
        rf"\s*{connector}\s*(?:[A-Za-z]+\s+)?\d", after, re.I
    ):
        return None
    ordinal = re.search(r"\b(\d{1,2})(st|nd|rd|th)\b", stated[0])
    if ordinal:
        day = int(ordinal[1])
        ending = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        if 11 <= day <= 13:
            ending = "th"
        if ending != ordinal[2]:
            return None
    value = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", stated[0]).replace(",", "")
    for pattern in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def _deadline(span: str, _text: str) -> bool:
    return explicit_deadline(span) is not None


def _intake(span: str, _text: str) -> bool:
    return bool(
        re.search(
            rf"\b{_CYCLE}\s+(?:cohort|intake|academic year|entry)\b"
            rf"|\b(?:cohort|intake|academic year|entry)"
            rf"(?:\s*:\s*|\s+(?:of )?){_CYCLE}\b",
            span,
            re.I,
        )
    )


def _nationality(span: str, _text: str) -> bool:
    return bool(
        re.search(
            rf"(?i:\b(?:applicants? (?:from|must be citizens of)|"
            rf"(?:eligible|available to|open to) (?:citizens of|nationals of|"
            rf"applicants from))\s+){_PLACE}\b"
            rf"|(?i:^(?:eligible nationalities|citizenship)\s*[:\n]\s*){_PLACE}\b"
            r"|(?i:\b(?:no (?:citizenship|nationality) restrictions|"
            r"no restrictions by nationality|citizens of all countries|"
            r"all nationalities may apply)\b)",
            span,
        )
    ) and not re.search(r"\b(?:last year|past recipients|example)\b", span, re.I)


def _gpa(span: str, _text: str) -> bool:
    return bool(
        re.search(
            rf"\b(?:minimum|required) (?:GPA|CGPA|grade.point average)\s*"
            rf"(?:is|of|:)?\s*{_NUMBER}"
            rf"|\b(?:GPA|CGPA|grade.point average)\b[^.\n]{{0,40}}"
            rf"\b(?:must be|threshold(?: of)?|at least)\s+{_NUMBER}",
            span,
            re.I,
        )
    ) and not re.search(r"\b(?:typical|average recipient|example only)\b", span, re.I)


def _language(span: str, _text: str) -> bool:
    language = (
        r"(?:IELTS|TOEFL|Cambridge English|English proficiency|CEFR|language test)"
    )
    return bool(
        re.search(
            rf"\b{language}\b[^\n]{{0,90}}\b(?:required|accepted|mandatory|exempt)\b"
            rf"|\b(?:proof of|evidence of|must submit)\s+(?:an? )?{language}\b"
            rf"|\bminimum {language}(?:\s+(?:Academic|iBT|score|score of))*"
            rf"\s*(?::|of|is)?\s*{_NUMBER}"
            rf"|^language requirements?\s*:\s*[^.\n]*\b{language}\b",
            span,
            re.I,
        )
    )


def _prior_degree(span: str, _text: str) -> bool:
    return bool(
        re.search(
            rf"\b(?:must (?:already )?(?:hold|have|possess|have completed)|"
            rf"prior degree\s*:)\s*(?:an? |the )?{_DEGREE}\b"
            rf"|\b{_DEGREE}\b[^.\n]{{0,45}}\b(?:required|prerequisite) for admission\b",
            span,
            re.I,
        )
    )


_RULES: dict[str, Callable[[str, str], bool]] = {
    "scholarship_name": _name,
    "university_or_provider": _provider,
    "destination_country": _destination,
    "degree_level": _degree,
    "eligible_study_fields": _study_fields,
    "funding_type": _funding_type,
    "funding_amount": _funding_amount,
    "application_deadline": _deadline,
    "application_cycle": _intake,
    "eligible_nationalities": _nationality,
    "gpa_requirement": _gpa,
    "language_requirement": _language,
    "prior_degree_requirement": _prior_degree,
}


def _source_units(text: str) -> list[str]:
    units = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) <= 400:
            if line:
                units.append(line)
        else:
            units.extend(
                sentence
                for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", line)
                if 0 < len(sentence) <= 400
            )
    return units


def supports(field: str, quote: str, text: str, scope: str) -> bool:
    """Return whether one literal quote expresses the requested relationship."""
    rule = _RULES.get(field)
    if (
        rule is None
        or not quote.strip()
        or len(quote) > 400
        or quote not in text
        or _NON_EVIDENCE.search(quote)
        or _OMITTED.search(quote)
        or (field.startswith("funding_") and scope not in {"funding", "unclear"})
    ):
        return False
    # A shorter quote can avoid a caveat in its original sentence. Abstain
    # unless there is at least one occurrence retaining that context.
    containing = [
        unit
        for unit in _source_units(text)
        if re.search(rf"(?<!\w){re.escape(quote)}(?!\w)", unit)
        and not _NON_EVIDENCE.search(unit)
        and not (field.startswith("funding_") and _FUNDING_EXAMPLE.search(unit))
    ]
    caveats = set(_CAVEAT.findall(quote.casefold()))
    if "\n" not in quote and not any(
        set(_CAVEAT.findall(unit.casefold())) <= caveats for unit in containing
    ):
        return False
    return rule(quote, text)


def candidates(field: str, text: str, scope: str) -> tuple[str, ...]:
    """Enumerate exact spans with a supported relation for bounded model selection."""
    units = _source_units(text)
    if field in {"funding_type", "eligible_nationalities"}:
        # Permit adjacent evidence in list-style official excerpts only when
        # the joining newline itself appears in the source.
        units += [
            left + "\n" + right
            for left, right in zip(units, units[1:], strict=False)
            if (
                field == "funding_type"
                and not any(_funding_type(unit, text) for unit in (left, right))
                and _funding_type(left + "\n" + right, text)
            )
            or (field == "eligible_nationalities" and left.casefold() == "citizenship")
        ]
    return tuple(
        dict.fromkeys(unit for unit in units if supports(field, unit, text, scope))
    )
