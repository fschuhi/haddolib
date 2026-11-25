"""
tests/test_snapshot_core.py -- Tests for the pure snapshot layer (snapshot_core.py).

These tests ARE the spec for write_snapshot(). They use empty_db (the schema on an
in-memory connection) and the same minimal seed used across the
query_core tests.

Seed layout (4 books):
  - Book A -- Magazin / rack 01 / box 01 / pos 1.0, isbndb, tags: Schweden, Thriller
  - Book B -- Magazin / rack 01 / box 01 / pos 2.0, isbndb, no tags
  - photo  -- Magazin / rack 01 / box 02 / pos 1.0, own_photo, no revision, tags: Krimi
  - Book D -- Wohnzimmer / no space / no bin,        manual,   no tags, no cover
"""

import io
from datetime import datetime

import pytest
from openpyxl import load_workbook

from haddolib.snapshot_core import SNAPSHOT_FIELDS, write_snapshot
from haddolib.roster import FIELD_MAP, TAGS_HEADER

NOW = datetime(2026, 6, 24, 15, 37, 43)
TS = "2026-06-20T12:00:00"


# ---------------------------------------------------------------------------
# Seed helper (minimal copy -- avoids cross-test-file imports)
# ---------------------------------------------------------------------------

def _seed(conn) -> None:
    """Insert the standard 4-book dataset into empty_db."""

    def _book(isbn13, room, space_label, bin_label, position, book_status,
              cover_ref=None, cover_source=None, cover_status=None,
              source=None, title=None, tags=None):
        cur = conn.execute(
            "INSERT INTO book (isbn13, room, space_label, bin_label, position, "
            "book_status, preferred_cover_id, created_at) VALUES (?,?,?,?,?,?,NULL,?)",
            (isbn13, room, space_label, bin_label, position, book_status, TS),
        )
        book_id = cur.lastrowid
        if title:
            conn.execute(
                "INSERT INTO book_revision (book_id, source, title, created_at) "
                "VALUES (?,?,?,?)",
                (book_id, source, title, TS),
            )
        if cover_ref:
            cur2 = conn.execute(
                "INSERT INTO cover (book_id, cover_ref, cover_source, cover_status, "
                "created_at) VALUES (?,?,?,?,?)",
                (book_id, cover_ref, cover_source, cover_status, TS),
            )
            conn.execute(
                "UPDATE book SET preferred_cover_id = ? WHERE book_id = ?",
                (cur2.lastrowid, book_id),
            )
        for tag_name in (tags or []):
            row = conn.execute(
                "SELECT tag_id FROM tag WHERE name = ?", (tag_name,)
            ).fetchone()
            if row is None:
                tag_id = conn.execute(
                    "INSERT INTO tag (name) VALUES (?)", (tag_name,)
                ).lastrowid
            else:
                tag_id = row["tag_id"]
            conn.execute(
                "INSERT INTO book_tag (book_id, tag_id) VALUES (?,?)",
                (book_id, tag_id),
            )

    _book("9783423058087", "Magazin", "rack 01", "box 01", 1.0, "ready",
          cover_ref="https://img/a.jpg", cover_source="isbndb",
          cover_status="beautiful", source="isbndb", title="Book A",
          tags=["Thriller", "Schweden"])
    _book("9781234567897", "Magazin", "rack 01", "box 01", 2.0, "needs_cover",
          cover_ref="https://img/b.jpg", cover_source="isbndb",
          cover_status="unreviewed", source="isbndb", title="Book B")
    _book(None, "Magazin", "rack 01", "box 02", 1.0, "needs_search",
          cover_ref="rack_01 2026-02-16 21.29.43.jpg", cover_source="own_photo",
          cover_status="unreviewed", tags=["Krimi"])
    _book("9780306406157", "Wohnzimmer", None, None, None, "ready",
          source="manual", title="Book D")
    conn.commit()


@pytest.fixture
def seeded_db(empty_db):
    """empty_db with the standard seed applied."""
    _seed(empty_db)
    return empty_db


def _snapshot_workbook(seeded_db) -> object:
    """Run write_snapshot into an in-memory buffer and return the loaded workbook."""
    buf = io.BytesIO()
    write_snapshot(seeded_db, buf, NOW)
    buf.seek(0)
    return load_workbook(buf)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_write_snapshot_produces_xlsx(seeded_db) -> None:
    # write_snapshot should produce a file that openpyxl can open without error.
    buf = io.BytesIO()
    write_snapshot(seeded_db, buf, NOW)
    buf.seek(0)
    wb = load_workbook(buf)
    assert wb.active is not None


