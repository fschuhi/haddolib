"""
tests/test_prototype_schema.py — Smoke test for the prototype schema.

The first executable spec for the two-week prototype: the schema file loads
cleanly onto a connection, and the five tables and the one view it defines all
exist. Nothing more — behaviour (ingest, the LEFT-JOIN visibility of a
revisionless book, the isbn13 double-add guard) is specified by the step-2 suite
that comes with the roster ingest.

Loaded via the `proto_db` fixture (conftest.py), which applies
data/haddolib_prototype.sql to a fresh in-memory connection.
"""

EXPECTED_TABLES = {"book", "book_revision", "cover", "tag", "book_tag"}
EXPECTED_VIEWS = {"book_current"}


def _objects_of_type(conn, kind: str) -> set[str]:
    """Names of all user objects of a given sqlite_master type ('table' / 'view')."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
        (kind,),
    ).fetchall()
    return {row["name"] for row in rows}


def test_prototype_schema_loads_and_defines_the_five_tables(proto_db) -> None:
    # The fixture has already run apply_schema(); if the DDL were malformed the
    # fixture setup would have raised. Here we assert the shape is exactly right.
    tables = _objects_of_type(proto_db, "table")
    assert EXPECTED_TABLES <= tables, f"missing tables: {EXPECTED_TABLES - tables}"


def test_prototype_schema_defines_book_current_view(proto_db) -> None:
    views = _objects_of_type(proto_db, "view")
    assert EXPECTED_VIEWS <= views, f"missing views: {EXPECTED_VIEWS - views}"
