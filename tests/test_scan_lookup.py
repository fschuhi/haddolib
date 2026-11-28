"""
tests/test_scan_lookup.py -- Tests for the pure helpers of scripts/scan_lookup.py
(read_scan_sheet, classify_isbn). The script lives outside the package, so it is
loaded by path.
"""

import importlib.util
from pathlib import Path

import pytest
from openpyxl import Workbook

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "scan_lookup.py"
_spec = importlib.util.spec_from_file_location("scan_lookup", _SCRIPT)
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

HEADER = ["room", "space_label", "bin_label", "position", "isbn"]


def _make_scan_sheet(path: Path, rows: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# classify_isbn()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", "   "])
def test_classify_empty(value) -> None:
    assert script.classify_isbn(value) == (script.KIND_EMPTY, None)


def test_classify_valid_isbn13() -> None:
    assert script.classify_isbn("9783446195134") == (script.KIND_VALID, "9783446195134")


def test_classify_valid_isbn13_with_hyphens_and_spaces() -> None:
    assert script.classify_isbn(" 978-3-446 19513-4 ") == (script.KIND_VALID, "9783446195134")


def test_classify_isbn10_is_converted_to_isbn13() -> None:
    assert script.classify_isbn("0306406152") == (script.KIND_VALID, "9780306406157")


@pytest.mark.parametrize("value", ["080442957X", "080442957x", "0-8044-2957-X"])
def test_classify_isbn10_with_x(value) -> None:
    assert script.classify_isbn(value) == (script.KIND_VALID, "9780804429573")


def test_classify_number_cell_int() -> None:
    assert script.classify_isbn(9783446195134) == (script.KIND_VALID, "9783446195134")


def test_classify_number_cell_float() -> None:
    assert script.classify_isbn(9783446195134.0) == (script.KIND_VALID, "9783446195134")


def test_classify_number_cell_isbn10_lost_leading_zero_is_invalid() -> None:
    # 0306406152 stored as a number loses its leading zero.
    assert script.classify_isbn(306406152) == (script.KIND_INVALID, "306406152")


def test_classify_wrong_check_digit_is_invalid() -> None:
    assert script.classify_isbn("9783446195135") == (script.KIND_INVALID, "9783446195135")


def test_classify_wrong_length_is_invalid() -> None:
    assert script.classify_isbn("97834461951") == (script.KIND_INVALID, "97834461951")


def test_classify_invalid_keeps_the_value_as_scanned() -> None:
    assert script.classify_isbn(" 978-3-446-19513-5 ") == (script.KIND_INVALID, "978-3-446-19513-5")


def test_classify_digits_only_note_is_invalid() -> None:
    assert script.classify_isbn("1808") == (script.KIND_INVALID, "1808")


@pytest.mark.parametrize("value", ["Goethe blue linen", "Faust 1808", "12345X", "X"])
def test_classify_text(value) -> None:
    assert script.classify_isbn(value) == (script.KIND_TEXT, value)


def test_classify_text_is_trimmed() -> None:
    assert script.classify_isbn("  Goethe blue linen ") == (script.KIND_TEXT, "Goethe blue linen")


# ---------------------------------------------------------------------------
# read_scan_sheet()
# ---------------------------------------------------------------------------

def test_read_scan_sheet_reads_rows_in_order(tmp_path) -> None:
    path = _make_scan_sheet(tmp_path / "scan.xlsx", [
        HEADER,
        ["Magazin", "rack 15", "box 01", 1, "9783446195134"],
        ["Magazin", "rack 15", "box 01", 2, None],
    ])
    assert script.read_scan_sheet(path) == [
        {"room": "Magazin", "space_label": "rack 15", "bin_label": "box 01", "position": 1,
         "isbn": "9783446195134"},
        {"room": "Magazin", "space_label": "rack 15", "bin_label": "box 01", "position": 2,
         "isbn": None},
    ]


def test_read_scan_sheet_finds_columns_by_name_and_ignores_extra_columns(tmp_path) -> None:
    path = _make_scan_sheet(tmp_path / "scan.xlsx", [
        ["isbn", "comment", "position", "bin_label", "space_label", "room"],
        ["080442957X", "whatever", 3, "box 02", "rack 15", "Magazin"],
    ])
    assert script.read_scan_sheet(path) == [
        {"room": "Magazin", "space_label": "rack 15", "bin_label": "box 02", "position": 3,
         "isbn": "080442957X"},
    ]


def test_read_scan_sheet_skips_empty_rows(tmp_path) -> None:
    path = _make_scan_sheet(tmp_path / "scan.xlsx", [
        HEADER,
        [None, None, None, None, None],
        ["Magazin", "rack 15", "box 01", 1, "9783446195134"],
        ["", " ", None, None, ""],
    ])
    rows = script.read_scan_sheet(path)
    assert [r["isbn"] for r in rows] == ["9783446195134"]


def test_read_scan_sheet_keeps_number_cells(tmp_path) -> None:
    path = _make_scan_sheet(tmp_path / "scan.xlsx", [
        HEADER,
        ["Magazin", "rack 15", "box 01", 1.5, 9783446195134],
    ])
    row = script.read_scan_sheet(path)[0]
    assert row["position"] == 1.5
    assert row["isbn"] == 9783446195134


def test_read_scan_sheet_keeps_text_position_as_text(tmp_path) -> None:
    path = _make_scan_sheet(tmp_path / "scan.xlsx", [
        HEADER,
        ["Magazin", "rack 15", "box 01", " 1,5 ", "9783446195134"],
    ])
    assert script.read_scan_sheet(path)[0]["position"] == "1,5"


def test_read_scan_sheet_reads_the_first_sheet(tmp_path) -> None:
    wb = Workbook()
    wb.active.append(HEADER)
    wb.active.append(["Magazin", "rack 15", "box 01", 1, "9783446195134"])
    other = wb.create_sheet("notes")
    other.append(["something else"])
    wb.active = 1
    path = tmp_path / "scan.xlsx"
    wb.save(path)
    assert [r["isbn"] for r in script.read_scan_sheet(path)] == ["9783446195134"]


def test_read_scan_sheet_missing_column_raises(tmp_path) -> None:
    path = _make_scan_sheet(tmp_path / "scan.xlsx", [
        ["room", "space_label", "bin_label", "isbn"],
        ["Magazin", "rack 15", "box 01", "9783446195134"],
    ])
    with pytest.raises(ValueError, match="position"):
        script.read_scan_sheet(path)
