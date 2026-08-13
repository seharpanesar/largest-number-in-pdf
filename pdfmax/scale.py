"""Work out what multiplier a number carries.

Documents declare scale in two ways: inline next to the number ("$1,730.8
million") and as a note governing a region of the page ("(Dollars in
Millions)"). This module finds both and decides which one applies.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .extract import Line
from .numbers import Number

SCALE_WORDS = {
    "hundred": 1e2,
    "thousand": 1e3,
    "million": 1e6,
    "billion": 1e9,
    "trillion": 1e12,
}
SUFFIX_LETTERS = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}

_IN_SCALE_RE = re.compile(
    r"\bin\s+(hundred|thousand|million|billion|trillion)s?\b", re.IGNORECASE
)
# Inside a parenthetical the "in" is often dropped: "($ Millions)", "($M)".
# Requiring a currency symbol and no digits keeps "($5 million contract)" out.
_BARE_SCALE_RE = re.compile(
    r"^[^\d]*[$£€¥][^\d]*?\b(hundred|thousand|million|billion|trillion)s?\b[^\d]*$",
    re.IGNORECASE,
)
_SUFFIX_SCALE_RE = re.compile(r"^\s*[$£€¥]\s*(?:in\s+)?([KMBT])\s*$", re.IGNORECASE)
_SUFFIX_WORDS = {"k": "thousand", "m": "million", "b": "billion", "t": "trillion"}
_PARENTHETICAL_RE = re.compile(r"\(([^()]{0,80})\)")
_DOCWIDE_RE = re.compile(
    r"""\b(
        all \s+ (?:\w+\s+){0,2} (?:amounts|figures|values|numbers|dollars)
      | (?:amounts|figures|values|numbers|dollars) \s+ (?:are\s+)?
        (?:expressed|stated|reported|presented|shown|listed)
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)
_MONEY_RE = re.compile(r"\$|\b(?:dollars?|usd|eur|euros?|gbp|pounds?|yen)\b", re.IGNORECASE)
_HOURS_RE = re.compile(r"\bhours?\b", re.IGNORECASE)


def _unit_of(text: str) -> Optional[str]:
    """What a scale note says it is counting, if it says at all."""
    if _MONEY_RE.search(text):
        return "money"
    if _HOURS_RE.search(text):
        return "hours"
    return None

