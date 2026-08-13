# Self-correcting loop prompt

Paste the block below to an AI agent working in this repo. It drives the
page-level oracle in `dev/oracle.py`, triages the disagreements, and fixes the
real bugs among them.

---

You are improving `pdfmax`, a tool that finds the largest number in a PDF, both
raw and adjusted for the document's own scale wording ("in millions"). Work in
this repo. Run a self-correcting loop until the stopping condition is met.

## The loop

1. Run the oracle:
   `set -a && . dev/.env && set +a && .venv/bin/python dev/oracle.py <PDF> --yes`
   It asks Claude, page by page, for that page's largest raw and adjusted value
   using independently extracted text, then prints only pages where pdfmax
   disagrees. Note the "N/M pages agree" score.
2. Triage every disagreement into exactly one bucket (rules below).
3. Fix the highest-value real bug — one per iteration, not a batch.
4. Add a regression test derived from the actual disagreeing page.
5. Verify: `.venv/bin/python -m pytest tests -q`, then re-run pdfmax over every
   PDF in `corpus/` plus the sample and confirm no headline answer regressed.
6. Append the outcome to `dev/ledger.md`, then go to 1.

## Triage: a disagreement is not automatically a bug

Assign each to one bucket and say which in your notes:

- **Tool bug.** pdfmax is wrong by its own README contract. Fix it.
- **Oracle miscalibration.** The oracle's prompt asks for something pdfmax never
  promised. Fix the *prompt*, not the parser. Real example: pdfmax counts
  `FY 2025` as the number 2,025 by design; an oracle told to exclude years
  reported 10 false disagreements on one 12-page run. Before changing any parser
  code, confirm the README actually promises the behavior the oracle expects.
- **Known limitation.** Real, understood, and documented in the README as a
  deliberate trade-off. Record it in the ledger and never revisit it.
- **Oracle error.** The model misread the page. Verify against the page text
  yourself before believing either side.

Do not weaken the oracle prompt to make disagreements disappear. Editing it is
legitimate only to correct a genuine mismatch with pdfmax's documented contract,
and you must state which README sentence justifies the edit.

## Bar for a fix

- Fix the underlying rule, not the instance. Adding the string "items managed"
  to a keyword list because one page has an "Items Managed" row is not a fix —
  it patches one document. Ask what structural signal distinguishes this case,
  and encode that. Unseen documents are the target.
- A fix must not regress any corpus answer. If it does, you have found a second
  bug hiding behind the first — fix both or revert.
- Prefer fixing extraction over compensating downstream.
- Fixes that only ever lower the adjusted maximum are cheap to get wrong; fixes
  that raise it need more scrutiny.
- Keep the code readable. This is a take-home judged on readability; a rule you
  cannot explain in two sentences in the README is too clever.
- Update the README when behavior or limitations change.

## Stop when any of these is true

- Every remaining disagreement is a known limitation or an oracle error.
- An iteration produces no fix that passes the bar above.
- Three consecutive iterations fail to raise the agreement score.
- You have run 6 iterations, or spent more than $5 of API budget
  (a 112-page pass costs roughly $0.25).

Then report: the score at each iteration, each bug found and the rule that fixed
it, and the remaining disagreements with the bucket you assigned.

## Notes

- `dev/` is gitignored — the oracle and the API key must never be committed. The
  shipped tool makes no network calls and has one dependency (pdfplumber).
- Use `--pages N` to re-check a specific range cheaply instead of a full pass.
- Commit each accepted fix separately, with the disagreement that motivated it
  in the message.
