"""
conftest.py -- Shared pytest fixtures for the haddolib test suite.

pytest auto-discovers this file: any fixture defined here is available to every
test module by name, with no import. (Background, if useful: "pytest fixtures",
"pytest conftest.py".)

`empty_db` yields a fresh `:memory:` connection with the schema loaded
(`DEFAULT_SCHEMA` in database.py): book / book_revision / cover / tag /
book_tag + the book_current view. The connection comes from `connect()`, so
the full connection contract applies -- foreign keys ON, row_factory, DELETE
journal. An in-memory database exists only while its connection is open, so
closing it after the test makes it evaporate -- teardown is free, and no test
can contaminate another.
"""

import pytest

from haddolib.database import apply_schema, connect


@pytest.fixture
def empty_db():
    """Yield a fresh in-memory connection with the schema loaded.

    Usage in a test:

        def test_something(empty_db):
            empty_db.execute("INSERT INTO book ...")
    """
    conn = connect(":memory:")
    apply_schema(conn)            # defaults to DEFAULT_SCHEMA
    yield conn
    conn.close()
