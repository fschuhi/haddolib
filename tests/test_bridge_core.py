"""
tests/test_bridge_core.py — the PURE bridgehead-core (no pyxll), on empty_db.

These tests ARE the spec for crossing 1's marshalling: how a raw 2D range is
sliced, how the driver's rejected-row capture becomes the rejected xlsx, how the
summary is packed for VBA, and the end-to-end run_import contract (DB write +
rejected xlsx + delimited return). The actual @xl_macro wrapper is a thin shell
over run_import and is exercised in the VM, not here.
"""

from datetime import datetime

import pytest
from openpyxl import load_workbook

from haddolib.bridge_core import (
    build_rejected_csv_rows,
    pack_summary,
    parse_block,
    run_import,
)
from haddolib.roster_import import ImportSummary

NOW = datetime(2026, 6, 15, 12, 0, 0)            # fixed → deterministic stamps
STAMP_FILE = "20260615_120000_rejected.xlsx"

# Header order deliberately NOT schema order, to prove the string maps, not order.
HEADERS = ["tags", "isbn13", "title", "revision_source", "cover_ref", "cover_source",
           "room", "space_label", "bin_label"]


def _row(tags="", isbn13="", title="", source="", cover_ref="", cover_source="",
         room="Magazin", space="rack 01", binl="01"):
    return (tags, isbn13, title, source, cover_ref, cover_source, room, space, binl)


def _vba_parse(s: str) -> dict:
    """Simulate VBA: Split on vbLf into lines, each on vbTab into key/value."""
    d = {}
    for line in s.split("\n"):
        key, _, value = line.partition("\t")
        d[key] = value
    return d


# ---------------------------------------------------------------------------
# parse_block — slice, guard, strip reserved columns
# ---------------------------------------------------------------------------

def test_parse_block_splits_header_from_rows() -> None:
    data = [("h1", "h2"), ("a", "b"), ("c", "d")]
    headers, rows = parse_block(data)
    assert headers == ["h1", "h2"]
    assert rows == [["a", "b"], ["c", "d"]]


def test_parse_block_strips_leading_rejected_reason_column() -> None:
    # A round-tripped rejected file with ONLY the reason column: it must vanish.
    data = [("Rejected_Reason", "isbn13", "title"),     # mixed case on purpose
            ("duplicate_isbn13", "9783423058087", "X")]
    headers, rows = parse_block(data)
    assert headers == ["isbn13", "title"]
    assert rows == [["9783423058087", "X"]]


def test_parse_block_strips_leading_rejected_reason_and_detail_columns() -> None:
    # The real round-trip: a rejected file leads with BOTH reserved columns.
    # Both must be stripped, in order, so neither reaches the mapper.
    data = [("rejected_reason", "Rejected_Detail", "isbn13", "title"),   # mixed case on purpose
            ("non_numeric_value", "height_cm = '21,59' is not a number",
             "9783423058087", "X")]
    headers, rows = parse_block(data)
    assert headers == ["isbn13", "title"]
    assert rows == [["9783423058087", "X"]]


def test_parse_block_single_cell_raises() -> None:
    # .Value2 on a single cell is a scalar, not a 2D structure.
    with pytest.raises(ValueError, match="single cell"):
        parse_block("9783423058087")
    with pytest.raises(ValueError, match="single cell"):
        parse_block(42.0)


def test_parse_block_flat_row_raises() -> None:
    # A 1D sequence (not tuple-of-tuples) is also not a valid block.
    with pytest.raises(ValueError, match="2D range"):
        parse_block(["h1", "h2"])


# ---------------------------------------------------------------------------
# build_rejected_csv_rows — the header re-enters here; reason + detail lead
# ---------------------------------------------------------------------------

def test_build_rejected_csv_rows_shape_detail_and_verbatim() -> None:
    headers = ["isbn13", "title", "height_cm"]
    rejected = [
        # a FIELD-level check carries a detail naming the offending cell...
        ("non_numeric_value", "height_cm = '21,59' is not a number",
         ("9783423058087", "Comma", "21,59")),
        # ...an identity check leaves the detail blank (code alone says enough).
        ("invalid_isbn13", "", ("9783423058088", "Bad", "")),
    ]
    rows, fieldnames = build_rejected_csv_rows(headers, rejected)
    assert fieldnames == ["rejected_reason", "rejected_detail", "isbn13", "title", "height_cm"]
    assert rows == [
        {"rejected_reason": "non_numeric_value",
         "rejected_detail": "height_cm = '21,59' is not a number",
         "isbn13": "9783423058087", "title": "Comma", "height_cm": "21,59"},
        {"rejected_reason": "invalid_isbn13", "rejected_detail": "",
         "isbn13": "9783423058088", "title": "Bad", "height_cm": ""},   # "" stays ""
    ]


# ---------------------------------------------------------------------------
# pack_summary — the delimited return channel, VBA-parseable
# ---------------------------------------------------------------------------

