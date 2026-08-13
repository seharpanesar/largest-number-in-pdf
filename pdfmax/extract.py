"""Read a PDF into an ordered stream of text lines.

Each line keeps its page number and vertical position, which is what lets
scale.py decide which "(Dollars in Millions)" note governs which numbers.
"""

from dataclasses import dataclass
from typing import List

import pdfplumber


@dataclass(frozen=True)
class Line:
    page: int  # 1-indexed
    top: float  # distance from the top of the page, in points
    text: str


def read_lines(path: str) -> tuple[List[Line], int]:
    """Return (lines, page_count). Pages with no extractable text are skipped."""
    lines: List[Line] = []
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for page_no, page in enumerate(pdf.pages, start=1):
            # x_tolerance=2 rather than the default 3: some documents (LaTeX
            # papers, older 10-Ks) otherwise extract as "trainedfor300,000",
            # gluing values to words so they read as identifiers and get dropped.
            for raw in page.extract_text_lines(return_chars=False, x_tolerance=2):
                text = raw["text"].strip()
                if text:
                    lines.append(Line(page_no, float(raw["top"]), text))
            page.flush_cache()  # keep memory flat on large documents
    return lines, page_count
