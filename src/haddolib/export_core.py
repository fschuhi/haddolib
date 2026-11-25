#!/usr/bin/env python3
"""
export_core.py — The pure export layer for haddolib.

Produces a full catalogue snapshot as an xlsx file, in a format that is
directly re-importable via haddo_import / import_roster. A dump → edit →
bootstrap → re-import cycle is the supported path for manual bibliographic
corrections until crossing 4 (bib editing dialog) is built.

Public entry point:

  dump_db(conn, dest, now) — write all books to an xlsx at dest.

Column contract:
  The output headers are exactly the keys of roster.FIELD_MAP (plus "tags"),
  in DUMP_FIELDS order. This is not accidental: the import layer maps by
  header string, so the dump and the import must speak the same vocabulary.
  If FIELD_MAP ever gains or loses a key, DUMP_FIELDS must be updated in step.
  See haddolib-design.md §4 (contract note on field-name uniqueness).

Columns intentionally excluded from the dump:
  • book_id    — surrogate key; meaningless after a bootstrap + re-import
                 (new ids are minted). Including it would imply a stable
                 identity across re-imports that does not exist.
  • revised_at — the revision's created_at timestamp; a property of the
                 original ingest run, not re-playable via import.

Round-trip caveats (documented in GOALS.md):
  • Only the preferred cover survives (book_current surfaces one cover row).
  • Only the most recent revision survives (book_current's newest-wins JOIN).
  • Orphan tags (use_count = 0) are not present in any book's tag list and
    therefore vanish.
  • book_id and revised_at are not preserved (see above).

This module is PURE: no PyXLL, no Excel object model. Testable on macOS.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from haddolib.common import write_xlsx
from haddolib.query_core import all_books
from haddolib.roster import FIELD_MAP, TAGS_HEADER

# ---------------------------------------------------------------------------
# Column order for the dump xlsx
# ---------------------------------------------------------------------------

# Exactly the FIELD_MAP keys (in their natural grouping order) plus TAGS_HEADER.
# This list is the contract: import reads by header string, so every name here
# must match a key in FIELD_MAP or be TAGS_HEADER. Nothing else, nothing less.
DUMP_FIELDS: list[str] = [
    # ── book ──────────────────────────────────────────────────────────────────
    "isbn13",
    "room",
    "space_label",
    "bin_label",
    "position",
    "book_status",
    "book_note",
    # ── book_revision ─────────────────────────────────────────────────────────
    "revision_source",
    "revision_comment",
    "title",
    "title_long",
    "subtitle",
    "authors",
    "publisher",
    "date_published",
    "edition",
    "pages",
    "binding",
    "language",
    "dimensions",
    "height_cm",
    "length_cm",
    "width_cm",
    "weight_kg",
    "subjects",
    "dewey_decimal",
    "isbn10",
    # ── cover ─────────────────────────────────────────────────────────────────
    "cover_ref",
    "cover_source",
    "cover_status",
    # ── tags ──────────────────────────────────────────────────────────────────
    "tags",
]

# Sanity-check at import time: every entry in DUMP_FIELDS must be a known
# FIELD_MAP key or the special TAGS_HEADER. A mismatch here means FIELD_MAP
# was updated without updating DUMP_FIELDS — catch it loud and early.
_KNOWN = set(FIELD_MAP) | {TAGS_HEADER}
_UNKNOWN = [f for f in DUMP_FIELDS if f not in _KNOWN]
if _UNKNOWN:
    raise RuntimeError(
        f"export_core.DUMP_FIELDS contains entries not in FIELD_MAP or TAGS_HEADER: "
        f"{_UNKNOWN!r}. Update DUMP_FIELDS to match."
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def dump_db(
    conn: sqlite3.Connection,
    dest,
    now: datetime,
) -> int:
    """Write a full catalogue snapshot to dest as an xlsx.

    conn — an open SQLite connection (the haddolib connection contract assumed:
           foreign keys ON, row_factory = sqlite3.Row).
    dest — a path (str / os.PathLike) or a writable binary file-like object,
           passed directly to common.write_xlsx. The caller is responsible for
           constructing the path (including the timestamp stem); this function
           does not touch the filesystem beyond the single write_xlsx call.
    now  — the run timestamp. Not used by this function directly, but accepted
           for symmetry with run_import so the CLI wrapper has a single "now"
           to stamp both the filename and any future audit fields.

    Returns the number of books written (excluding the header row).
    """
    books = all_books(conn)
    rows = [_to_dump_row(book) for book in books]
    write_xlsx(rows, dest, DUMP_FIELDS)
    return len(rows)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_dump_row(book: dict) -> dict:
    """Map one all_books() dict to a DUMP_FIELDS-keyed dict.

    book_current exposes every column that DUMP_FIELDS names, with the same
    names — no renaming is needed. We simply pick the keys we want (DUMP_FIELDS)
    and let the rest (book_id, revised_at) fall away.

    Missing keys default to None (write_xlsx writes an empty cell for None).
    """
    return {field: book.get(field) for field in DUMP_FIELDS}
