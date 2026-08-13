"""End-to-end check against the sample budget document."""

import os

import pytest

from pdfmax import analyze

SAMPLE = os.path.join(
    os.path.dirname(__file__), os.pardir, "FY25_Air_Force_Working_Capital_Fund.pdf"
)

pytestmark = pytest.mark.skipif(
    not os.path.exists(SAMPLE), reason="sample document not present"
)


@pytest.fixture(scope="module")
def report():
    return analyze(SAMPLE)


def test_largest_raw_number(report):
    # Prose on page 93: "costing between $250,000 and $6,000,000".
    finding = report.largest_raw[0]
    assert finding.number.value == 6_000_000
    assert finding.line.page == 93


def test_largest_adjusted_number(report):
    # Page 13, "(Dollars in Millions)": Total Revenue FY 2025 = 30,704.1.
    finding = report.largest_adjusted[0]
    assert finding.adjusted == pytest.approx(30_704_100_000)
    assert finding.multiplier == 1e6
    assert finding.line.page == 13


def test_headcount_on_a_dollars_page_is_not_scaled(report):
    # Civilian End Strength 35,110 shares page 13 with the dollar figures;
    # scaling it would make it the (wrong) document maximum.
    assert report.largest_adjusted[0].adjusted < 35_110 * 1e6


def test_runs_well_within_the_one_minute_budget(report):
    assert report.seconds < 30
