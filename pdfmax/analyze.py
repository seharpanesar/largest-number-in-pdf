"""Tie the pieces together: PDF in, largest raw and adjusted values out."""

import time
from dataclasses import dataclass
from typing import List

from .extract import Line, read_lines
from .numbers import Number, find_numbers
from .scale import ScaleIndex


@dataclass(frozen=True)
class Finding:
    number: Number
    line: Line
    multiplier: float
    reason: str

    @property
    def adjusted(self) -> float:
        return self.number.value * self.multiplier

    def context(self, width: int = 120) -> str:
        """The number's line, trimmed to a window around the number itself."""
        text = self.line.text
        if len(text) <= width:
            return text
        start = max(0, self.number.start - width // 2)
        end = min(len(text), start + width)
        snippet = text[start:end]
        return ("..." if start else "") + snippet + ("..." if end < len(text) else "")


@dataclass
class Report:
    path: str
    pages: int
    numbers_found: int
    seconds: float
    largest_raw: List[Finding]
    largest_adjusted: List[Finding]


def analyze(path: str, top: int = 1) -> Report:
    started = time.time()
    lines, page_count = read_lines(path)
    scales = ScaleIndex(lines)

    findings: List[Finding] = []
    for line in lines:
        for number in find_numbers(line.text):
            multiplier, reason = scales.resolve(number, line)
            findings.append(Finding(number, line, multiplier, reason))

    return Report(
        path=path,
        pages=page_count,
        numbers_found=len(findings),
        seconds=time.time() - started,
        largest_raw=_best(findings, lambda f: f.number.value, top),
        largest_adjusted=_best(findings, lambda f: f.adjusted, top),
    )


def _best(findings: List[Finding], key, top: int) -> List[Finding]:
    """Top findings by `key`, collapsing repeats of the same value on a page."""
    ranked = sorted(findings, key=key, reverse=True)
    best, seen = [], set()
    for finding in ranked:
        marker = (round(key(finding), 6), finding.line.page)
        if marker in seen:
            continue
        seen.add(marker)
        best.append(finding)
        if len(best) == top:
            break
    return best
