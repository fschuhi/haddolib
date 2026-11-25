"""
tests/test_common_xlsx.py -- write_xlsx: the rejected-rows file writer.

This is the spec for the one thing xlsx buys over CSV for the rejected file:
ISBNs (and any digit-string) survive as TEXT cells, so the fix-and-reimport loop
can never be handed a number-mangled ISBN on the second pass. Genuine numbers
stay numeric in the same write.
"""

from openpyxl import load_workbook

from haddolib.common import write_xlsx


def test_write_xlsx_writes_header_then_rows(tmp_path) -> None:
    fieldnames = ["rejected_reason", "isbn13", "title", "pages"]
    rows = [
        {"rejected_reason": "invalid_isbn13", "isbn13": "9783446195134",
         "title": "Demo", "pages": 320},
    ]
    path = tmp_path / "rej.xlsx"
    write_xlsx(rows, path, fieldnames)

    ws = load_workbook(path).active
    assert [c.value for c in ws[1]] == fieldnames     # header row, in order
    assert ws.max_row == 2                            # header + one data row


def test_write_xlsx_keeps_isbn_as_text_not_number(tmp_path) -> None:
    # The whole point: a 13-digit ISBN must NOT become 9,78E+12, and a
    # leading-zero ISBN-10 must NOT lose its zero. Both arrive as strings; both
    # must stay TEXT cells (data_type 's', not 'n').
    fieldnames = ["isbn13", "isbn10"]
    rows = [{"isbn13": "9783446195134", "isbn10": "0134685997"}]
    path = tmp_path / "isbn.xlsx"
    write_xlsx(rows, path, fieldnames)

    ws = load_workbook(path).active
    isbn13_cell, isbn10_cell = ws["A2"], ws["B2"]
    assert isbn13_cell.value == "9783446195134"
    assert isbn13_cell.data_type == "s"              # 's' = string, not number
    assert isbn10_cell.value == "0134685997"         # leading zero preserved
    assert isbn10_cell.data_type == "s"


def test_write_xlsx_keeps_numeric_fields_numeric(tmp_path) -> None:
    # Native passthrough: a real number stays a number cell (clean 320, not "320").
    fieldnames = ["pages"]
    rows = [{"pages": 320}]
    path = tmp_path / "num.xlsx"
    write_xlsx(rows, path, fieldnames)

    cell = load_workbook(path).active["A2"]
    assert cell.value == 320
    assert cell.data_type == "n"                     # 'n' = numeric


def test_write_xlsx_missing_key_yields_empty_cell(tmp_path) -> None:
    # build_rejected_file_rows always supplies every field, but be robust: a dict
    # missing a fieldname must not raise -- it writes an empty cell.
    fieldnames = ["a", "b"]
    rows = [{"a": "present"}]                         # 'b' absent on purpose
    path = tmp_path / "gap.xlsx"
    write_xlsx(rows, path, fieldnames)

    ws = load_workbook(path).active
    assert ws["A2"].value == "present"
    assert ws["B2"].value is None
