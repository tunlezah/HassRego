"""Small dependency-free helpers for reading government result pages.

Every jurisdiction presents its answer as label/value pairs — in a table, a
definition list, or as "Label: value" text. Extracting all of those into one
normalised mapping and then looking labels up fuzzily survives a site restyle
far better than CSS selectors do, and needs nothing outside the standard
library.
"""

from __future__ import annotations

import re
from datetime import date
from html import unescape
from html.parser import HTMLParser

_WS = re.compile(r"\s+")
_TAG = re.compile(r"<[^>]+>")
_DROP_BLOCKS = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.S | re.I)
_BLOCK_TAGS = {
    "br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "td", "th", "dt", "dd", "section", "article",
}


def strip_tags(html: str) -> str:
    """Return the visible text of an HTML fragment, whitespace collapsed."""
    text = _DROP_BLOCKS.sub(" ", html)
    # Keep block boundaries so "Label</td><td>Value" does not become one word.
    text = re.sub(r"<\s*(" + "|".join(_BLOCK_TAGS) + r")\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"</\s*(" + "|".join(_BLOCK_TAGS) + r")\s*>", "\n", text, flags=re.I)
    text = _TAG.sub(" ", text)
    text = unescape(text)
    lines = [_WS.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def normalise_key(label: str) -> str:
    """Reduce a label to comparable form: lowercase alphanumerics only."""
    return re.sub(r"[^a-z0-9]", "", label.lower())


class _PairParser(HTMLParser):
    """Collect table rows, definition lists and label elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pairs: list[tuple[str, str]] = []
        self._stack: list[str] = []
        self._cells: list[str] = []
        self._buf: list[str] = []
        self._capture = False
        self._pending_label: str | None = None
        self._skip_depth = 0

    # -- capture helpers ----------------------------------------------------
    def _flush(self) -> str:
        text = _WS.sub(" ", "".join(self._buf)).strip()
        self._buf = []
        return text

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        self._stack.append(tag)
        if tag == "tr":
            self._cells = []
        if tag in ("td", "th", "dt", "dd", "label"):
            self._buf = []
            self._capture = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in ("td", "th"):
            self._cells.append(self._flush())
            self._capture = False
        elif tag == "tr":
            # A two-cell row is a label/value pair; wider rows are data tables.
            if len(self._cells) == 2:
                self.pairs.append((self._cells[0], self._cells[1]))
            self._cells = []
        elif tag in ("dt", "label"):
            self._pending_label = self._flush()
            self._capture = False
        elif tag == "dd":
            value = self._flush()
            self._capture = False
            if self._pending_label:
                self.pairs.append((self._pending_label, value))
                self._pending_label = None
        if self._stack and tag in self._stack:
            while self._stack:
                if self._stack.pop() == tag:
                    break

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._capture:
            self._buf.append(data)


def extract_pairs(html: str) -> dict[str, str]:
    """Return every label/value pair found on the page, keyed normalised.

    Later occurrences do not overwrite earlier ones, because result pages tend
    to repeat headings in footers and help text.
    """
    parser = _PairParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass

    pairs: dict[str, str] = {}
    for label, value in parser.pairs:
        key = normalise_key(label)
        if key and value and key not in pairs:
            pairs[key] = value.strip()

    # "Label: value" runs in plain text, which several sites use for the
    # status line itself.
    for line in strip_tags(html).split("\n"):
        if ":" not in line or len(line) > 200:
            continue
        label, _, value = line.partition(":")
        key = normalise_key(label)
        value = value.strip()
        if key and value and key not in pairs:
            pairs[key] = value
    return pairs


def find_value(pairs: dict[str, str], *candidates: str) -> str | None:
    """Look a label up, exact-first then by substring, in candidate order."""
    wanted = [normalise_key(c) for c in candidates]
    for key in wanted:
        if key in pairs:
            return pairs[key]
    for key in wanted:
        for have, value in pairs.items():
            if key and key in have:
                return value
    return None


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_PATTERNS = (
    # 2026-02-01 / 2026/02/01
    (re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b"), ("y", "m", "d")),
    # 01/02/2026 and 01-02-2026 — Australian day-first order
    (re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b"), ("d", "m", "y")),
    # 01 Feb 2026 / 1 February 2026
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})\b"), ("d", "M", "y")),
    # Feb 01 2026
    (re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b"), ("M", "d", "y")),
    # 01/02/26 — two digit year, assumed 2000s
    (re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2})\b"), ("d", "m", "yy")),
)


def parse_date(text: str | None) -> date | None:
    """Parse the date formats these services use. Day-first, as in Australia."""
    if not text:
        return None
    for pattern, order in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        parts = dict(zip(order, match.groups(), strict=True))
        try:
            if "M" in parts:
                month = _MONTHS.get(parts["M"][:3].lower())
                if month is None:
                    continue
            else:
                month = int(parts["m"])
            year = int(parts["y"]) if "y" in parts else 2000 + int(parts["yy"])
            return date(year, month, int(parts["d"]))
        except (ValueError, KeyError):
            continue
    return None