def test_pack_summary_round_trips_through_vba_split() -> None:
    s = ImportSummary(inserted=10, duplicate_isbn13=2, invalid_isbn13=1,
                      duplicate_photo=1, no_key=1, errors=[(5, "boom")],
                      unknown_headers=["mystery", "another"])
    packed = pack_summary(s, "/data/import/20260615_120000_rejected.xlsx")
    d = _vba_parse(packed)

    assert d["inserted"] == "10"
    assert d["declined"] == "5"                       # 2+1+1+1
    assert d["errors"] == "1"
    assert d["total"] == "16"                         # 10 + 5 + 1
    assert d["invalid_isbn13"] == "1"
    assert d["unknown_columns"] == "mystery, another"
    assert d["rejected_rows_file"].endswith(STAMP_FILE)
    assert "10 inserted" in d["summary_line"]


def test_pack_summary_scrubs_delimiters_from_values() -> None:
    # A header carrying a stray tab/newline must not break the channel.
    s = ImportSummary(inserted=1, unknown_headers=["bad\tcol", "line\nbreak"])
    d = _vba_parse(pack_summary(s, ""))
    # exactly the 11 known keys parsed back — no spurious lines from injected \n/\t
    assert len(d) == 11
    assert "\t" not in d["unknown_columns"] and "\n" not in d["unknown_columns"]
    assert d["rejected_rows_file"] == ""


# ---------------------------------------------------------------------------
# run_import — end to end: DB write + rejected xlsx + delimited return
# ---------------------------------------------------------------------------

def test_run_import_with_rejects_writes_xlsx_and_reports(empty_db, tmp_path) -> None:
    good = _row(isbn13="9783423058087", title="Good", source="isbndb")
    bad = _row(isbn13="9783423058088", title="Bad cksum", source="isbndb")   # wrong check digit
    data = [tuple(HEADERS), good, bad]

    packed = run_import(empty_db, data, NOW, str(tmp_path))
    d = _vba_parse(packed)

    # the delimited summary reports the run correctly
    assert d["inserted"] == "1"
    assert d["declined"] == "1"
    assert d["invalid_isbn13"] == "1"
    assert d["errors"] == "0"
    assert d["rejected_rows_file"].endswith(STAMP_FILE)

    # the good book actually landed
    assert empty_db.execute("SELECT COUNT(*) FROM book").fetchone()[0] == 1

    # the rejected xlsx exists at the stamped name
    xlsx_path = tmp_path / STAMP_FILE
    assert xlsx_path.exists()

    ws = load_workbook(xlsx_path).active
    header = [c.value for c in ws[1]]
    assert header[0] == "rejected_reason"                          # leading columns
    assert header[1] == "rejected_detail"
    assert ws.max_row == 2                                         # header + 1 row

    record = dict(zip(header, [c.value for c in ws[2]]))
    assert record["rejected_reason"] == "invalid_isbn13"
    assert record["rejected_detail"] in (None, "")                # identity check -> blank detail
    assert record["isbn13"] == "9783423058088"                    # verbatim value
    assert record["title"] == "Bad cksum"

    # and the ISBN stayed a TEXT cell — the whole reason for the xlsx switch
    isbn_col = header.index("isbn13") + 1                          # 1-based
    assert ws.cell(row=2, column=isbn_col).data_type == "s"


def test_run_import_with_non_numeric_reject_carries_detail(empty_db, tmp_path) -> None:
    # A field-level reject populates rejected_detail end-to-end (column B in the file).
    headers = ["isbn13", "title", "revision_source", "height_cm"]
    good = ("9783423058087", "Good", "isbndb", 21.59)              # native number -> inserted
    bad = ("9781234567897", "Comma", "isbndb", "21,59")            # text cell -> non_numeric_value
    data = [tuple(headers), good, bad]

    packed = run_import(empty_db, data, NOW, str(tmp_path))
    d = _vba_parse(packed)
    assert d["inserted"] == "1"
    assert d["declined"] == "1"

    ws = load_workbook(tmp_path / STAMP_FILE).active
    header = [c.value for c in ws[1]]
    record = dict(zip(header, [c.value for c in ws[2]]))
    assert record["rejected_reason"] == "non_numeric_value"
    assert record["rejected_detail"] == "height_cm = '21,59' is not a number"
    assert record["isbn13"] == "9781234567897"                    # verbatim


def test_run_import_all_clean_writes_no_file(empty_db, tmp_path) -> None:
    data = [tuple(HEADERS), _row(isbn13="9783423058087", title="Good", source="isbndb")]

    packed = run_import(empty_db, data, NOW, str(tmp_path))
    d = _vba_parse(packed)

    assert d["inserted"] == "1"
    assert d["declined"] == "0"
    assert d["rejected_rows_file"] == ""                           # nothing to offer
    assert list(tmp_path.glob("*.xlsx")) == []                    # and no file written