def test_write_snapshot_header_matches_snapshot_fields(seeded_db) -> None:
    # The header row must be exactly SNAPSHOT_FIELDS, in order.
    ws = _snapshot_workbook(seeded_db).active
    header = [cell.value for cell in ws[1]]
    assert header == SNAPSHOT_FIELDS


def test_snapshot_fields_covers_field_map_and_tags() -> None:
    # SNAPSHOT_FIELDS must contain every FIELD_MAP key and TAGS_HEADER -- nothing
    # from the import vocabulary should be silently missing from the snapshot.
    assert set(SNAPSHOT_FIELDS) == set(FIELD_MAP) | {TAGS_HEADER}


def test_write_snapshot_row_count(seeded_db) -> None:
    # 4 books in the seed -> 4 data rows (plus 1 header = 5 total rows in xlsx).
    ws = _snapshot_workbook(seeded_db).active
    assert ws.max_row == 5


def test_write_snapshot_returns_book_count(seeded_db) -> None:
    buf = io.BytesIO()
    count = write_snapshot(seeded_db, buf, NOW)
    assert count == 4


def test_write_snapshot_values_round_trip(seeded_db) -> None:
    # Book A's key fields must survive the snapshot intact.
    ws = _snapshot_workbook(seeded_db).active
    header = [cell.value for cell in ws[1]]

    # Find Book A's row (isbn13 = 9783423058087).
    book_a_row = None
    for row in ws.iter_rows(min_row=2, values_only=True):
        record = dict(zip(header, row))
        if record["isbn13"] == "9783423058087":
            book_a_row = record
            break

    assert book_a_row is not None, "Book A not found in snapshot"
    assert book_a_row["title"] == "Book A"
    assert book_a_row["room"] == "Magazin"
    assert book_a_row["space_label"] == "rack 01"
    assert book_a_row["bin_label"] == "box 01"
    assert book_a_row["position"] == 1.0
    assert book_a_row["book_status"] == "ready"
    assert book_a_row["revision_source"] == "isbndb"
    assert book_a_row["cover_ref"] == "https://img/a.jpg"
    assert book_a_row["cover_source"] == "isbndb"
    assert book_a_row["tags"] == "Schweden, Thriller"


def test_write_snapshot_revisionless_book_included(seeded_db) -> None:
    # The photo book has no revision -- it must appear with NULL bib fields,
    # not be absent from the snapshot.
    ws = _snapshot_workbook(seeded_db).active
    header = [cell.value for cell in ws[1]]
    photo_rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        record = dict(zip(header, row))
        if record["isbn13"] is None:
            photo_rows.append(record)

    assert len(photo_rows) == 1
    photo = photo_rows[0]
    assert photo["title"] is None
    assert photo["revision_source"] is None
    assert photo["cover_ref"] == "rack_01 2026-02-16 21.29.43.jpg"
    assert photo["tags"] == "Krimi"


def test_write_snapshot_empty_db_writes_header_only(empty_db) -> None:
    # An empty database should produce an xlsx with just the header row.
    buf = io.BytesIO()
    count = write_snapshot(empty_db, buf, NOW)
    buf.seek(0)
    ws = load_workbook(buf).active
    assert ws.max_row == 1
    assert count == 0


def test_write_snapshot_isbn13_is_text_cell(seeded_db) -> None:
    # ISBNs must be written as text cells -- the whole reason for xlsx over CSV.
    # openpyxl data_type "s" means string; "n" would mean number (corrupted).
    buf = io.BytesIO()
    write_snapshot(seeded_db, buf, NOW)
    buf.seek(0)
    ws = load_workbook(buf).active
    header = [cell.value for cell in ws[1]]
    isbn_col = header.index("isbn13") + 1   # 1-based column index

    for row_idx in range(2, ws.max_row + 1):
        cell = ws.cell(row=row_idx, column=isbn_col)
        if cell.value is not None:
            assert cell.data_type == "s", (
                f"Row {row_idx}: isbn13 cell has data_type {cell.data_type!r}, "
                f"expected 's' (string). Value: {cell.value!r}"
            )
