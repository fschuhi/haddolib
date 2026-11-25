"""
tests/test_harness.py — Self-test of the `db` fixture (the test harness itself).

Before we test ingest logic, we prove the harness delivers what it promises: a
fresh in-memory database with the full schema loaded and the connection contract
intact. These tests are also executable documentation of the schema's shape and
of the invariants the later ingest tests will rely on.

What each test demonstrates:
  • The fixture loads every expected table and view.
  • Foreign-key enforcement reaches a test through the fixture (not just in
    isolation) — a `copy` referencing a missing `edition` is rejected.
  • The isbn13 length CHECK reaches a test through the fixture.
  • The UNIQUE-with-many-NULLs behaviour the photo/pre-ISBN editions rely on
    actually holds in this harness.
  • Each test gets a clean database (isolation): a row inserted in one test is
    not visible in another.
"""

import sqlite3

import pytest

EXPECTED_TABLES = {
    "edition", "edition_revision", "copy", "space",
    "location_event", "tag", "copy_tag", "cover",
}
EXPECTED_VIEWS = {"edition_current", "book_current"}


def _names(db, kind: str) -> set:
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
        (kind,),
    ).fetchall()
    return {r["name"] for r in rows}


# ---------------------------------------------------------------------------
# Schema is present
# ---------------------------------------------------------------------------

def test_all_tables_present(db) -> None:
    assert _names(db, "table") == EXPECTED_TABLES


def test_all_views_present(db) -> None:
    assert _names(db, "view") == EXPECTED_VIEWS


# ---------------------------------------------------------------------------
# The connection contract reaches the test through the fixture
# ---------------------------------------------------------------------------

def test_foreign_keys_enforced_through_fixture(db) -> None:
    # copy.edition_id REFERENCES edition(edition_id); edition 999 does not exist.
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO copy (copy_id, edition_id, created_at) VALUES (1, 999, '2026-06-14')"
        )


def test_isbn13_length_check_through_fixture(db) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO edition (edition_id, isbn13, created_at) VALUES (1, 'too-short', '2026-06-14')"
        )


def test_many_null_isbn13_editions_allowed(db) -> None:
    # The photo / pre-ISBN trick: UNIQUE permits unlimited NULLs.
    db.execute("INSERT INTO edition (edition_id, isbn13, created_at) VALUES (1, NULL, '2026-06-14')")
    db.execute("INSERT INTO edition (edition_id, isbn13, created_at) VALUES (2, NULL, '2026-06-14')")
    count = db.execute("SELECT COUNT(*) AS n FROM edition").fetchone()["n"]
    assert count == 2


# ---------------------------------------------------------------------------
# Isolation — each test gets a clean database
# ---------------------------------------------------------------------------

def test_isolation_insert_one(db) -> None:
    db.execute("INSERT INTO edition (edition_id, isbn13, created_at) VALUES (1, NULL, '2026-06-14')")
    assert db.execute("SELECT COUNT(*) AS n FROM edition").fetchone()["n"] == 1


def test_isolation_starts_empty(db) -> None:
    # If the fixture leaked state from test_isolation_insert_one, this would fail.
    assert db.execute("SELECT COUNT(*) AS n FROM edition").fetchone()["n"] == 0
