import pytest

from pdfmax.extract import Line
from pdfmax.numbers import find_numbers
from pdfmax.scale import ScaleIndex, find_declaration


def resolve(lines, page, top, text, which=-1):
    """Resolve the multiplier for one number on `text` (the last one by default)."""
    line = Line(page, top, text)
    index = ScaleIndex(lines + [line])
    return index.resolve(find_numbers(text)[which], line)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("(Dollars in Millions)", 1e6),
        ("COST ($ IN MILLIONS)", 1e6),
        ("(Hours in Thousands)", 1e3),
        ("(In Thousands)", 1e3),
        ("Amounts in billions", 1e9),
        ("All figures in this report are in thousands unless noted otherwise.", 1e3),
    ],
)
def test_scale_notes_are_recognised(text, expected):
    assert find_declaration(text)[0] == expected


def test_prose_mentioning_a_scale_word_is_not_a_declaration():
    prose = (
        "The program is expected to result in millions of dollars of savings "
        "over the life of the contract, according to the estimate."
    )
    assert find_declaration(prose) is None


def test_page_note_applies_to_numbers_below_it():
    header = Line(3, 100.0, "(Dollars in Millions)")
    multiplier, _ = resolve([header], 3, 200.0, "Total Revenue 30,704.1")
    assert multiplier == 1e6


def test_page_note_does_not_leak_onto_other_pages():
    header = Line(3, 100.0, "(Dollars in Millions)")
    multiplier, _ = resolve([header], 4, 200.0, "Headcount 512")
    assert multiplier == 1


def test_footnote_below_a_table_still_applies():
    note = Line(3, 500.0, "(Dollars in Thousands)")
    multiplier, _ = resolve([note], 3, 200.0, "Total 1,200.0")
    assert multiplier == 1e3


def test_a_footnote_does_not_reach_back_over_an_earlier_table():
    # Page 27 of the sample stacks four tables; "(Hours in Thousands)" is a row
    # label in the last of them and must not scale the headcounts two tables up.
    manpower = Line(27, 235.0, "CSAG Manpower Resources FY 2023 FY 2024 FY 2025")
    hours = Line(27, 335.0, "Maintenance Direct Production Earned Hours FY 2023 FY 2024 FY 2025")
    note = Line(27, 356.0, "(Hours in Thousands) 24,413 25,661 23,774")
    multiplier, _ = resolve(
        [manpower, hours, note], 27, 268.0, "Civilian Full Time Equivalents 28,858"
    )
    assert multiplier == 1


def test_document_wide_note_applies_everywhere():
    note = Line(1, 50.0, "All dollar amounts in this document are in millions.")
    multiplier, _ = resolve([note], 42, 300.0, "Total 25.5")
    assert multiplier == 1e6


def test_inline_word_beats_the_page_note():
    header = Line(3, 100.0, "(Dollars in Thousands)")
    multiplier, reason = resolve([header], 3, 200.0, "ending FY 2025 with $1,730.8 million")
    assert multiplier == 1e6 and "inline" in reason


def test_currency_letter_suffix():
    multiplier, _ = resolve([], 1, 10.0, "a contract worth $1.5M")
    assert multiplier == 1e6


def test_bare_letter_suffix_is_ignored():
    # A lone M in a table is far more often a column marker than "million".
    multiplier, _ = resolve([], 1, 10.0, "Military End Strength M 12,472")
    assert multiplier == 1


def test_percentages_are_never_scaled():
    header = Line(3, 100.0, "(Dollars in Millions)")
    multiplier, _ = resolve([header], 3, 200.0, "Defect rate 3.15%")
    assert multiplier == 1


def test_years_are_never_scaled():
    header = Line(3, 100.0, "(Dollars in Millions)")
    multiplier, _ = resolve([header], 3, 200.0, "FY 2025 column")
    assert multiplier == 1


def test_money_note_does_not_scale_a_headcount_row():
    header = Line(3, 100.0, "(Dollars in Millions)")
    multiplier, reason = resolve([header], 3, 200.0, "Civilian End Strength 33,848 35,110")
    assert multiplier == 1 and "wrong unit" in reason


def test_non_money_note_scales_its_own_unit():
    # "(Hours in Thousands)" is not about money, so the count-row rule is moot.
    header = Line(3, 100.0, "(Hours in Thousands)")
    multiplier, _ = resolve([header], 3, 200.0, "Direct Labor Hours 4,150")
    assert multiplier == 1e3


def test_share_counts_are_not_scaled_as_dollars():
    # Berkshire's 10-K puts share counts under "(dollars in millions except
    # per share amounts)"; scaling them yields a $2.27 quadrillion maximum.
    header = Line(96, 100.0, "(dollars in millions except per share amounts)")
    line = "Average equivalent Class B shares outstanding 2,265,269,867"
    multiplier, reason = resolve([header], 96, 200.0, line)
    assert multiplier == 1 and "wrong unit" in reason


