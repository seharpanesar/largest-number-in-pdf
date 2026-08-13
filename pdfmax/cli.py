"""Command line entry point: python -m pdfmax FILE"""

import argparse
import json
import sys

from .analyze import Finding, Report, analyze


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmax",
        description="Find the largest number in a PDF, raw and scale-adjusted.",
    )
    parser.add_argument("pdf", help="path to a PDF file")
    parser.add_argument(
        "-n", "--top", type=int, default=1, help="show this many runners-up (default 1)"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(argv)

    try:
        report = analyze(args.pdf, top=max(1, args.top))
    except FileNotFoundError:
        print(f"pdfmax: no such file: {args.pdf}", file=sys.stderr)
        return 2
    except Exception as exc:  # unreadable, encrypted, or malformed PDF
        print(f"pdfmax: could not read {args.pdf}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(_as_dict(report), indent=2))
    else:
        _print_report(report)
    return 0


def _print_report(report: Report) -> None:
    pages = "page" if report.pages == 1 else "pages"
    print(
        f"{report.path} — {report.pages} {pages}, "
        f"{report.numbers_found:,} numbers, {report.seconds:.1f}s"
    )
    if not report.largest_raw:
        print("\nNo numbers found.")
        return

    print("\nLargest raw number")
    for finding in report.largest_raw:
        print(f"  {_fmt(finding.number.value)}")
        _print_source(finding)

    print("\nLargest adjusted number")
    for finding in report.largest_adjusted:
        detail = ""
        if finding.multiplier != 1:
            detail = f"  =  {finding.number.text} × {_fmt(finding.multiplier)}"
        print(f"  {_fmt(finding.adjusted)}{detail}")
        print(f"    scale: {finding.reason}")
        _print_source(finding)


def _print_source(finding: Finding) -> None:
    print(f"    page {finding.line.page}: {finding.context()}")


def _fmt(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return f"{int(value):,}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _as_dict(report: Report) -> dict:
    return {
        "file": report.path,
        "pages": report.pages,
        "numbers_found": report.numbers_found,
        "seconds": round(report.seconds, 2),
        "largest_raw": [_finding_dict(f) for f in report.largest_raw],
        "largest_adjusted": [_finding_dict(f) for f in report.largest_adjusted],
    }


def _finding_dict(finding: Finding) -> dict:
    return {
        "value": finding.number.value,
        "adjusted_value": finding.adjusted,
        "multiplier": finding.multiplier,
        "as_written": finding.number.text,
        "scale_reason": finding.reason,
        "page": finding.line.page,
        "context": finding.context(),
    }
