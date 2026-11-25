"""
tests/test_tag_core.py -- Tests for the pure tag write layer (tag_core.py).

These tests ARE the spec for tag_core.set_tags. They use empty_db (the
schema on an in-memory connection). Each test sets up its own
minimal book fixture -- no shared seed -- so the cases stay independent and
easy to read.

Core contract under test:
  - Tags are replaced wholesale (delete-all-then-reinsert).
  - Tag matching is case-insensitive; unknown tags are auto-added to tag.
  - The tag table is append-only: removed tags stay in tag, only book_tag
    rows are deleted.
  - An empty/blank tags_text clears all tags without error.
  - Does not commit -- the caller owns the transaction.
"""

import pytest

from haddolib.tag_core import set_tags

TS = "2026-06-20T12:00:00"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_book(conn, isbn13: str = "9783423058087") -> int:
    """Insert a minimal book row and return its book_id."""
    cur = conn.execute(
        "INSERT INTO book (isbn13, room, space_label, bin_label, position, "
        "book_status, preferred_cover_id, created_at) VALUES (?,?,?,?,?,?,NULL,?)",
        (isbn13, "Magazin", "rack 01", "box 01", 1.0, "ready", TS),
    )
    return cur.lastrowid


def _tag_names_for_book(conn, book_id: int) -> list[str]:
    """Return the tag names linked to a book, sorted alphabetically."""
    rows = conn.execute(
        "SELECT t.name FROM tag AS t "
        "JOIN book_tag AS bt ON bt.tag_id = t.tag_id "
        "WHERE bt.book_id = ? ORDER BY t.name",
        (book_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def _all_tag_names(conn) -> list[str]:
    """Return all tag names in the tag table, sorted alphabetically."""
    rows = conn.execute("SELECT name FROM tag ORDER BY name").fetchall()
    return [r["name"] for r in rows]


# ---------------------------------------------------------------------------
# Basic set / replace
# ---------------------------------------------------------------------------

def test_set_tags_adds_tags_to_untagged_book(empty_db) -> None:
    book_id = _make_book(empty_db)
    empty_db.commit()

    set_tags(empty_db, book_id, "Klassiker, SciFi")
    empty_db.commit()

    assert _tag_names_for_book(empty_db, book_id) == ["Klassiker", "SciFi"]


def test_set_tags_replaces_existing_tags(empty_db) -> None:
    book_id = _make_book(empty_db)
    set_tags(empty_db, book_id, "Thriller, Schweden")
    empty_db.commit()

    set_tags(empty_db, book_id, "Klassiker")
    empty_db.commit()

    assert _tag_names_for_book(empty_db, book_id) == ["Klassiker"]


def test_set_tags_clears_all_tags_on_empty_string(empty_db) -> None:
    book_id = _make_book(empty_db)
    set_tags(empty_db, book_id, "Thriller")
    empty_db.commit()

    set_tags(empty_db, book_id, "")
    empty_db.commit()

    assert _tag_names_for_book(empty_db, book_id) == []


def test_set_tags_clears_all_tags_on_blank_string(empty_db) -> None:
    book_id = _make_book(empty_db)
    set_tags(empty_db, book_id, "Thriller")
    empty_db.commit()

    set_tags(empty_db, book_id, "   ")
    empty_db.commit()

    assert _tag_names_for_book(empty_db, book_id) == []


def test_set_tags_on_already_untagged_book_is_harmless(empty_db) -> None:
    book_id = _make_book(empty_db)
    empty_db.commit()

    set_tags(empty_db, book_id, "")
    empty_db.commit()

    assert _tag_names_for_book(empty_db, book_id) == []


# ---------------------------------------------------------------------------
# Case-insensitive tag reuse
# ---------------------------------------------------------------------------

def test_set_tags_case_insensitive_reuses_existing_tag_row(empty_db) -> None:
    # Pre-create "Klassiker" in the tag table with that capitalisation.
    tag_id = empty_db.execute(
        "INSERT INTO tag (name) VALUES (?)", ("Klassiker",)
    ).lastrowid
    empty_db.commit()

    book_id = _make_book(empty_db)
    # Pass the same tag in all-lowercase -- must reuse the existing row.
    set_tags(empty_db, book_id, "klassiker")
    empty_db.commit()

    # Only one tag row should exist in the tag table.
    assert _all_tag_names(empty_db) == ["Klassiker"]
    # The book is linked to it.
    assert _tag_names_for_book(empty_db, book_id) == ["Klassiker"]


def test_set_tags_first_spelling_wins_for_new_tag(empty_db) -> None:
    # "scifi" is new; the first call establishes the spelling.
    book_id = _make_book(empty_db)
    set_tags(empty_db, book_id, "scifi")
    empty_db.commit()

    assert _all_tag_names(empty_db) == ["scifi"]

    # A second book uses "SciFi" -- must reuse "scifi", not create a new row.
    book_id2 = _make_book(empty_db, isbn13="9781234567897")
    set_tags(empty_db, book_id2, "SciFi")
    empty_db.commit()

    assert _all_tag_names(empty_db) == ["scifi"]


# ---------------------------------------------------------------------------
# Tag table is append-only (removed tags stay in tag)
# ---------------------------------------------------------------------------

def test_set_tags_does_not_delete_orphaned_tag_rows(empty_db) -> None:
    book_id = _make_book(empty_db)
    set_tags(empty_db, book_id, "Thriller, Schweden")
    empty_db.commit()

    # Replace with a different tag -- Thriller and Schweden become orphans.
    set_tags(empty_db, book_id, "Klassiker")
    empty_db.commit()

    # The book now only has Klassiker...
    assert _tag_names_for_book(empty_db, book_id) == ["Klassiker"]
    # ...but Thriller and Schweden still exist in the tag table.
    assert _all_tag_names(empty_db) == ["Klassiker", "Schweden", "Thriller"]


# ---------------------------------------------------------------------------
# Whitespace and duplicates in input
# ---------------------------------------------------------------------------

def test_set_tags_trims_whitespace_around_tag_names(empty_db) -> None:
    book_id = _make_book(empty_db)
    set_tags(empty_db, book_id, "  Klassiker  ,  SciFi  ")
    empty_db.commit()

    assert _tag_names_for_book(empty_db, book_id) == ["Klassiker", "SciFi"]


def test_set_tags_deduplicates_repeated_tags(empty_db) -> None:
    book_id = _make_book(empty_db)
    set_tags(empty_db, book_id, "Klassiker, Klassiker, klassiker")
    empty_db.commit()

    # Only one book_tag row and one tag row.
    assert _tag_names_for_book(empty_db, book_id) == ["Klassiker"]
    assert _all_tag_names(empty_db) == ["Klassiker"]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_set_tags_raises_on_zero_book_id(empty_db) -> None:
    with pytest.raises(ValueError, match="positive integer book_id"):
        set_tags(empty_db, 0, "Klassiker")


def test_set_tags_raises_on_negative_book_id(empty_db) -> None:
    with pytest.raises(ValueError, match="positive integer book_id"):
        set_tags(empty_db, -1, "Klassiker")


def test_set_tags_raises_on_string_book_id(empty_db) -> None:
    with pytest.raises(ValueError, match="positive integer book_id"):
        set_tags(empty_db, "42", "Klassiker")


# ---------------------------------------------------------------------------
# Does not commit (caller owns the transaction)
# ---------------------------------------------------------------------------

def test_set_tags_does_not_commit(empty_db) -> None:
    # If set_tags committed internally, a rollback afterwards would have no
    # effect and the tags would still be there.
    book_id = _make_book(empty_db)
    empty_db.commit()

    set_tags(empty_db, book_id, "Klassiker")
    empty_db.rollback()                         # undo the set_tags work

    assert _tag_names_for_book(empty_db, book_id) == []