def test_shareholders_is_not_mistaken_for_a_share_count():
    header = Line(96, 100.0, "(dollars in millions)")
    multiplier, _ = resolve([header], 96, 200.0, "Net earnings to shareholders $ 96,223")
    assert multiplier == 1e6


@pytest.mark.parametrize("note", ["($ Millions)", "($M)", "Cash ($ Millions)", "Revenue ($M)"])
def test_a_parenthetical_may_drop_the_word_in(note):
    # "($ Millions)" and "($M)" are as common as "(Dollars in Millions)".
    assert find_declaration(note)[0] == 1e6


def test_an_amount_in_parentheses_is_not_a_scale_note():
    # The digit is what separates a note from a quoted amount.
    assert find_declaration("(a $5 million contract)") is None


def test_a_note_in_a_table_header_does_not_govern_the_next_table():
    # Page 29 of the sample: a "($M)" table is followed by a count table that
    # declares no scale of its own.
    note = Line(29, 100.0, "Supply Undelivered Orders ($M) FY 2023 FY 2024 FY 2025")
    next_table = Line(29, 200.0, "Supply Item Quantity Requirements FY 2023 FY 2024 FY 2025")
    multiplier, _ = resolve([note, next_table], 29, 300.0, "Items Managed 111,004")
    assert multiplier == 1


def test_a_note_in_a_table_header_still_governs_its_own_table():
    note = Line(29, 100.0, "Supply Undelivered Orders ($M) FY 2023 FY 2024 FY 2025")
    multiplier, _ = resolve([note], 29, 150.0, "Supply Division 5,741.3")
    assert multiplier == 1e6


def test_a_sentence_ending_in_a_note_is_a_caption_not_a_table_header():
    # Apple's 10-K introduces each table this way. The years belong to the
    # sentence, not to a header row, so the note must survive the real header
    # printed directly beneath it.
    caption = Line(42, 59.0, "The following table shows net sales for 2023, 2022 and 2021 (in millions):")
    header = Line(42, 87.0, "2023 2022")
    multiplier, _ = resolve([caption, header], 42, 143.0, "Gross property 114,599 114,457", 0)
    assert multiplier == 1e6


def test_a_standalone_caption_survives_a_later_table_header():
    # A caption on its own line governs the region, not one table.
    caption = Line(3, 90.0, "(Dollars in Thousands)")
    header = Line(3, 120.0, "Element of Cost FY 2024 FY 2025")
    multiplier, _ = resolve([caption, header], 3, 200.0, "Equipment 259,899.7")
    assert multiplier == 1e3


def test_prose_mentioning_two_years_is_not_a_table_header():
    footnote = "1 A full-year FY 2024 appropriation for this account was not enacted at the "
    footnote += "time the budget was prepared, therefore the FY 2024 amounts are annualized."
    caption = Line(13, 90.0, "(Dollars in Millions)")
    multiplier, _ = resolve([caption, Line(13, 100.0, footnote)], 13, 200.0, "Revenue 30,704.1")
    assert multiplier == 1e6


def test_an_hours_note_does_not_scale_a_headcount_row():
    header = Line(27, 100.0, "(Hours in Thousands)")
    multiplier, _ = resolve([header], 27, 200.0, "Civilian End Strength 30,389")
    assert multiplier == 1


def test_an_hours_note_does_scale_its_own_hours_row():
    header = Line(27, 100.0, "(Hours in Thousands)")
    multiplier, _ = resolve([header], 27, 200.0, "Maintenance Earned Hours 25,661")
    assert multiplier == 1e3


def test_a_page_number_is_not_scaled():
    caption = Line(96, 90.0, "(Dollars in Millions)")
    multiplier, reason = resolve([caption], 96, 700.0, "92")
    assert multiplier == 1 and "own line" in reason


def test_a_scale_word_wrapped_to_the_next_line_still_applies():
    # Prose wraps: "The upper range is $2,239.3" / "million. The difference..."
    first = Line(15, 100.0, "The upper range is $2,239.3")
    second = Line(15, 112.0, "million. The difference between the two ranges is smaller.")
    index = ScaleIndex([first, second])
    number = find_numbers(first.text)[-1]
    multiplier, reason = index.resolve(number, first)
    assert multiplier == 1e6 and "inline" in reason


def test_a_wrap_does_not_reach_across_a_page_break():
    first = Line(15, 700.0, "Total cost was 42")
    second = Line(16, 90.0, "million dollars of unrelated text on the next page.")
    index = ScaleIndex([first, second])
    number = find_numbers(first.text)[-1]
    assert index.resolve(number, first)[0] == 1
