#!/usr/bin/env python3
"""
bridge_core.py — the PURE core of import crossing 1 (the VBA↔PyXLL bridge).

Everything the bridge does EXCEPT touching Excel's object model and opening the
live database lives here, so it is unit-testable on macOS without pyxll. The
actual @xl_macro wrapper (pyxll_bridge.py) stays a thin shell: stamp `now`, open
the live connection, call run_import, return the string.

Boundary shape (see BRIDGE_CONTRACT.md):
  • VBA orchestrates and owns the UI; Python is a pure, stateless engine.
  • Input is a generic 2D structure (tuple-of-tuples of raw cell values), sliced
    here — NOT a DataFrame. The coercion layer (common.as_*) is the single source
    of truth for typing; we keep the marshalling stupid so it can't fight it.
  • The return channel is ONE delimited-string scalar (§4): VBA Splits it twice
    into a Scripting.Dictionary. The rejected rows do NOT travel in that string —
    they go to an xlsx file on disk (§5), whose path is reported back in the
    summary under the `rejected_rows_file` key.
"""

import os
from datetime import datetime

from haddolib.common import write_xlsx
from haddolib.roster_import import ImportSummary, import_roster

# The two leading columns the rejected file carries (§5):
#   A = rejected_reason — the stable machine code (or, for an errored row, the
#       exception message).
#   B = rejected_detail — free text naming the offending cell for field-level
#       checks (blank for identity checks and errors).
# Both are stripped on re-import so a round-tripped rejected file never trips an
# "unknown header".
REJECTED_REASON_COLUMN = "rejected_reason"
REJECTED_DETAIL_COLUMN = "rejected_detail"


def parse_block(data) -> tuple[list, list]:
    """Slice a raw 2D range into (headers, rows).

    `data` is what PyXLL hands from a named Range's `.Value2`: a tuple of tuples
    of raw cell values. The first inner tuple is the header row; the rest are data.

    Two pieces of marshalling housekeeping (BRIDGE_CONTRACT.md §6):

      • Single-cell guard: `.Value2` on a SINGLE cell marshals as a scalar, not a
        2D structure, which would make `data[0]` mean the first character. We
        reject that loudly rather than silently mangling it — a single cell is not
        an import block.
      • Strip the leading reserved columns if present: a previously-written
        rejected file, re-imported after fixing, leads with `rejected_reason` and
        then `rejected_detail`. Neither must reach the mapper as an unknown
        header. Stripped in order (reason, then detail) so a file carrying just
        the reason column, or both, both round-trip cleanly. Defensive even when
        the named range is defined to exclude these columns.
    """
    if (not isinstance(data, (list, tuple))
            or len(data) == 0
            or not isinstance(data[0], (list, tuple))):
        raise ValueError(
            "import block must be a 2D range (a single cell is not an import block)"
        )

    headers = list(data[0])
    rows = [list(r) for r in data[1:]]

    for reserved in (REJECTED_REASON_COLUMN, REJECTED_DETAIL_COLUMN):
        if headers and str(headers[0]).strip().lower() == reserved:
            headers = headers[1:]
            rows = [r[1:] for r in rows]

    return headers, rows


def build_rejected_csv_rows(headers, rejected_rows) -> tuple[list[dict], list[str]]:
    """Turn the driver's (reason, detail, raw values) capture into dict rows.

    THIS is where the column headers re-enter: the driver stored values only, so
    here we zip them back against the very headers that went into the call and
    prepend the two reserved columns. fieldnames lead with `rejected_reason`, then
    `rejected_detail`, then the original columns verbatim — open the file, read
    the reason in column A, the offending cell in column B, fix the adjacent
    cells, re-import.

    (Name kept for stability across the CSV→xlsx switch; the dict/fieldnames shape
    it returns is format-agnostic and feeds write_xlsx unchanged.)
    """
    str_headers = [str(h) for h in headers]
    fieldnames = [REJECTED_REASON_COLUMN, REJECTED_DETAIL_COLUMN, *str_headers]
    out: list[dict] = []
    for reason, detail, values in rejected_rows:
        row = {REJECTED_REASON_COLUMN: reason, REJECTED_DETAIL_COLUMN: detail}
        row.update(dict(zip(str_headers, values)))
        out.append(row)
    return out, fieldnames


def pack_summary(summary: ImportSummary, rejected_file: str) -> str:
    """Pack an ImportSummary into the delimited-string return channel (§4).

    Layout: `key\\tvalue` lines joined by `\\n`. VBA Splits on vbLf into lines,
    then each line on vbTab into key/value, filling a Scripting.Dictionary.

    The payload is small and known (counts, one filename, one summary line). Every
    value is scrubbed of tab/CR/LF defensively so the two delimiters can never
    collide — only `unknown_columns` could realistically carry one, and individual
    error messages never travel here (they ride the rejected file, where the cell
    grid handles them). `rejected_file` is "" when nothing was rejected.
    """
    fields = {
        "inserted": summary.inserted,
        "declined": summary.declined,
        "errors": len(summary.errors),
        "total": summary.total,
        "duplicate_isbn13": summary.duplicate_isbn13,
        "invalid_isbn13": summary.invalid_isbn13,
        "duplicate_photo": summary.duplicate_photo,
        "no_key": summary.no_key,
        "unknown_columns": ", ".join(summary.unknown_headers),
        "rejected_rows_file": rejected_file,
        "summary_line": summary.summary_line(),
    }
    lines = []
    for key, value in fields.items():
        safe = str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")
        lines.append(f"{key}\t{safe}")
    return "\n".join(lines)


def run_import(conn, data, now: datetime, import_dir) -> str:
    """Orchestrate one import crossing and return the delimited summary string.

    Pure except for the DB handle it is given and the one file it writes:

      1. parse_block            — slice headers/rows, guard, strip reserved columns.
      2. import_roster          — the driver does ALL validation/dedup/insert and
                                  captures every non-insert in summary.rejected_rows.
      3. write the rejected xlsx — only if something was rejected; create-per-run,
                                  named with the run timestamp, owned by Python so
                                  cell TYPES are set explicitly: a string ISBN
                                  stays a text cell and a real number stays a
                                  number cell, so Excel never re-guesses untyped
                                  text on open (no 9,78E+12, no "02. Mai" dates,
                                  no lost leading zeros).
      4. pack_summary           — the scalar VBA turns into a Dictionary.

    `now` is the single source of truth for time: created_at (one stamp for the
    whole run into the DB) and the filename stamp both derive from it. The wrapper
    passes datetime.now(); tests pass a fixed datetime for determinism.

    Assumes `import_dir` exists (its creation is owned outside the engine). When
    nothing is rejected, no file is written and the summary's rejected_rows_file
    is "".
    """
    created_at = now.isoformat()
    headers, rows = parse_block(data)
    summary = import_roster(conn, headers, rows, created_at)

    rejected_file = ""
    if summary.rejected_rows:
        filename = f"{now.strftime('%Y%m%d_%H%M%S')}_rejected.xlsx"
        path = os.path.join(import_dir, filename)
        rejected_rows, fieldnames = build_rejected_csv_rows(headers, summary.rejected_rows)
        write_xlsx(rejected_rows, path, fieldnames)
        rejected_file = path

    return pack_summary(summary, rejected_file)
