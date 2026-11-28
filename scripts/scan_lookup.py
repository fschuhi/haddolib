#!/usr/bin/env python3
"""
scan_lookup.py -- Turn a scan sheet into a lookup sheet.

A scan sheet is an xlsx with one row per scanned book and the columns room,
space_label, bin_label, position and isbn. The isbn cell holds what was scanned
or typed in Notepad++: an ISBN-13, an ISBN-10, a short text to recognise a book
without a barcode, or nothing.

This file holds the pure helpers that read a scan sheet and classify its isbn
cells. They use no network and are tested in tests/test_scan_lookup.py.
"""

from pathlib import Path

from openpyxl import load_workbook

from haddolib.common import as_text, is_valid_isbn10, is_valid_isbn13, isbn10_to_isbn13

# --- Constants ---

SCAN_COLUMNS = ["room", "space_label", "bin_label", "position", "isbn"]

# The kinds classify_isbn() returns.
KIND_EMPTY = "empty"        # nothing in the cell
KIND_TEXT = "text"          # a note to recognise the book, not an ISBN
KIND_INVALID = "invalid"    # looks like an ISBN, but fails the check digit or the length
KIND_VALID = "valid"        # a valid ISBN-13 or ISBN-10, returned as ISBN-13


# --- Reading the scan sheet ---

def read_scan_sheet(xlsx_path: Path) -> list[dict]:
    """
    Read the first sheet of a scan sheet xlsx and return one dict per book row,
    with the keys of SCAN_COLUMNS, in sheet order.

    Columns are found by header name, so their order does not matter and extra
    columns are ignored. Rows whose five scan columns are all empty are skipped:
    Excel often keeps such rows at the end of a sheet.

    Values: room, space_label and bin_label become text (blank -> None). position
    stays a number if the cell holds one; anything else is kept as text, so a
    wrong value stays visible and the database import rejects it. isbn is the raw
    cell value, for classify_isbn().

    Formulas are read as their last computed values (data_only=True), so a
    location filled in by formula works.

    Raises ValueError if one of the SCAN_COLUMNS is missing from the header row.
    """
    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    try:
        rows = wb.worksheets[0].iter_rows(values_only=True)
        header = [as_text(h) for h in next(rows, ())]
        missing = [name for name in SCAN_COLUMNS if name not in header]
        if missing:
            raise ValueError(f"{xlsx_path}: column(s) {missing!r} not found in the header row")
        index = {name: header.index(name) for name in SCAN_COLUMNS}

        scan_rows: list[dict] = []
        for row in rows:
            cells = {name: row[i] if i < len(row) else None for name, i in index.items()}
            if all(as_text(value) is None for value in cells.values()):
                continue
            position = cells["position"]
            scan_rows.append({
                "room":        as_text(cells["room"]),
                "space_label": as_text(cells["space_label"]),
                "bin_label":   as_text(cells["bin_label"]),
                "position":    position if isinstance(position, (int, float)) else as_text(position),
                "isbn":        cells["isbn"],
            })
        return scan_rows
    finally:
        wb.close()


# --- Classifying the isbn cell ---

def _is_isbn_candidate(compact: str) -> bool:
    """True if compact is digits only, or 9 digits followed by 'X' (an ISBN-10 check digit)."""
    if compact.isdigit():
        return True
    return len(compact) == 10 and compact[:9].isdigit() and compact[9] == "X"


def classify_isbn(value) -> tuple[str, str | None]:
    """
    Classify one isbn cell of a scan sheet. Returns (kind, value):

      (KIND_EMPTY,   None)     -- the cell is empty or blank
      (KIND_TEXT,    text)     -- a note, e.g. "Goethe blue linen"; goes to book_note
      (KIND_INVALID, scanned)  -- an ISBN candidate that is not a valid ISBN; the
                                  value as scanned (trimmed), for isbn13
      (KIND_VALID,   isbn13)   -- a valid ISBN-13, or a valid ISBN-10 converted to
                                  ISBN-13; hyphens and spaces removed

    An ISBN candidate is what is left after removing hyphens and spaces, if it is
    digits only, or 9 digits followed by X. So a note made only of digits (e.g.
    "1808") counts as a candidate and comes back as invalid, which is easy to
    spot in the lookup sheet.

    A number cell (an ISBN that Excel stored as a number) is turned back into
    its digits: 9783446195134.0 -> "9783446195134". A lost leading zero of an
    ISBN-10 cannot be restored; such a value comes back as invalid.
    """
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = as_text(value)
    if text is None:
        return KIND_EMPTY, None

    compact = text.replace("-", "").replace(" ", "").upper()
    if not _is_isbn_candidate(compact):
        return KIND_TEXT, text
    if is_valid_isbn13(compact):
        return KIND_VALID, compact
    if is_valid_isbn10(compact):
        return KIND_VALID, isbn10_to_isbn13(compact)
    return KIND_INVALID, text
