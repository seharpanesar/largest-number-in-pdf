from pdfmax import analyze
from pdfmax.cli import main


def test_a_pdf_with_no_text_is_not_an_error(blank_pdf, capsys):
    assert main([blank_pdf]) == 0
    assert "No numbers found" in capsys.readouterr().out


def test_report_is_empty_rather_than_missing(blank_pdf):
    report = analyze(blank_pdf)
    assert report.pages == 1 and report.largest_raw == []


def test_missing_file_exits_nonzero(capsys):
    assert main(["does-not-exist.pdf"]) == 2
    assert "no such file" in capsys.readouterr().err


def test_unreadable_file_exits_nonzero(tmp_path, capsys):
    junk = tmp_path / "junk.pdf"
    junk.write_text("this is not a PDF")
    assert main([str(junk)]) == 2
    assert "could not read" in capsys.readouterr().err


def test_json_output_is_valid(blank_pdf, capsys):
    import json

    assert main([blank_pdf, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["pages"] == 1
