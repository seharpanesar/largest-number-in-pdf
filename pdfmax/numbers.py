"""Pull numeric literals out of a line of text.

The hard part is not finding digits, it is ignoring digits that are not
quantities: part numbers, fiscal-year labels, dates, and the garbled tokens
that overlapping text in a PDF produces.
"""

import re
from dataclasses import dataclass
from typing import List, Tuple

Span = Tuple[int, int]

_NUMBER_RE = re.compile(
    r"""
    (?<![\d.,])                       # do not start mid-number
    (?:
        \d{1,3}(?:,\d{3})+(?:\.\d+)?  # grouped thousands: 1,234  1,234,567.89
      | \d*\.\d+                      # decimal, with or without a leading digit
      | \d+                           # plain integer: 35110
    )
    (?!\d)                            # ...and must not run into more digits
    """,
    re.VERBOSE,
)

# Spans that look numeric but are not quantities. A number overlapping one of
# these is discarded.
_MASKS = [
    re.compile(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}"),  # dates: 1/15/2024, 2024-01-15
    re.compile(r"\d{3}[-.]\d{3}[-.]\d{4}"),  # phone numbers: 555-867-5309
    re.compile(r"\(\d{3}\)\s*\d{3}[-.\s]\d{4}"),  # phone numbers: (555) 867-5309
    re.compile(r"\d+(?:\.\d+){2,}"),  # versions and outline numbering: 1.2.3
    re.compile(r"[A-Za-z][\w-]*\d[\w-]*"),  # FY2025, PE-123, AO54R6
    re.compile(r"\d[\w-]*[A-Za-z][\w-]*"),  # 0708055F, 12A, 3rd
    re.compile(r"\d+(?:-\d+){2,}"),  # hyphen-joined runs: 2019-02-26-101520-300
    re.compile(r"\b(?:project|element|contract)\s+\d{4,}\b", re.I),  # "Project 675329"
    re.compile(r"(?:https?://|www\.)\S+"),  # URLs, which are full of digits
    re.compile(r"\S+\.(?:gov|com|org|net|edu|int|mil)\b\S*"),
]

# "$5M" / "$1.5 B" is unambiguous enough to keep, so it is exempted from the
# masks above. A bare "5M" is not: a lone M is often a column marker.
_CURRENCY_SUFFIX_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s?[KMBT]\b")

_PERCENT_RE = re.compile(r"\s*(?:%|percent\b|pct\b)", re.IGNORECASE)

# A long run of digits carrying no separator is an identifier rather than a
# quantity — a phone number, an EIN, an account number, or text that overlapped
# during extraction. Values this large get thousands separators in practice.
_UNSEPARATED_IDENTIFIER_DIGITS = 7
_CURRENCY_SYMBOLS = "$£€¥"


@dataclass(frozen=True)
class Number:
    value: float
    text: str  # exactly as written, e.g. "30,704.1"
    start: int  # offset of `text` within its line
    end: int
    is_percent: bool


def find_numbers(text: str) -> List[Number]:
    blocked = _blocked_spans(text)
    found = []
    for match in _NUMBER_RE.finditer(text):
        span = match.span()
        if any(_overlaps(span, b) for b in blocked):
            continue
        literal = match.group()
        if _is_identifier_like(literal, text, span[0]):
            continue
        value = float(literal.replace(",", ""))
        if _is_negated(text, span):
            value = -value
        found.append(
            Number(
                value=value,
                text=literal,
                start=span[0],
                end=span[1],
                is_percent=bool(_PERCENT_RE.match(text, span[1])),
            )
        )
    return found


def _blocked_spans(text: str) -> List[Span]:
    exempt = [m.span() for m in _CURRENCY_SUFFIX_RE.finditer(text)]
    spans = []
    for pattern in _MASKS:
        for match in pattern.finditer(text):
            if not any(_contains(e, match.span()) for e in exempt):
                spans.append(match.span())
    return spans


def _is_identifier_like(literal: str, text: str, start: int) -> bool:
    """Reject digit runs that are labels rather than amounts."""
    if len(literal) > 1 and literal[0] == "0" and "." not in literal:
        return True  # zero-padded, e.g. '0708055'
    if literal.isdigit() and len(literal) >= _UNSEPARATED_IDENTIFIER_DIGITS:
        # A currency symbol says the author meant it as an amount.
        return not (start and text[start - 1] in _CURRENCY_SYMBOLS)
    return False


# Financial tables write minus as a hyphen, a true minus sign, or an en dash.
_MINUS_SIGNS = "-\u2212\u2013"


def _is_negated(text: str, span: Span) -> bool:
    """Accounting notation: (46.6) and -46.6 both mean negative."""
    start, end = span
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    if before == "(" and after == ")":
        return True
    if before not in _MINUS_SIGNS or not before:
        return False
    # "770-778" is a page range, not a negative number.
    return start < 2 or not text[start - 2].isdigit()


def _overlaps(a: Span, b: Span) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _contains(outer: Span, inner: Span) -> bool:
    return outer[0] <= inner[0] and inner[1] <= outer[1]
