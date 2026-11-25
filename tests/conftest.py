"""
conftest.py — Shared pytest fixtures for the haddolib test suite.

pytest auto-discovers this file: any fixture defined here is available to every
test module by name, with no import. (Background, if useful: "pytest fixtures",
"pytest conftest.py".)

Two independent in-memory harnesses coexist here, one per schema:

  • `db`       — the FIVE-GRAIN DREAM schema (data/haddolib_schema.sql, the
                 default of apply_schema). The dream test suite reads this.
                 Hibernated: kept green against its own schema, not developed
                 against during prototype work (see PROTOTYPE_SCHEMA_DECISION.md
                 §8). Untouched.

  • `proto_db` — the PROTOTYPE schema (data/haddolib_prototype.sql): book /
                 book_revision / cover / tag / book_tag + the book_current view.
                 The prototype suite reads this.

They never collide: each fixture loads its own schema file onto its own fresh
`:memory:` connection (so the full connection contract applies — foreign keys
ON, row_factory, DELETE journal). An in-memory database exists only while its
connection is open, so closing it after the test makes it evaporate — teardown
is free, and no test can contaminate another. No skip-markers are needed: you
simply run the prototype targets during prototype work, the dream suite stays
green and out of the way.
"""

from pathlib import Path

import pytest

from haddolib.database import apply_schema, connect

# tests/conftest.py -> .parent = tests/ -> .parent = repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PROTOTYPE_SCHEMA = _REPO_ROOT / "data" / "haddolib_prototype.sql"


@pytest.fixture
def db():
    """Yield a fresh in-memory connection with the (dream) haddolib schema loaded.

    Usage in a test:

        def test_something(db):
            db.execute(...)        # a pristine, schema-loaded database
    """
    conn = connect(":memory:")
    apply_schema(conn)            # defaults to data/haddolib_schema.sql (dream)
    yield conn
    conn.close()


@pytest.fixture
def proto_db():
    """Yield a fresh in-memory connection with the PROTOTYPE schema loaded.

    Usage in a test:

        def test_something(proto_db):
            proto_db.execute("INSERT INTO book ...")
    """
    conn = connect(":memory:")
    apply_schema(conn, _PROTOTYPE_SCHEMA)
    yield conn
    conn.close()
