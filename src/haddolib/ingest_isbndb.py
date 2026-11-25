#!/usr/bin/env python3
"""
ingest_isbndb.py — Turn one ISBNdb-sheet row into edition (+ revision) rows.

HIBERNATED (June 2026): This module is the dream-schema ingest path
(`edition` + `edition_revision`). It is kept green against `haddolib_schema.sql`
but is NOT developed during prototype work — the active build is the prototype
schema (`book` / `book_revision` / `cover` / `tag` / `book_tag`), with its own
roster import in `roster.py` + `roster_import.py`. See
`PROTOTYPE_SCHEMA_DECISION.md` for the rationale; this file thaws when the
dream re-emerges post-birthday. On thaw, repoint the private coercion helpers
below to `common.as_text` / `common.as_int` / `common.as_real` (they were
promoted during the prototype session and are now duplicated here).

This is the testable core of the first ingest slice. It takes a single row as a
plain dict (keyed like the ISBNdb sheet headers) and a connection, and applies
the *idempotent, insert-only* re-import path:

  • edition  — keyed on isbn13. Insert if absent; reuse the existing edition_id
               if present. Never a second edition for the same ISBN.
  • revision — one rev0 snapshot with source='isbndb', inserted ONLY if the
               edition has no isbndb revision yet. Re-import is therefore a
               no-op and never appends a duplicate snapshot (and never clobbers
               a later manual revision).
  • not-found — rows from failed lookups (found == 0) are skipped entirely: no
               edition, no revision; reason="skipped: not found".

Field mapping (sheet key -> edition_revision column):
  the sheet's `edition` -> `print_edition` (the name "edition" was taken);
  `found` is a sheet flag, not a column; `subtitle` has no ISBNdb source and is
  always NULL here (it is filled only by the deliberate manual-revision path).

Normalisation: every absent value (None or "") becomes NULL, so "absent" is
represented one way, not a mix of "" and NULL. `pages` is coerced to int and the
dimension fields to float (the schema declares them INTEGER/REAL under STRICT,
which would reject an empty string).

Input contract: the live source is the Excel sheet read via PyXLL, which hands
Python the cells' true values — numbers as native int/float (Excel stores whole
numbers as floats, so pages may arrive as 946.0), blanks as None. The German
decimal comma seen in the seed CSV is a display/import detail of that CSV and
never reaches here; the coercion helpers therefore expect native numbers and
treat any non-numeric string as a loud error rather than parsing locales.

Transactions: this function does NOT commit. The edition and its revision are
written in one transaction so the caller (the later Excel driver) can commit
once per row, keeping the pair atomic. Tests read through the same connection,
which sees the uncommitted rows.

Reading racks.xlsm is a separate thin layer wrapped around this function later;
keeping the core dict-in/result-out is what lets the tests run purely in memory.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class IngestResult:
    """What one call to ingest_isbndb_row did, for tests and for the driver's summary."""
    edition_id: int | None
    edition_created: bool
    revision_created: bool
    reason: str


def _utcnow_iso() -> str:
    """Current time as an ISO-8601 UTC string (the default 'now')."""
    return datetime.now(timezone.utc).isoformat()


def _text(value) -> str | None:
    """Trim to text; an empty/missing value becomes NULL (None)."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _to_int(value) -> int | None:
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


def _to_real(value) -> float | None:
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


def ingest_isbndb_row(
    conn: sqlite3.Connection,
    row: dict,
    created_at: str | None = None,
) -> IngestResult:
    """
    Ingest a single ISBNdb-sheet row, idempotently.

    conn       — a connection from database.connect().
    row        — one sheet row as a dict (keys = ISBNdb sheet headers).
    created_at — timestamp to stamp on new rows; defaults to current UTC.
                 Injected so tests are deterministic.
    """
    # not-found rows (failed ISBNdb lookups) carry found == 0; insert nothing.
    if row.get("found") == 0:
        return IngestResult(
            edition_id=None,
            edition_created=False,
            revision_created=False,
            reason="skipped: not found",
        )

    created_at = created_at or _utcnow_iso()

    isbn13 = (row.get("isbn13") or "").strip()

    # ── edition: insert-or-reuse, keyed on isbn13 ──────────────────────────
    existing = conn.execute(
        "SELECT edition_id FROM edition WHERE isbn13 = ?", (isbn13,)
    ).fetchone()
    if existing is not None:
        edition_id = existing["edition_id"]
        edition_created = False
    else:
        cur = conn.execute(
            "INSERT INTO edition (isbn13, created_at) VALUES (?, ?)",
            (isbn13, created_at),
        )
        edition_id = cur.lastrowid
        edition_created = True

    # ── revision: insert rev0 only if this edition has no isbndb revision ──
    has_isbndb_rev = conn.execute(
        "SELECT 1 FROM edition_revision WHERE edition_id = ? AND source = 'isbndb' LIMIT 1",
        (edition_id,),
    ).fetchone()

    if has_isbndb_rev is None:
        snapshot = {
            "edition_id":     edition_id,
            "source":         "isbndb",
            "created_at":     created_at,
            "title":          _text(row.get("title")),
            "title_long":     _text(row.get("title_long")),
            "subtitle":       None,                       # no ISBNdb source; manual path fills it
            "authors":        _text(row.get("authors")),
            "publisher":      _text(row.get("publisher")),
            "date_published": _text(row.get("date_published")),
            "print_edition":  _text(row.get("edition")),  # rename: sheet "edition" -> print_edition
            "pages":          _to_int(row.get("pages")),
            "binding":        _text(row.get("binding")),
            "language":       _text(row.get("language")),
            "dimensions":     _text(row.get("dimensions")),
            "height_cm":      _to_real(row.get("height_cm")),
            "length_cm":      _to_real(row.get("length_cm")),
            "width_cm":       _to_real(row.get("width_cm")),
            "weight_kg":      _to_real(row.get("weight_kg")),
            "subjects":       _text(row.get("subjects")),
            "dewey_decimal":  _text(row.get("dewey_decimal")),
            "isbn10":         _text(row.get("isbn10")),
            "cover_url":      _text(row.get("cover_url")),
        }
        conn.execute(
            """INSERT INTO edition_revision
                   (edition_id, source, created_at, title, title_long, subtitle, authors,
                    publisher, date_published, print_edition, pages, binding, language,
                    dimensions, height_cm, length_cm, width_cm, weight_kg, subjects,
                    dewey_decimal, isbn10, cover_url)
               VALUES
                   (:edition_id, :source, :created_at, :title, :title_long, :subtitle, :authors,
                    :publisher, :date_published, :print_edition, :pages, :binding, :language,
                    :dimensions, :height_cm, :length_cm, :width_cm, :weight_kg, :subjects,
                    :dewey_decimal, :isbn10, :cover_url)""",
            snapshot,
        )
        revision_created = True
    else:
        revision_created = False

    return IngestResult(
        edition_id=edition_id,
        edition_created=edition_created,
        revision_created=revision_created,
        reason="ok",
    )

