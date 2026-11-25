#!/usr/bin/env python3
"""
common.py — Shared utilities for haddolib cataloguing tools.

Provides:
  - ISBN validation (ISBN-10 and ISBN-13, including checksum)
  - ISBN-10 to ISBN-13 conversion
  - CSV writing with UTF-8 BOM and semicolon delimiter (German Excel compatible)
  - XLSX writing with native cell types (ISBNs stay text; numbers stay numbers)
  - German decimal formatting
  - ISBN-as-text prefix for Excel
  - Value coercion for Excel/PyXLL input (text/int/real -> SQLite; blank -> NULL)
"""

import csv


# ---------------------------------------------------------------------------
# Excel compatibility
# ---------------------------------------------------------------------------

def fmt_decimal(value: float, decimals: int = 2) -> str:
    """Format a float using a German decimal comma (e.g. 21,50)."""
    return f"{value:.{decimals}f}".replace(".", ",")


# ---------------------------------------------------------------------------
# ISBN validation
# ---------------------------------------------------------------------------

def is_valid_isbn13(raw: str) -> bool:
    """
    Return True if raw is a valid ISBN-13.

    Validation steps:
      1. Strip hyphens and spaces, uppercase
      2. Must be exactly 13 digits
      3. Must start with 978 or 979
      4. Mod-10 checksum: weights 1,3,1,3,... over first 12 digits;
         check digit = (10 - sum % 10) % 10
    """
    s = raw.replace("-", "").replace(" ", "").upper()
    if len(s) != 13 or not s.isdigit():
        return False
    if not (s.startswith("978") or s.startswith("979")):
        return False
    total = sum((3 if i % 2 else 1) * int(d) for i, d in enumerate(s[:12]))
    return (10 - total % 10) % 10 == int(s[12])


def is_valid_isbn10(raw: str) -> bool:
    """
    Return True if raw is a valid ISBN-10.

    Validation steps:
      1. Strip hyphens and spaces, uppercase
      2. Must be exactly 10 characters
      3. First 9 characters must be digits
      4. Last character is a digit or 'X' (representing 10)
      5. Mod-11 checksum: sum of (position × digit) for positions 1–9;
         check digit = sum % 11  (X means 10)
    """
    s = raw.replace("-", "").replace(" ", "").upper()
    if len(s) != 10:
        return False
    if not s[:9].isdigit():
        return False
    last = s[9]
    if last != "X" and not last.isdigit():
        return False
    check = 10 if last == "X" else int(last)
    total = sum((i + 1) * int(d) for i, d in enumerate(s[:9]))
    return total % 11 == check


def is_valid_isbn(raw: str) -> bool:
    """Return True if raw is a valid ISBN-10 or ISBN-13."""
    return is_valid_isbn13(raw) or is_valid_isbn10(raw)


def isbn10_to_isbn13(isbn10: str) -> str:
    """
    Convert a valid ISBN-10 to its ISBN-13 equivalent.

    Steps:
      1. Strip hyphens and spaces, uppercase
      2. Prepend '978' and drop the ISBN-10 check digit (last character)
      3. Recalculate the ISBN-13 check digit:
         weights 1,3,1,3,... over first 12 digits;
         check digit = (10 - sum % 10) % 10

    The caller is responsible for ensuring isbn10 is a valid ISBN-10
    (i.e. is_valid_isbn10(isbn10) is True). Behaviour is undefined for
    invalid inputs.
    """
    s = isbn10.replace("-", "").replace(" ", "").upper()
    body = "978" + s[:9]
    total = sum((3 if i % 2 else 1) * int(d) for i, d in enumerate(body))
    check = (10 - total % 10) % 10
    return body + str(check)


# ---------------------------------------------------------------------------
# Value coercion (Excel/PyXLL cell value -> SQLite-ready value)
# ---------------------------------------------------------------------------
# Kept here, in one shared place, so every import path uses the same definition
# rather than drifting copies.
#
# The shared rule: a blank or missing value becomes NULL (None). This matters
# because Excel UDFs / XLOOKUP always return something — an unmatched lookup
# yields "" (empty string), never an IsEmpty-true cell — so "" must be read as
# "no value", i.e. NULL.

def as_text(value) -> str | None:
    """Trim to text; an empty/missing value becomes NULL (None)."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def as_int(value) -> int | None:
    """Coerce to int; blank/missing becomes NULL.

    Native numbers pass straight through — Excel/PyXLL hands whole numbers as
    floats (e.g. 946.0), so int(946.0) is the real-world path. Strings are
    parsed via int(float(...)) so a stray '946.0' also works; a non-numeric
    string (e.g. a German-comma '1,2927') raises loudly rather than corrupting.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    return int(float(s)) if s else None


def as_real(value) -> float | None:
    """Coerce to float; blank/missing becomes NULL.

    Native numbers pass straight through (the PyXLL path); strings are parsed.
    A German-comma string raises loudly — locale parsing is the CSV layer's job,
    not ours, because PyXLL delivers the true float from the cell.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    return float(s) if s else None


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict], dest, fieldnames: list[str]) -> None:
    """
    Write rows as semicolon-delimited CSV with UTF-8 BOM (German Excel compatible).

    dest       — a writable file-like object (opened in text mode)
    fieldnames — column names; each row dict is expected to contain these keys
    """
    dest.write("\ufeff")  # UTF-8 BOM
    writer = csv.DictWriter(
        dest,
        fieldnames=fieldnames,
        delimiter=";",
        lineterminator="\r\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)


# ---------------------------------------------------------------------------
# XLSX output
# ---------------------------------------------------------------------------

def write_xlsx(rows: list[dict], dest, fieldnames: list[str]) -> None:
    """
    Write rows to a single-sheet .xlsx, values kept in their NATIVE types.

    dest       — a path (str / os.PathLike) OR a writable BINARY file-like object
                 (not a text handle — openpyxl saves binary). The bridge passes a
                 path; tests can pass a path or an io.BytesIO.
    fieldnames — the header row and the column order. Each row dict is read by
                 these keys; a missing key yields an empty cell.

    Why xlsx and not CSV for the rejected-rows file: an .xlsx cell carries its
    type explicitly, so a string ISBN ("9783446195134", "0134685997") is written
    as a TEXT cell and Excel will NOT re-guess it as a number on open — no lost
    leading zero, no 9,78E+12 scientific notation. CSV carries no type metadata,
    so Excel re-guesses on open and can corrupt exactly the value the
    fix-and-reimport loop depends on. Native passthrough also keeps genuine
    numbers (pages, dimensions) as real numbers in the same write:
    str -> text cell, int/float -> number cell, None -> empty cell.

    No type forcing by design: a value that arrives numeric is written numeric.
    Setting up the import ranges as text is the caller's responsibility, and a
    surfaced "number stored as text" marker is a useful signal, not a defect.

    openpyxl is imported lazily so tools that never write xlsx don't pay for it.
    """
    from openpyxl import Workbook  # lazy: only the xlsx path needs it

    wb = Workbook()
    ws = wb.active
    ws.append(list(fieldnames))
    for row in rows:
        ws.append([row.get(name) for name in fieldnames])
    wb.save(dest)