# A scale note that names money does not govern rows that plainly count
# something else — headcounts and workyears sit in the same table as dollars.
_COUNT_LABEL_RE = re.compile(
    r"""\b(
        end\s+strength | work\s?years? | man\s?years? | staff\s?years?
      | number\s+of | no\.\s*of | quantity | qty | units\s+of
      | personnel | employees | positions | headcount | fte | hours
      | shares?          # share counts, and per-share amounts, are not millions
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

# Inline scale word trailing a number: "1,730.8 million", "(3.15) billion".
_INLINE_WORD_RE = re.compile(
    r"[\s)]*\b(hundred|thousand|million|billion|trillion)s?\b", re.IGNORECASE
)
_INLINE_SUFFIX_RE = re.compile(r"\s?([KMBT])\b")

_YEAR_RE = re.compile(r"^\d{4}$")

# A short line carrying two or more period labels is a table's column header.
# Long lines are prose that happens to mention years, not headers.
_PERIOD_LABEL_RE = re.compile(r"\b(?:FY|CY)\s?\d{2,4}\b|\b(?:19|20)\d{2}\b", re.IGNORECASE)


def _is_column_header(text: str) -> bool:
    return len(text) <= 100 and len(_PERIOD_LABEL_RE.findall(text)) >= 2


def _is_header_note(text: str, note: str) -> bool:
    """Is this scale note written into a table's own column header?

    A note that labels a table's stub column comes before the period labels
    naming the data columns — `Supply Undelivered Orders ($M) FY 2023 FY 2024`.
    A sentence that trails off into `...for 2023, 2022 and 2021 (in millions):`
    puts its note last: that is a caption introducing the table, not a header.
    """
    if not _is_column_header(text):
        return False
    first_label = _PERIOD_LABEL_RE.search(text)
    return 0 <= text.find(note) < first_label.start()


@dataclass(frozen=True)
class Declaration:
    page: int
    top: float
    multiplier: float
    text: str  # the note as written, for explaining the result
    unit: Optional[str]  # "money", "hours", or None if the note doesn't say
    document_wide: bool
    table_scoped: bool  # the note sits in a table's own header line


def find_declaration(text: str) -> Optional[tuple[float, str, Optional[str], bool]]:
    """Parse a scale note out of one line, or return None.

    Returns (multiplier, note_text, unit, document_wide). A bare "in
    millions" in running prose is ignored — the note must be parenthesised, be
    a short caption, or use whole-document phrasing.
    """
    for parenthetical in _PARENTHETICAL_RE.finditer(text):
        inner = parenthetical.group(1)
        match = _IN_SCALE_RE.search(inner) or _BARE_SCALE_RE.match(inner)
        if match:
            return _build(match, inner, document_wide=False)
        suffix = _SUFFIX_SCALE_RE.match(inner)
        if suffix:
            word = _SUFFIX_WORDS[suffix.group(1).lower()]
            return SCALE_WORDS[word], inner.strip(), "money", False

    match = _IN_SCALE_RE.search(text)
    if not match:
        return None
    if _DOCWIDE_RE.search(text):
        return _build(match, text, document_wide=True)
    if len(text) <= 60:  # a caption or column header, not a sentence
        return _build(match, text, document_wide=False)
    return None


def _build(match, context: str, document_wide: bool):
    multiplier = SCALE_WORDS[match.group(1).lower()]
    return multiplier, context.strip(), _unit_of(context), document_wide


class ScaleIndex:
    """Resolves the multiplier for any number, given every line in the document."""

    def __init__(self, lines: List[Line]):
        self._by_page: Dict[int, List[Declaration]] = {}
        self._document: Optional[Declaration] = None
        self._headers: Dict[int, List[float]] = {}
        # Prose wraps: "$2,239.3" can end a line with its "million" on the next.
        self._next_line: Dict[tuple[int, float], str] = {}
        for current, following in zip(lines, lines[1:]):
            if current.page == following.page:
                self._next_line[(current.page, current.top)] = following.text
        for line in lines:
            parsed = find_declaration(line.text)
            if not parsed:
                if _is_column_header(line.text):
                    self._headers.setdefault(line.page, []).append(line.top)
                continue
            multiplier, note, unit, document_wide = parsed
            declaration = Declaration(
                line.page,
                line.top,
                multiplier,
                note,
                unit,
                document_wide,
                _is_header_note(line.text, note),
            )
            self._by_page.setdefault(line.page, []).append(declaration)
            if document_wide and self._document is None:
                self._document = declaration

    def resolve(self, number: Number, line: Line) -> tuple[float, str]:
        """Return (multiplier, human-readable reason)."""
        if number.is_percent:
            return 1.0, "percentage"

        inline = self._inline(number, line)
        if inline:
            return inline

        if _is_stray_numeral(number, line):
            return 1.0, "bare numeral on its own line (page number or footer)"

        declaration = self._governing(number, line)
        if declaration is None:
            return 1.0, "no scale declared"
        if _YEAR_RE.match(number.text) and 1900 <= number.value <= 2100:
            return 1.0, "looks like a year"
        if _wrong_unit(declaration, _row_label(number, line)):
            return 1.0, f'wrong unit: row counts something else, ignoring "{declaration.text}"'
        where = "document" if declaration.document_wide else f"page {declaration.page}"
        return declaration.multiplier, f'{where}: "{declaration.text}"'

    def _crosses_table(self, page: int, one: float, other: float) -> bool:
        """Does another table's header sit between these two lines on a page?"""
        low, high = sorted((one, other))
        return any(low < top <= high for top in self._headers.get(page, []))

    def _inline(self, number: Number, line: Line) -> Optional[tuple[float, str]]:
        text = line.text
        word = _INLINE_WORD_RE.match(text, number.end)
        if word is None and number.end == len(text.rstrip()):
            # The number ends the line; its scale word may have wrapped.
            word = _INLINE_WORD_RE.match(self._next_line.get((line.page, line.top), ""))
        if word:
            return SCALE_WORDS[word.group(1).lower()], f'inline: "{word.group().strip()}"'
        preceded_by_currency = number.start > 0 and text[number.start - 1] in "$£€¥"
        suffix = _INLINE_SUFFIX_RE.match(text, number.end)
        if preceded_by_currency and suffix:
            return SUFFIX_LETTERS[suffix.group(1)], f'inline: "{suffix.group().strip()}"'
        return None

    def _governing(self, number: Number, line: Line) -> Optional[Declaration]:
        on_page = self._by_page.get(line.page, [])
        above = [d for d in on_page if d.top <= line.top]
        if above:
            governing = above[-1]
            if governing.table_scoped and self._crosses_table(line.page, governing.top, line.top):
                return None  # a later table began, and it declared no scale
            return governing
        if on_page:
            # The note sits below the numbers (a table footnote). It still
            # governs, but only back to the top of its own table: a note buried
            # in the last table on a page says nothing about the ones above it.
            footnote = on_page[0]
            if self._crosses_table(line.page, line.top, footnote.top):
                return None
            return footnote
        return self._document


def _wrong_unit(declaration: Declaration, label: str) -> bool:
    """True when a note names one unit but the row plainly counts another."""
    if declaration.unit is None:
        return False
    match = _COUNT_LABEL_RE.search(label)
    if not match:
        return False
    # "(Hours in Thousands)" does govern the row actually labelled hours.
    return not (declaration.unit == "hours" and match.group().lower().startswith("hour"))


def _is_stray_numeral(number: Number, line: Line) -> bool:
    """A small integer alone on its line is page furniture, not a table value."""
    return (
        line.text.strip() == number.text
        and number.value == int(number.value)
        and abs(number.value) < 10_000
    )


def _row_label(number: Number, line: Line) -> str:
    """The descriptive text preceding a number on its line, e.g. a row header."""
    return line.text[: number.start]
