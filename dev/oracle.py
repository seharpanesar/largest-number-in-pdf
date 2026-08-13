"""Dev-only verification oracle. NOT part of the solution — see README.

Asks Claude to independently find the largest raw and scale-adjusted value on
each page, then diffs that against what pdfmax computed for the same page.
Disagreements are where the bugs are.

Two deliberate choices keep the check honest:
  * Page text comes from PyMuPDF, not the pdfplumber path pdfmax uses, so an
    extraction bug in one does not hide itself in the other.
  * The model is never told pdfmax's answer, so it cannot anchor on it.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python dev/oracle.py FY25_Air_Force_Working_Capital_Fund.pdf --yes
"""

import argparse
import concurrent.futures
import os
import sys
from typing import Optional

import anthropic
import pymupdf
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from pdfmax.extract import Line  # noqa: E402
from pdfmax.numbers import find_numbers  # noqa: E402
from pdfmax.scale import ScaleIndex  # noqa: E402

MODEL = "claude-opus-5"

PROMPT = """\
Below is the text of one page from a PDF. Find the largest numerical values on it.

largest_raw: the greatest value that literally appears as a numeral, ignoring any
scale wording. Count plain integers even when they read as a year (2025) or a page
number — those are still numbers on the page. Exclude only strings that are
identifiers rather than quantities: phone numbers, dates like 1/15/2024, program or
part codes (0708055F), version numbers like 1.2.3, digits glued to letters with no
space (FY2025, AO54R6 — but "FY 2025" with a space does count as 2025), and runs of
seven or more digits with no thousands separators.

largest_adjusted: the greatest value after applying the page's own natural-language
scale guidance. Under a heading like "(Dollars in Millions)", a table value of 3.15
means 3150000. Inline wording like "$1.7 billion" counts too. Do NOT apply a money
scale to a row that plainly counts something else — headcounts, share counts,
quantities, hours, percentages, years.

If the page holds no real numeric values, return null for both.

<page>
{page}
</page>"""


class PageFinding(BaseModel):
    largest_raw: Optional[float]
    largest_adjusted: Optional[float]
    as_written: str
    scale_note: str
    reasoning: str


def pdfmax_page_maxima(path: str):
    """What pdfmax concludes for each page, using its own extraction path."""
    from pdfmax.extract import read_lines

    lines, _ = read_lines(path)
    scales = ScaleIndex(lines)
    per_page: dict[int, tuple[float, float]] = {}
    for line in lines:
        for number in find_numbers(line.text):
            multiplier, _ = scales.resolve(number, line)
            raw, adjusted = per_page.get(line.page, (float("-inf"),) * 2)
            per_page[line.page] = (
                max(raw, number.value),
                max(adjusted, number.value * multiplier),
            )
    return per_page


def page_texts(path: str) -> dict[int, str]:
    """Independent extraction — PyMuPDF, not the pdfplumber path pdfmax uses."""
    document = pymupdf.open(path)
    return {i: page.get_text() for i, page in enumerate(document, start=1)}


def ask(client: anthropic.Anthropic, page: int, text: str, effort: str):
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": effort},
        output_format=PageFinding,
        messages=[{"role": "user", "content": PROMPT.format(page=text)}],
    )
    if response.stop_reason == "refusal":
        return page, None
    return page, response.parsed_output


def close_enough(ours: float, theirs: Optional[float]) -> bool:
    if theirs is None:
        return ours <= 0
    if ours == theirs:
        return True
    return abs(ours - theirs) <= 0.01 * max(abs(ours), abs(theirs))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify pdfmax against Claude, page by page.")
    parser.add_argument("pdf")
    parser.add_argument("--pages", type=int, default=0, help="limit to the first N pages")
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh"])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    args = parser.parse_args()

    texts = page_texts(args.pdf)
    if args.pages:
        texts = {p: t for p, t in texts.items() if p <= args.pages}
    texts = {p: t for p, t in texts.items() if any(c.isdigit() for c in t)}

    tokens = sum(len(t) for t in texts.values()) // 4
    print(f"{len(texts)} pages with digits, ~{tokens:,} input tokens (~${tokens / 1e6 * 5:.2f} on {MODEL})")
    if not args.yes and input("proceed? [y/N] ").strip().lower() != "y":
        return 1

    ours = pdfmax_page_maxima(args.pdf)
    client = anthropic.Anthropic()
    findings = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(ask, client, p, t, args.effort) for p, t in texts.items()]
        for done, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            page, finding = future.result()
            findings[page] = finding
            print(f"\r  {done}/{len(futures)} pages checked", end="", flush=True)
    print()

    disagreements = 0
    for page in sorted(findings):
        finding = findings[page]
        if finding is None:
            print(f"\np{page}: model declined to answer")
            continue
        our_raw, our_adjusted = ours.get(page, (0.0, 0.0))
        raw_ok = close_enough(our_raw, finding.largest_raw)
        adjusted_ok = close_enough(our_adjusted, finding.largest_adjusted)
        if raw_ok and adjusted_ok:
            continue
        disagreements += 1
        print(f"\np{page}")
        if not raw_ok:
            print(f"  raw       pdfmax={our_raw:>20,.2f}   claude={finding.largest_raw}")
        if not adjusted_ok:
            print(f"  adjusted  pdfmax={our_adjusted:>20,.2f}   claude={finding.largest_adjusted}")
        print(f"  as written: {finding.as_written}   scale: {finding.scale_note}")
        print(f"  {finding.reasoning}")

    print(f"\n{len(findings) - disagreements}/{len(findings)} pages agree; {disagreements} to review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
