"""Shared result-page interpretation.

Every jurisdiction renders the same handful of facts under slightly different
labels, so one generic reader with a broad candidate list handles them all;
providers only need to add their own quirks.
"""

from __future__ import annotations

import re
from datetime import date

from ..models import RegoResult, RegoStatus, derive_status
from ._html import extract_pairs, find_value, parse_date, strip_tags

STATUS_LABELS = (
    "registration status",
    "vehicle registration status",
    "licence status",
    "status",
    "registration",
)

EXPIRY_LABELS = (
    "registration expiry date",
    "registration expiry",
    "registration expires",
    "licence expiry date",
    "licence expiry",
    "expiry date",
    "date of expiry",
    "expires on",
    "expires",
    "expiry",
    "registration due",
    "due date",
)

MAKE_LABELS = ("make", "manufacturer", "vehicle make")
MODEL_LABELS = ("model", "vehicle model")
COLOUR_LABELS = ("colour", "color", "primary colour", "vehicle colour")
BODY_LABELS = ("body type", "bodytype", "body", "vehicle type", "type")
CLASS_LABELS = ("vehicle class", "class", "registration class")
CTP_LABELS = ("ctp insurer", "ctp insurance provider", "ctp provider", "insurer")

# Deciding "the registry has no such plate" is a negative answer that can set off
# an automation, so the evidence is split into two tiers.
#
# Tier A talks about the *search* — a page only says these things after really
# looking, so they stand on their own.
DEFINITIVE_NOT_FOUND_PATTERNS = (
    r"no records? (?:were |was )?found",
    r"no matching (?:vehicle|record|registration|result)",
    r"no (?:vehicle|result)s? (?:were |was )?found",
    r"(?:could|can) ?not be found",
    r"we (?:could not|couldn't|cannot|can't) find",
    r"unable to (?:find|locate)",
    r"plate (?:number )?(?:is )?not (?:valid|found|recognised|recognized)",
    r"no details (?:are )?available for",
)

# Tier B talks about *registration state*. The same words turn up in help text
# and outage notices, so they only count when the page also shows the plate we
# asked about — proof that a search really ran.
CORROBORATED_NOT_FOUND_PATTERNS = (
    r"not (?:currently )?registered",
    r"no current registration",
    r"unregistered",
)

# Pages that are telling us the service is broken, not answering the question.
OUTAGE_PATTERNS = (
    r"service (?:is )?(?:currently )?unavailable",
    r"temporarily unavailable",
    r"try again later",
    r"under maintenance",
    r"scheduled outage",
    r"an error (?:has )?occurred",
    r"something went wrong",
)

_DEFINITIVE_RE = re.compile("|".join(DEFINITIVE_NOT_FOUND_PATTERNS), re.I)
_CORROBORATED_RE = re.compile("|".join(CORROBORATED_NOT_FOUND_PATTERNS), re.I)
_OUTAGE_RE = re.compile("|".join(OUTAGE_PATTERNS), re.I)

# Wording that means "this page is telling us the registration is fine", used
# when a service reports status in prose instead of in a labelled field.
_POSITIVE_RE = re.compile(
    r"\b(currently registered|registration is current|is registered|"
    r"registered until|unexpired|current registration)\b",
    re.I,
)

def looks_like_outage(text: str) -> bool:
    """Return True when the page is reporting a fault rather than an answer."""
    return bool(_OUTAGE_RE.search(text))


def looks_not_found(text: str, plate: str = "") -> bool:
    """Return True when the page really says the plate is unknown.

    A phrase about registration state only counts when the plate we searched
    for is echoed back, so an outage notice or a paragraph of help text can
    never be read as "this vehicle is not registered".
    """
    if looks_like_outage(text):
        return False
    if _DEFINITIVE_RE.search(text):
        return True
    if not plate or not _CORROBORATED_RE.search(text):
        return False
    return plate.upper() in re.sub(r"[^A-Z0-9]", "", text.upper())


def parse_result_page(
    html: str,
    *,
    plate: str,
    jurisdiction: str,
    today: date,
    default_registered: bool = True,
) -> RegoResult:
    """Turn a jurisdiction's result page into a :class:`RegoResult`.

    ``default_registered`` says whether the service returning a record at all
    implies a live registration. It is True for the services that only return a
    record for registered vehicles, and False where a record is returned
    regardless of status.
    """
    pairs = extract_pairs(html)
    text = strip_tags(html)

    expiry = parse_date(find_value(pairs, *EXPIRY_LABELS))
    raw_status = find_value(pairs, *STATUS_LABELS)

    # A "no record" page usually carries neither an expiry nor a status, so
    # only trust the phrase when the page really is empty of facts.
    if expiry is None and not raw_status and looks_not_found(text, plate):
        return RegoResult(
            status=RegoStatus.NOT_FOUND,
            plate=plate,
            jurisdiction=jurisdiction,
            message=_first_match(text),
        )

    if expiry is None and not raw_status:
        # Last resort: a date somewhere near the word "expir".
        expiry = _expiry_near_keyword(text)

    if expiry is None and not raw_status:
        if _POSITIVE_RE.search(text):
            return RegoResult(
                status=RegoStatus.REGISTERED,
                plate=plate,
                jurisdiction=jurisdiction,
                message=_first_match(text),
            )
        return RegoResult.unknown(
            plate,
            jurisdiction,
            "no_result_fields",
            message="The page loaded but contained no registration details.",
        )

    status = derive_status(
        raw_status=raw_status,
        expiry=expiry,
        today=today,
        default_registered=default_registered,
    )

    return RegoResult(
        status=status,
        plate=plate,
        jurisdiction=jurisdiction,
        expiry=expiry,
        make=_clean(find_value(pairs, *MAKE_LABELS)),
        model=_clean(find_value(pairs, *MODEL_LABELS)),
        colour=_clean(find_value(pairs, *COLOUR_LABELS)),
        body_type=_clean(find_value(pairs, *BODY_LABELS)),
        vehicle_class=_clean(find_value(pairs, *CLASS_LABELS)),
        ctp_insurer=_clean(find_value(pairs, *CTP_LABELS)),
        message=raw_status,
    )


def _clean(value: str | None) -> str | None:
    """Drop placeholder values services use for "nothing here"."""
    if value is None:
        return None
    cleaned = value.strip(" \t-\u2013\u2014\u00a0")
    if not cleaned or cleaned.lower() in ("n/a", "na", "none", "not applicable", "-"):
        return None
    return cleaned[:100]


def _expiry_near_keyword(text: str) -> date | None:
    """Find a date on the same line as an expiry word."""
    for line in text.split("\n"):
        if re.search(r"expir|due|valid to|valid until", line, re.I):
            found = parse_date(line)
            if found is not None:
                return found
    return None


def _first_match(text: str) -> str | None:
    """Return the sentence that triggered a not-found decision."""
    match = _DEFINITIVE_RE.search(text) or _CORROBORATED_RE.search(text)
    if not match:
        return None
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    line = text[line_start : line_end if line_end != -1 else len(text)]
    return line.strip()[:200] or None
