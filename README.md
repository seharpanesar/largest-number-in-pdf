# pdfmax: largest number in a PDF

Finds the greatest numerical value in a PDF, both as written ("raw") and after
applying the document's own natural-language scale guidance ("adjusted"), so
`3.15` under a heading that reads *(Dollars in Millions)* is understood as
3,150,000.

## Install and run

```bash
git clone https://github.com/seharpanesar/largest-number-in-pdf.git
cd largest-number-in-pdf
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m pdfmax FY25_Air_Force_Working_Capital_Fund.pdf
```

`-n 5` shows runners-up, `--json` emits machine-readable output. Requires Python
3.10+ for the [pdfplumber](https://github.com/jsvine/pdfplumber)
 dependency. Runtime is ~15 pages/second, memory flat regardless of length.

## Methodology

Text is extracted line by line with pdfplumber, keeping each line's page and
vertical position: position is what ties a scale note to the numbers it
actually governs. Every line then goes through three steps.

**1. Find real numbers.** Common strings in PDFs include digits but aren't
numbers: dates, phone numbers, version strings, URLs, zero-padded codes.
`pdfmax/numbers.py:find_numbers()` extracts candidates from each line;
`_blocked_spans()` and `_is_identifier_like()` filter out the bad candidates.

**2. Find scale declarations.** *Inline*: `$1,730.8 million`, `$1.5M`.
*Regional*: a note like `(Dollars in Millions)` or `($M)` as a part of a
page. To qualify as regional the note must be parenthesised, a short caption, or
use whole-document phrasing..
`pdfmax/scale.py:find_declaration()` implements this logic. inline scale words
are matched separately by `ScaleIndex._inline()`.

**3. Decide what each number means.** In order: percentages and
years are never scaled. An inline scale word beats everything else. Then the
nearest regional note above the number on its page, or the nearest below it if
none is above. then a document-wide note.
A note governs only its own page,
since these headings are repeated per page and letting one leak forward invents
multipliers on pages that never claimed them. `pdfmax/scale.py:ScaleIndex.resolve()`
implements this precedence chain, calling `_governing()` to walk the page for
the nearest note.

## How it was validated

I included some same pdfs to test against under `corpus`. It includes two large annual reports, two government
budget documents, a policy commentary report (near-numberless prose), a lengthy
security-controls reference (492 pages of identifiers), an arXiv paper, and
deliberately broken inputs: an empty PDF, a truncated one, and a text file with
a `.pdf` extension.

I created a script to use Claude's api, page by page, for that
page's largest raw and scale-adjusted value, then diffs the answer against
pdfmax's own. This gives me some idea of ground truth and performance

The diffs would be diagnosed (as it could be an issue with claude api). If it is a genuine issue, it is root caused an resolved. I used `ORACLE_LOOP.md` as prompt for claude to self correct the code base.

This caught real bugs that spot-checking missed: a table footnote scaling  
the three unrelated tables above it, and a line like `...from 2023, 2024 (in $M)` where the years themselves were getting scaled into the millions, which
is why a bare year is now excluded before any scale is applied.

See dev/ledger.md for its performance against real PDFs

Note that the Claude API is not used in pdfmax. It is only used for validation.

I also included unit tests cover number parsing and scale resolution.

## Shortcomings

- **Scoping is by region and table, never by column.** A *$ Per Barrel* column
beside a *TOTAL* column under one *(Dollars in Millions)* heading gets both
scaled.
- **A table's scale leaks into its prose.** Page 93's *(Dollars in Thousands)*
heading also scales a sentence quoting literal dollar amounts — deliberate,
since detecting prose vs. table breaks the commoner opposite case.
- **Narrow by design.** Text-based PDFs only (no OCR); US number formatting
only; a 4-digit number in 1900-2100 is always read as a year and never
scaled.