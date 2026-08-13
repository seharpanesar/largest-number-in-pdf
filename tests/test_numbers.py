from pdfmax.numbers import find_numbers


def values(text):
    return [n.value for n in find_numbers(text)]


def test_thousands_separators_and_decimals():
    assert values("Total 1,234,567.89 and 30704.1") == [1234567.89, 30704.1]


def test_leading_decimal_is_not_read_as_an_integer():
    assert values("Savings .5 .000") == [0.5, 0.0]


def test_accounting_parentheses_mean_negative():
    assert values("Net Operating Result (46.6)") == [-46.6]
    assert values("Delta -12.5") == [-12.5]


def test_zero_padded_identifiers_are_rejected():
    assert values("Program Element 0708055F") == []


def test_alphanumeric_identifiers_are_rejected():
    assert values("FY2025 budget PE-123 and AO54R6") == []
    assert values("Direct Appropriation1") == []


def test_dates_versions_and_phone_numbers_are_rejected():
    assert values("dated 1/15/2024") == []
    assert values("see section 1.2.3") == []
    assert values("call 555-867-5309") == []


def test_percentages_are_flagged():
    (number,) = find_numbers("On-time rate 85%")
    assert number.value == 85 and number.is_percent


def test_a_spaced_fiscal_year_still_parses_as_a_number():
    # "FY 2025" is a legitimate number token; scale.py is what declines to
    # multiply it. Only glued forms like "FY2025" are rejected outright.
    assert values("FY 2025 revenue 30,704.1") == [2025.0, 30704.1]


def test_en_dash_and_minus_sign_mean_negative():
    # Budget tables often use an en dash for negatives.
    assert values("–455,324 and −99.5") == [-455324.0, -99.5]


def test_a_dash_between_two_numbers_is_a_range_not_a_negative():
    assert values("pages 770–778") == [770.0, 778.0]


def test_grouped_numbers_do_not_swallow_following_digits():
    # "pages 770-778, 2016" once parsed as 778,201.
    assert 778201 not in values("Recognition, pages 770-778, 2016.")


def test_phone_numbers_are_rejected():
    assert values("call 555-867-5309") == []
    assert values("Fax: (202) 512-1800") == []
    assert values("Phone: 5558675309") == []


def test_long_unseparated_runs_are_treated_as_identifiers():
    # Amounts this large carry separators in practice; bare runs are EINs,
    # account numbers, or text that overlapped during extraction.
    assert values("California 94-2404110") == [94.0]
    assert values("999999 units") == [999999.0]  # six digits is still a quantity


def test_a_currency_symbol_rescues_an_unseparated_amount():
    assert values("$6000000 contract") == [6000000.0]


def test_a_number_glued_to_a_word_is_still_found():
    # Some PDFs extract without spaces. Extraction uses a tighter x_tolerance
    # to avoid this, but the parser should not compound the problem.
    assert 300000 in values("were trained for 300,000 steps")


def test_project_identifiers_are_rejected():
    assert values("RDT&E Program Element 0708055F Project 675329 to DAF") == []
