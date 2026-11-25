#!/usr/bin/env python3
"""
database.py -- The single front door to the haddolib SQLite database.

Every piece of code that touches the database (ingest scripts, tests, and later
the PyXLL bridge) opens its connection through `connect()` here, never via a raw
`sqlite3.connect(...)`. Routing all connections through one factory guarantees
the connection *contract* is always honoured:

  1. Foreign keys are ON. SQLite turns foreign-key enforcement OFF by default, and the switch is
       PER-CONNECTION -- it is forgotten the moment a connection closes. A caller
       that forgets `PRAGMA foreign_keys = ON` silently runs with no enforcement,
       so a `book_revision` pointing at a non-existent `book` would slip in unnoticed.
       Doing it here, once, makes forgetting impossible.

  2. Journal mode is DELETE (SQLite's default rollback journal).
       During a write SQLite keeps a small temporary companion file beside the
       database so an interrupted write can be rolled back rather than left
       half-applied (corrupt). DELETE mode deletes that file when the write
       finishes. We choose it deliberately over WAL: with only ~2 users we don't
       need WAL's reader/writer concurrency, and DELETE keeps backups trivial --
       "copy the one file when nothing is writing", with no extra flush step.
       Setting it explicitly (even though it is the default) makes the file state
       our intent rather than relying on a default a future reader must know.

  3. Rows are readable by column name.
       `row_factory = sqlite3.Row` lets query results be read as `row["title"]`
       instead of `row[0]`, which keeps ingest code and tests legible.

`apply_schema()` runs the schema DDL (`DEFAULT_SCHEMA`) against a connection.
The same function serves two purposes: the test harness loads the schema onto a
fresh in-memory connection, and the one-time creation of the live Windows DB
(`apply_schema(connect())` on the VM) runs the identical DDL -- no duplicated
schema-loading logic.

Path: the live database lives natively in the Windows VM at DEFAULT_DB. Tests
pass `":memory:"` (an ephemeral in-memory database); the live workbench calls
`connect()` with no argument and gets the real file.

Note: `PRAGMA journal_mode = DELETE` has no effect on an in-memory database --
it has no file to journal to, so it reports `memory`. That is expected, and the
tests document the distinction.
"""

import sqlite3
from pathlib import Path

# Live database -- native Windows path inside the VM (NOT the Y: share).
# Its own folder keeps SQLite's temporary companion files and our backups tidy,
# and leaves room should haddolib ever grow a second database.
DEFAULT_DB = r"C:\SQLite\haddolib\haddolib.db"

# Default location of the schema DDL, resolved relative to THIS module so it
# works regardless of the current working directory.
#   src/haddolib/database.py  ->  .parent = haddolib/  ->  .parent = src/  ->  .parent = repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SCHEMA = _REPO_ROOT / "data" / "haddolib_default_schema.sql"


def connect(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    """
    Open a SQLite connection with the haddolib connection contract applied.

    db_path -- filesystem path to the database file. Defaults to the live
               Windows DB. Pass ":memory:" for an ephemeral in-memory database
               (used by the tests), or any other path for a throwaway file.

    Returns a `sqlite3.Connection` that already has foreign keys enabled,
    journal mode set to DELETE, and `sqlite3.Row` as its row factory.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")      # per-connection; OFF by default
    conn.execute("PRAGMA journal_mode = DELETE;")  # our chosen rollback journal
    conn.row_factory = sqlite3.Row                 # rows readable by column name
    return conn


def apply_schema(conn: sqlite3.Connection, sql_path: Path = DEFAULT_SCHEMA) -> sqlite3.Connection:
    """
    Load the haddolib schema DDL onto an existing connection.

    conn     -- a connection from `connect()` (or any sqlite3 connection).
    sql_path -- path to the schema file; defaults to DEFAULT_SCHEMA.

    Reads the DDL and runs it as one script, then commits so the result is
    persisted (this matters for a file-backed DB; harmless for `:memory:`).

    Returns the same connection, so the live DB can be created in one line:

        apply_schema(connect())     # one-time, on the Windows VM

    Raises FileNotFoundError if the schema file is missing -- a loud, early
    failure is better than a silent empty database.
    """
    ddl = Path(sql_path).read_text(encoding="utf-8")
    conn.executescript(ddl)
    conn.commit()
    return conn
