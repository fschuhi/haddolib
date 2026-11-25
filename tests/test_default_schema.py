"""
tests/test_default_schema.py -- Smoke test for the schema (DEFAULT_SCHEMA).

The schema file loads cleanly onto a connection, and the five tables and the
one view it defines all exist. Also: the connection contract and the schema's
checks reach a test through the fixture, and each test starts with an empty
database.

Loaded via the `empty_db` fixture (conftest.py), which applies
data/haddolib_default_schema.sql to a fresh in-memory connection.
"""

import sqlite3

import pytest

EXPECTED_TABLES = {"book", "book_revision", "cover", "tag", "book_tag"}
EXPECTED_VIEWS = {"book_current"}


def _objects_of_type(conn, kind: str) -> set[str]:
    """Names of all user objects of a given sqlite_master type ('table' / 'view')."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
        (kind,),
    ).fetchall()
    return {row["name"] for row in rows}


def test_schema_loads_and_defines_the_five_tables(empty_db) -> None:
    # The fixture has already run apply_schema(); if the DDL were malformed the
    # fixture setup would have raised. Here we assert the shape is exactly right.
    tables = _objects_of_type(empty_db, "table")
    assert EXPECTED_TABLES <= tables, f"missing tables: {EXPECTED_TABLES - tables}"


def test_schema_defines_book_current_view(empty_db) -> None:
    views = _objects_of_type(empty_db, "view")
    assert EXPECTED_VIEWS <= views, f"missing views: {EXPECTED_VIEWS - views}"


# ---------------------------------------------------------------------------
# The connection contract and the schema's checks reach the test
# ---------------------------------------------------------------------------

def test_foreign_keys_enforced_through_fixture(empty_db) -> None:
    # book_revision.book_id REFERENCES book(book_id); book 999 does not exist.
    with pytest.raises(sqlite3.IntegrityError):
        empty_db.execute(
            "INSERT INTO book_revision (book_id, source, created_at) "
            "VALUES (999, 'manual', '2026-06-14')"
        )


def test_isbn13_length_check_through_fixture(empty_db) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        empty_db.execute(
            "INSERT INTO book (isbn13, created_at) VALUES ('too-short', '2026-06-14')"
        )


def test_many_null_isbn13_books_allowed(empty_db) -> None:
    # Photo and pre-ISBN books have no isbn13; UNIQUE permits any number of NULLs.
    empty_db.execute("INSERT INTO book (isbn13, created_at) VALUES (NULL, '2026-06-14')")
    empty_db.execute("INSERT INTO book (isbn13, created_at) VALUES (NULL, '2026-06-14')")
    count = empty_db.execute("SELECT COUNT(*) AS n FROM book").fetchone()["n"]
    assert count == 2


# ---------------------------------------------------------------------------
# Isolation -- each test gets a clean database
# ---------------------------------------------------------------------------

def test_isolation_insert_one(empty_db) -> None:
    empty_db.execute("INSERT INTO book (isbn13, created_at) VALUES (NULL, '2026-06-14')")
    assert empty_db.execute("SELECT COUNT(*) AS n FROM book").fetchone()["n"] == 1


def test_isolation_starts_empty(empty_db) -> None:
    # If the fixture leaked state from test_isolation_insert_one, this would fail.
    assert empty_db.execute("SELECT COUNT(*) AS n FROM book").fetchone()["n"] == 0
