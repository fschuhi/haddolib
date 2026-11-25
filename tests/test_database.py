"""
tests/test_database.py -- Tests for the connection factory in database.py.

These tests are executable documentation of the connection *contract*: what is
guaranteed about any connection handed out by `connect()`. They also pin down
one genuine SQLite quirk worth understanding -- that an in-memory database and a
file-backed database do not behave identically for journal mode.

What each test demonstrates:

  - Foreign keys are ON for every connection (the edge SQLite leaves OFF by
    default, per-connection). This is the most important guarantee.
  - A FILE-backed connection is in DELETE journal mode -- our chosen rollback
    journal, which keeps backups simple.
  - An IN-MEMORY connection reports `memory`, NOT `delete`, because there is no
    file to journal to. All our later tests live in `:memory:` and the live DB
    lives on disk, so this distinction matters.
  - Rows come back readable by column name (`row["..."]`), not just by index.
"""

import sqlite3

from haddolib.database import DEFAULT_DB, connect


# ---------------------------------------------------------------------------
# Guarantee 1 -- foreign keys are ON (the headline of the contract)
# ---------------------------------------------------------------------------

def test_foreign_keys_on_for_memory() -> None:
    conn = connect(":memory:")
    fk = conn.execute("PRAGMA foreign_keys").fetchone()
    assert fk["foreign_keys"] == 1, "connect() must enable foreign keys"
    conn.close()


def test_foreign_keys_on_for_file(tmp_path) -> None:
    # tmp_path is a pytest-provided throwaway directory, cleaned up automatically.
    conn = connect(str(tmp_path / "fk.db"))
    fk = conn.execute("PRAGMA foreign_keys").fetchone()
    assert fk["foreign_keys"] == 1, "connect() must enable foreign keys on a file DB too"
    conn.close()


def test_raw_connection_has_foreign_keys_off() -> None:
    # Documents WHY the factory exists: a plain sqlite3.connect leaves FKs OFF.
    raw = sqlite3.connect(":memory:")
    assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 0, (
        "a raw connection should have foreign keys OFF -- this is the edge connect() closes"
    )
    raw.close()


# ---------------------------------------------------------------------------
# Guarantee 2 -- journal mode, with the :memory: vs. file distinction
# ---------------------------------------------------------------------------

def test_file_connection_is_delete_journal(tmp_path) -> None:
    conn = connect(str(tmp_path / "journal.db"))
    jm = conn.execute("PRAGMA journal_mode").fetchone()
    assert jm["journal_mode"] == "delete", "a file-backed connection must use the DELETE journal"
    conn.close()


def test_memory_connection_reports_memory_journal() -> None:
    # The instructive wrinkle: an in-memory DB cannot be in DELETE mode -- it has
    # no file to journal to -- so it reports `memory`. This is expected, not a bug.
    conn = connect(":memory:")
    jm = conn.execute("PRAGMA journal_mode").fetchone()
    assert jm["journal_mode"] == "memory", (
        "an in-memory database reports `memory` journal mode, not `delete`"
    )
    conn.close()


# ---------------------------------------------------------------------------
# Guarantee 3 -- rows are readable by column name
# ---------------------------------------------------------------------------

def test_rows_are_accessible_by_name() -> None:
    conn = connect(":memory:")
    row = conn.execute("SELECT 1 AS answer, 'haddolib' AS who").fetchone()
    assert row["answer"] == 1, "row_factory must allow access by column name"
    assert row["who"] == "haddolib"
    conn.close()


# ---------------------------------------------------------------------------
# Default path -- connect() with no argument targets the live Windows DB
# ---------------------------------------------------------------------------

def test_default_path_is_native_windows() -> None:
    # We don't open the live DB in tests; we only assert the wiring points at it.
    assert DEFAULT_DB == r"C:\SQLite\haddolib\haddolib.db"
