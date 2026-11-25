#!/usr/bin/env python3
"""
tag_core.py -- The pure tag-management write layer for haddolib.

All tag write operations live here. Reads (for display) stay in query_core.py.
No PyXLL, no Excel -- testable on macOS via the empty_db fixture.

Public entry points:

  set_tags(conn, book_id, tags_text) -- replace all tags for a book.

Tag contract (mirrors the import path in roster_import.py):
  - Tag matching is case-insensitive (COLLATE NOCASE on the unique index).
  - The first spelling seen for a tag name is the one stored in the tag table.
  - Unknown tags are auto-added to the tag table; this module never removes
    tag rows -- orphan pruning is a separate, explicit operation.
  - set_tags never commits -- the caller owns the transaction.
"""

from __future__ import annotations

import sqlite3

from haddolib.roster import split_tags


def _resolve_or_create_tags(conn: sqlite3.Connection, names: list[str]) -> list[int]:
    """Resolve tag names to tag_ids, auto-inserting any that don't exist yet.

    Matching is case-insensitive (COLLATE NOCASE), so 'Klassiker' and
    'klassiker' resolve to the same row -- the first spelling seen wins.
    Deduplicates by resolved tag_id, so passing the same name twice (in any
    casing) yields one id rather than a primary-key clash downstream.
    """
    ids: list[int] = []
    for name in names:
        row = conn.execute(
            "SELECT tag_id FROM tag WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row is None:
            tag_id = conn.execute(
                "INSERT INTO tag (name) VALUES (?)", (name,)
            ).lastrowid
        else:
            tag_id = row["tag_id"]
        if tag_id not in ids:
            ids.append(tag_id)
    return ids


def set_tags(
    conn: sqlite3.Connection,
    book_id: int,
    tags_text: str,
) -> None:
    """Replace all tags for a book with the tags in tags_text.

    tags_text is a comma-delimited string of tag names (e.g. "Klassiker, SciFi").
    Whitespace around names is trimmed; blank entries are dropped. An empty or
    blank tags_text clears all tags for the book.

    Steps:
      1. Parse tags_text into a clean name list (via split_tags).
      2. Delete all existing book_tag rows for this book_id.
      3. Resolve each name to a tag_id (auto-creating unknown tags in the tag
         table); link each to the book via a new book_tag row.

    The tag table is append-only from this function's perspective: tags removed
    from a book are NOT deleted from the tag table. Orphan pruning is a separate
    explicit operation.

    Does NOT commit -- the caller owns the transaction boundary.

    Raises ValueError if book_id is not a positive integer.
    """
    if not isinstance(book_id, int) or book_id <= 0:
        raise ValueError(f"set_tags() requires a positive integer book_id, got {book_id!r}")

    names = split_tags(tags_text)

    conn.execute("DELETE FROM book_tag WHERE book_id = ?", (book_id,))

    for tag_id in _resolve_or_create_tags(conn, names):
        conn.execute(
            "INSERT INTO book_tag (book_id, tag_id) VALUES (?, ?)",
            (book_id, tag_id),
        )
