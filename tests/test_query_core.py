"""
tests/test_query_core.py — Tests for the pure read layer (query_core.py).

These tests ARE the spec for query_core. They use proto_db (the prototype
schema on an in-memory connection) and seed a small, known dataset that
exercises every query's logic: the room filter, the NULL-isbn13 photo books,
the revision_source IS NOT NULL bib-check, the location hierarchy, and the
cover fields.

Seed layout (used across most tests):
  • 2 books in "Magazin", rack 01, box 01  — both with bib data (isbndb)
  • 1 book in "Magazin", rack 01, box 02  — photo-only (isbn13=NULL, own_photo)
  • 1 book in "Wohnzimmer", no space/bin  — bib data (manual)
  Total: 4 books, 3 with bib, 1 photo-only.

Extended seed for books_by_title / books_by_author / books_by_tags tests
(populated_db fixture, defined below):
  Adds 3 more books to the base seed, chosen to exercise substring matching,
  multi-author overlap, tag AND/OR logic, and the dedup correctness requirement.
"""

import pytest

from haddolib.query_core import query, rooms, spaces, bins, space_count, \
    location_combo_count, book_count, book_count_with_bib, \
    book_count_photo_only, count_by_status, count_by_revision_source, \
    count_by_cover_source, count_by_cover_status, \
    distinct_statuses, distinct_revision_sources, \
    distinct_cover_sources, distinct_cover_statuses, \
    books_by_bin, books_by_title, books_by_author, books_by_tags, books_by_ids, \
    tag_stats, all_books

TS = "2026-06-20T12:00:00"


# ---------------------------------------------------------------------------
# Seed helper
# ---------------------------------------------------------------------------

def _seed(conn) -> None:
    """Insert the standard 4-book dataset into proto_db."""

    def _book(isbn13, room, space, bin_label, book_status, cover_ref=None,
              cover_source=None, cover_status=None, source=None, title=None,
              position=None, tags=None):
        cur = conn.execute(
            "INSERT INTO book (isbn13, room, space_label, bin_label, position, book_status, "
            "preferred_cover_id, created_at) VALUES (?,?,?,?,?,?,NULL,?)",
            (isbn13, room, space, bin_label, position, book_status, TS),
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
                "INSERT INTO cover (book_id, cover_ref, cover_source, cover_status, created_at) "
                "VALUES (?,?,?,?,?)",
                (book_id, cover_ref, cover_source, cover_status, TS),
            )
            conn.execute(
                "UPDATE book SET preferred_cover_id = ? WHERE book_id = ?",
                (cur2.lastrowid, book_id),
            )
        if tags:
            for tag_name in tags:
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
                    "INSERT INTO book_tag (book_id, tag_id) VALUES (?, ?)",
                    (book_id, tag_id),
                )
        return book_id

    # 2 ISBN books in Magazin / rack 01 / box 01 (positions 1 and 2)
    _book("9783423058087", "Magazin", "rack 01", "box 01", "ready",
          cover_ref="https://img/a.jpg", cover_source="isbndb",
          cover_status="beautiful", source="isbndb", title="Book A",
          position=1.0, tags=["Thriller", "Schweden"])
    _book("9781234567897", "Magazin", "rack 01", "box 01", "needs_cover",
          cover_ref="https://img/b.jpg", cover_source="isbndb",
          cover_status="unreviewed", source="isbndb", title="Book B",
          position=2.0)

    # 1 photo-only book in Magazin / rack 01 / box 02 (no isbn13, no revision)
    _book(None, "Magazin", "rack 01", "box 02", "needs_search",
          cover_ref="rack_01 2026-02-16 21.29.43.jpg", cover_source="own_photo",
          cover_status="unreviewed", position=1.0, tags=["Krimi"])

    # 1 book in Wohnzimmer, no space/bin, manual bib
    _book("9780306406157", "Wohnzimmer", None, None, "ready",
          source="manual", title="Book D")

    conn.commit()


@pytest.fixture
def db(proto_db):
    """proto_db with the standard seed applied."""
    _seed(proto_db)
    return proto_db


# ---------------------------------------------------------------------------
# rooms()
# ---------------------------------------------------------------------------

def test_rooms_returns_sorted_comma_list(db) -> None:
    result = rooms(db)
    assert result == "Magazin, Wohnzimmer"


def test_rooms_empty_when_no_books(proto_db) -> None:
    assert rooms(proto_db) == ""


# ---------------------------------------------------------------------------
# spaces()
# ---------------------------------------------------------------------------

def test_spaces_returns_sorted_list_for_room(db) -> None:
    result = spaces(db, "Magazin")
    assert result == "rack 01"          # only one rack in seed


def test_spaces_empty_for_room_with_no_spaces(db) -> None:
    # Wohnzimmer book has space_label=NULL
    assert spaces(db, "Wohnzimmer") == ""


def test_spaces_requires_room(db) -> None:
    with pytest.raises(ValueError, match="non-empty room"):
        spaces(db, "")


# ---------------------------------------------------------------------------
# bins()
# ---------------------------------------------------------------------------

def test_bins_returns_sorted_list_for_room_and_space(db) -> None:
    result = bins(db, "Magazin", "rack 01")
    assert result == "box 01, box 02"


def test_bins_requires_room(db) -> None:
    with pytest.raises(ValueError, match="non-empty room"):
        bins(db, "", "rack 01")


def test_bins_requires_space(db) -> None:
    with pytest.raises(ValueError, match="non-empty space"):
        bins(db, "Magazin", "")


# ---------------------------------------------------------------------------
# space_count()
# ---------------------------------------------------------------------------

def test_space_count_for_room(db) -> None:
    assert space_count(db, "Magazin") == 1


def test_space_count_zero_for_room_with_no_spaces(db) -> None:
    assert space_count(db, "Wohnzimmer") == 0


def test_space_count_requires_room(db) -> None:
    with pytest.raises(ValueError, match="non-empty room"):
        space_count(db, "")


# ---------------------------------------------------------------------------
# location_combo_count()
# ---------------------------------------------------------------------------

def test_location_combo_count(db) -> None:
    # Magazin/rack 01/box 01 and Magazin/rack 01/box 02 → 2 combos.
    # Wohnzimmer book has no space/bin → not counted.
    assert location_combo_count(db) == 2


def test_location_combo_count_zero_when_empty(proto_db) -> None:
    assert location_combo_count(proto_db) == 0


# ---------------------------------------------------------------------------
# book_count()
# ---------------------------------------------------------------------------

def test_book_count_all_rooms(db) -> None:
    assert book_count(db) == 4


def test_book_count_filtered_by_room(db) -> None:
    assert book_count(db, "Magazin") == 3
    assert book_count(db, "Wohnzimmer") == 1


def test_book_count_empty_string_means_all(db) -> None:
    assert book_count(db, "") == 4


# ---------------------------------------------------------------------------
# book_count_with_bib()
# ---------------------------------------------------------------------------

def test_book_count_with_bib_all_rooms(db) -> None:
    # 3 books have a revision (Book A, B, D); the photo-only book does not.
    assert book_count_with_bib(db) == 3


def test_book_count_with_bib_filtered(db) -> None:
    assert book_count_with_bib(db, "Magazin") == 2      # A and B; not the photo book
    assert book_count_with_bib(db, "Wohnzimmer") == 1   # D


# ---------------------------------------------------------------------------
# book_count_photo_only()
# ---------------------------------------------------------------------------

def test_book_count_photo_only_all_rooms(db) -> None:
    # Only one book has isbn13=NULL (the own_photo book in Magazin).
    assert book_count_photo_only(db) == 1


def test_book_count_photo_only_filtered(db) -> None:
    assert book_count_photo_only(db, "Magazin") == 1
    assert book_count_photo_only(db, "Wohnzimmer") == 0


# ---------------------------------------------------------------------------
# count_by_status()
# ---------------------------------------------------------------------------

def test_count_by_status_all_rooms(db) -> None:
    assert count_by_status(db, "ready") == 2          # Book A (Magazin) + D (Wohnzimmer)
    assert count_by_status(db, "needs_cover") == 1    # Book B
    assert count_by_status(db, "needs_search") == 1   # photo book
    assert count_by_status(db, "nonexistent") == 0


def test_count_by_status_filtered(db) -> None:
    assert count_by_status(db, "ready", "Magazin") == 1       # only Book A
    assert count_by_status(db, "ready", "Wohnzimmer") == 1    # only Book D


def test_count_by_status_requires_status(db) -> None:
    with pytest.raises(ValueError, match="non-empty status"):
        count_by_status(db, "")


# ---------------------------------------------------------------------------
# count_by_revision_source()
# ---------------------------------------------------------------------------

def test_count_by_revision_source_all_rooms(db) -> None:
    assert count_by_revision_source(db, "isbndb") == 2    # A and B
    assert count_by_revision_source(db, "manual") == 1    # D
    assert count_by_revision_source(db, "photosearch") == 0


def test_count_by_revision_source_filtered(db) -> None:
    assert count_by_revision_source(db, "isbndb", "Magazin") == 2
    assert count_by_revision_source(db, "isbndb", "Wohnzimmer") == 0


def test_count_by_revision_source_requires_source(db) -> None:
    with pytest.raises(ValueError, match="non-empty source"):
        count_by_revision_source(db, "")


# ---------------------------------------------------------------------------
# count_by_cover_source()
# ---------------------------------------------------------------------------

def test_count_by_cover_source_all_rooms(db) -> None:
    assert count_by_cover_source(db, "isbndb") == 2       # A and B
    assert count_by_cover_source(db, "own_photo") == 1    # photo book
    assert count_by_cover_source(db, "thalia") == 0


def test_count_by_cover_source_filtered(db) -> None:
    assert count_by_cover_source(db, "own_photo", "Magazin") == 1
    assert count_by_cover_source(db, "own_photo", "Wohnzimmer") == 0


def test_count_by_cover_source_requires_source(db) -> None:
    with pytest.raises(ValueError, match="non-empty source"):
        count_by_cover_source(db, "")


# ---------------------------------------------------------------------------
# count_by_cover_status()
# ---------------------------------------------------------------------------

def test_count_by_cover_status_all_rooms(db) -> None:
    assert count_by_cover_status(db, "beautiful") == 1      # A
    assert count_by_cover_status(db, "unreviewed") == 2     # B and photo book
    assert count_by_cover_status(db, "missing") == 0


def test_count_by_cover_status_filtered(db) -> None:
    assert count_by_cover_status(db, "unreviewed", "Magazin") == 2
    assert count_by_cover_status(db, "unreviewed", "Wohnzimmer") == 0


def test_count_by_cover_status_requires_status(db) -> None:
    with pytest.raises(ValueError, match="non-empty status"):
        count_by_cover_status(db, "")


# ---------------------------------------------------------------------------
# query() dispatcher
# ---------------------------------------------------------------------------

def test_dispatcher_unknown_name_raises(db) -> None:
    with pytest.raises(ValueError, match="unknown query"):
        query(db, "totally_unknown")


def test_dispatcher_rooms(db) -> None:
    assert query(db, "rooms") == "Magazin, Wohnzimmer"


def test_dispatcher_spaces(db) -> None:
    assert query(db, "spaces", "Magazin") == "rack 01"


def test_dispatcher_bins(db) -> None:
    assert query(db, "bins", "Magazin", "rack 01") == "box 01, box 02"


def test_dispatcher_space_count(db) -> None:
    assert query(db, "space_count", "Magazin") == 1


def test_dispatcher_location_combo_count(db) -> None:
    assert query(db, "location_combo_count") == 2


def test_dispatcher_book_count_no_room(db) -> None:
    assert query(db, "book_count") == 4


def test_dispatcher_book_count_with_room(db) -> None:
    assert query(db, "book_count", "Magazin") == 3


def test_dispatcher_book_count_with_bib(db) -> None:
    assert query(db, "book_count_with_bib") == 3


def test_dispatcher_book_count_photo_only(db) -> None:
    assert query(db, "book_count_photo_only") == 1


def test_dispatcher_count_by_status_no_room(db) -> None:
    assert query(db, "count_by_status", "ready") == 2


def test_dispatcher_count_by_status_with_room(db) -> None:
    assert query(db, "count_by_status", "ready", "Magazin") == 1


def test_dispatcher_count_by_revision_source(db) -> None:
    assert query(db, "count_by_revision_source", "isbndb") == 2


def test_dispatcher_count_by_cover_source(db) -> None:
    assert query(db, "count_by_cover_source", "own_photo") == 1


def test_dispatcher_count_by_cover_status(db) -> None:
    assert query(db, "count_by_cover_status", "beautiful") == 1


def test_dispatcher_wrong_param_count_raises(db) -> None:
    # spaces() needs exactly 1 param, not 0 or 2
    with pytest.raises(ValueError):
        query(db, "spaces")
    with pytest.raises(ValueError):
        query(db, "spaces", "Magazin", "extra")


# ---------------------------------------------------------------------------
# distinct_statuses()
# ---------------------------------------------------------------------------

def test_distinct_statuses(db) -> None:
    # Seed has: ready (x2), needs_cover, needs_search → sorted alphabetically
    assert distinct_statuses(db) == "needs_cover, needs_search, ready"


def test_distinct_statuses_empty_when_no_books(proto_db) -> None:
    assert distinct_statuses(proto_db) == ""


# ---------------------------------------------------------------------------
# distinct_revision_sources()
# ---------------------------------------------------------------------------

def test_distinct_revision_sources(db) -> None:
    # Seed has: isbndb (A, B), manual (D); photo book has no revision
    assert distinct_revision_sources(db) == "isbndb, manual"


def test_distinct_revision_sources_empty_when_no_books(proto_db) -> None:
    assert distinct_revision_sources(proto_db) == ""


# ---------------------------------------------------------------------------
# distinct_cover_sources()
# ---------------------------------------------------------------------------

def test_distinct_cover_sources(db) -> None:
    # Seed has: isbndb (A, B), own_photo (photo book); D has no cover
    assert distinct_cover_sources(db) == "isbndb, own_photo"


def test_distinct_cover_sources_empty_when_no_books(proto_db) -> None:
    assert distinct_cover_sources(proto_db) == ""


# ---------------------------------------------------------------------------
# distinct_cover_statuses()
# ---------------------------------------------------------------------------

def test_distinct_cover_statuses(db) -> None:
    # Seed has: beautiful (A), unreviewed (B, photo book); D has no cover
    assert distinct_cover_statuses(db) == "beautiful, unreviewed"


def test_distinct_cover_statuses_empty_when_no_books(proto_db) -> None:
    assert distinct_cover_statuses(proto_db) == ""


# ---------------------------------------------------------------------------
# dispatcher — vocabulary queries
# ---------------------------------------------------------------------------

def test_dispatcher_distinct_statuses(db) -> None:
    assert query(db, "distinct_statuses") == "needs_cover, needs_search, ready"


def test_dispatcher_distinct_revision_sources(db) -> None:
    assert query(db, "distinct_revision_sources") == "isbndb, manual"


def test_dispatcher_distinct_cover_sources(db) -> None:
    assert query(db, "distinct_cover_sources") == "isbndb, own_photo"


def test_dispatcher_distinct_cover_statuses(db) -> None:
    assert query(db, "distinct_cover_statuses") == "beautiful, unreviewed"


# ---------------------------------------------------------------------------
# books_by_bin()
# ---------------------------------------------------------------------------

def test_books_by_bin_returns_list_of_dicts(db) -> None:
    result = books_by_bin(db, "Magazin", "rack 01", "box 01")
    assert isinstance(result, list)
    assert all(isinstance(r, dict) for r in result)


def test_books_by_bin_correct_count(db) -> None:
    assert len(books_by_bin(db, "Magazin", "rack 01", "box 01")) == 2
    assert len(books_by_bin(db, "Magazin", "rack 01", "box 02")) == 1


def test_books_by_bin_position_order(db) -> None:
    # Box 01 has Book A at position 1.0 and Book B at position 2.0.
    result = books_by_bin(db, "Magazin", "rack 01", "box 01")
    assert result[0]["title"] == "Book A"
    assert result[1]["title"] == "Book B"


def test_books_by_bin_contains_expected_fields(db) -> None:
    result = books_by_bin(db, "Magazin", "rack 01", "box 01")
    row = result[0]
    # Core identity fields
    assert "book_id" in row
    assert "isbn13" in row
    # Bibliographic fields
    assert "title" in row
    assert "authors" in row
    # Location fields
    assert "room" in row
    assert "space_label" in row
    assert "bin_label" in row
    assert "position" in row
    # Cover fields
    assert "cover_ref" in row
    assert "cover_source" in row
    assert "cover_status" in row
    # Tags — the aggregated extra field
    assert "tags" in row


def test_books_by_bin_tags_comma_separated(db) -> None:
    result = books_by_bin(db, "Magazin", "rack 01", "box 01")
    # Book A has tags ["Thriller", "Schweden"] — alphabetical order: Schweden < Thriller
    assert result[0]["tags"] == "Schweden, Thriller"


def test_books_by_bin_tags_none_when_no_tags(db) -> None:
    # Book B has no tags — tags field should be None
    result = books_by_bin(db, "Magazin", "rack 01", "box 01")
    assert result[1]["tags"] is None

def test_books_by_bin_tags_alphabetical_order(proto_db) -> None:
    # Insert tags in reverse-alphabetical order (Zebra before Apfel) and
    # verify they come back sorted — this is the spec for _TAGS_SUBQUERY.
    cur = proto_db.execute(
        "INSERT INTO book (isbn13, room, space_label, bin_label, position, "
        "book_status, preferred_cover_id, created_at) VALUES (?,?,?,?,?,?,NULL,?)",
        ("9780000000002", "Magazin", "rack 99", "box 99", 1.0, "ready", "2026-01-01T00:00:00"),
    )
    book_id = cur.lastrowid
    for name in ["Zebra", "Mitte", "Apfel"]:   # inserted in reverse-alpha order
        tag_id = proto_db.execute(
            "INSERT INTO tag (name) VALUES (?)", (name,)
        ).lastrowid
        proto_db.execute(
            "INSERT INTO book_tag (book_id, tag_id) VALUES (?, ?)", (book_id, tag_id)
        )
    proto_db.commit()
    result = books_by_bin(proto_db, "Magazin", "rack 99", "box 99")
    assert result[0]["tags"] == "Apfel, Mitte, Zebra"


def test_books_by_bin_photo_book_has_no_isbn13(db) -> None:
    result = books_by_bin(db, "Magazin", "rack 01", "box 02")
    assert result[0]["isbn13"] is None
    assert result[0]["cover_ref"] == "rack_01 2026-02-16 21.29.43.jpg"


def test_books_by_bin_empty_for_nonexistent_bin(db) -> None:
    result = books_by_bin(db, "Magazin", "rack 01", "box 99")
    assert result == []


def test_books_by_bin_requires_room(db) -> None:
    with pytest.raises(ValueError, match="non-empty room"):
        books_by_bin(db, "", "rack 01", "box 01")


def test_books_by_bin_requires_space(db) -> None:
    with pytest.raises(ValueError, match="non-empty space"):
        books_by_bin(db, "Magazin", "", "box 01")


def test_books_by_bin_requires_bin_label(db) -> None:
    with pytest.raises(ValueError, match="non-empty bin_label"):
        books_by_bin(db, "Magazin", "rack 01", "")


def test_books_by_bin_rejects_blank_room(db) -> None:
    # Whitespace-only is also blank
    with pytest.raises(ValueError, match="non-empty room"):
        books_by_bin(db, "   ", "rack 01", "box 01")


def test_books_by_bin_strips_whitespace_from_params(db) -> None:
    # Leading/trailing whitespace on valid values is tolerated and stripped
    result = books_by_bin(db, " Magazin ", " rack 01 ", " box 01 ")
    assert len(result) == 2


def test_books_by_bin_no_cross_room_bleed(db) -> None:
    # All returned rows must belong to the requested room
    result = books_by_bin(db, "Magazin", "rack 01", "box 01")
    assert all(r["room"] == "Magazin" for r in result)


# ===========================================================================
# Extended fixture for books_by_title / books_by_author / books_by_tags
#
# Builds on the base _seed (4 books) and adds 3 more, chosen to exercise:
#   - substring overlaps in titles ("Krieg" appears in two titles)
#   - the same author across multiple books (H.G. Wells)
#   - tag AND/OR logic and the dedup-correctness requirement
#
# Full dataset (7 books):
#   Book A   — "Book A",               isbndb,  rack 01 / box 01,  tags: Thriller, Schweden
#   Book B   — "Book B",               isbndb,  rack 01 / box 01,  tags: (none)
#   photo    — None (no revision),     own_photo, rack 01 / box 02, tags: Krimi
#   Book D   — "Book D",               manual,  Wohnzimmer,        tags: (none)
#   Welten   — "Der Krieg der Welten", isbndb,  rack 02 / box 01,  tags: Klassiker, SciFi
#   Maschine — "Die Zeitmaschine",     isbndb,  rack 02 / box 01,  tags: Klassiker
#   Frieden  — "Krieg und Frieden",    isbndb,  rack 02 / box 02,  tags: Klassiker
# ===========================================================================

@pytest.fixture
def populated_db(proto_db):
    """Base seed + 3 extra books for title/author/tag query testing."""
    _seed(proto_db)

    def _extra(isbn13, title, authors, space, bin_label, position, tags=None):
        cur = proto_db.execute(
            "INSERT INTO book (isbn13, room, space_label, bin_label, position, "
            "book_status, preferred_cover_id, created_at) VALUES (?,?,?,?,?,'ready',NULL,?)",
            (isbn13, "Magazin", space, bin_label, position, TS),
        )
        book_id = cur.lastrowid
        proto_db.execute(
            "INSERT INTO book_revision (book_id, source, title, authors, created_at) "
            "VALUES (?, 'isbndb', ?, ?, ?)",
            (book_id, title, authors, TS),
        )
        for tag_name in (tags or []):
            row = proto_db.execute(
                "SELECT tag_id FROM tag WHERE name = ?", (tag_name,)
            ).fetchone()
            tag_id = row["tag_id"] if row else proto_db.execute(
                "INSERT INTO tag (name) VALUES (?)", (tag_name,)
            ).lastrowid
            proto_db.execute(
                "INSERT INTO book_tag (book_id, tag_id) VALUES (?, ?)",
                (book_id, tag_id),
            )

    _extra("9783492701600", "Der Krieg der Welten", "H.G. Wells",
           "rack 02", "box 01", 1.0, tags=["Klassiker", "SciFi"])
    _extra("9783442740789", "Die Zeitmaschine",     "H.G. Wells",
           "rack 02", "box 01", 2.0, tags=["Klassiker"])
    _extra("9783866470194", "Krieg und Frieden",    "Lew Tolstoi",
           "rack 02", "box 02", 1.0, tags=["Klassiker"])

    proto_db.commit()
    return proto_db


def _titles(rows: list[dict]) -> set[str]:
    """Extract the set of title strings from a list[dict] result."""
    return {r["title"] for r in rows}


# ---------------------------------------------------------------------------
# books_by_title()
# ---------------------------------------------------------------------------

def test_books_by_title_exact_match(populated_db) -> None:
    rows = books_by_title(populated_db, "Die Zeitmaschine")
    assert len(rows) == 1
    assert rows[0]["title"] == "Die Zeitmaschine"


def test_books_by_title_substring_match(populated_db) -> None:
    # "Krieg" appears in both "Der Krieg der Welten" and "Krieg und Frieden"
    rows = books_by_title(populated_db, "Krieg")
    assert _titles(rows) == {"Der Krieg der Welten", "Krieg und Frieden"}


def test_books_by_title_case_insensitive(populated_db) -> None:
    rows_lower = books_by_title(populated_db, "krieg")
    rows_upper = books_by_title(populated_db, "KRIEG")
    assert _titles(rows_lower) == _titles(rows_upper)


def test_books_by_title_ordered_by_shelf_position(populated_db) -> None:
    # "Krieg" matches Welten (rack 02 / box 01 / pos 1.0) and
    # Frieden (rack 02 / box 02 / pos 1.0) — box 01 comes before box 02.
    rows = books_by_title(populated_db, "Krieg")
    assert rows[0]["title"] == "Der Krieg der Welten"
    assert rows[1]["title"] == "Krieg und Frieden"


def test_books_by_title_tags_included(populated_db) -> None:
    rows = books_by_title(populated_db, "Die Zeitmaschine")
    assert rows[0]["tags"] == "Klassiker"


def test_books_by_title_no_match_returns_empty(populated_db) -> None:
    assert books_by_title(populated_db, "Zauberberg") == []


def test_books_by_title_raises_on_blank(populated_db) -> None:
    with pytest.raises(ValueError, match="search string"):
        books_by_title(populated_db, "")


def test_books_by_title_raises_on_whitespace_only(populated_db) -> None:
    with pytest.raises(ValueError, match="search string"):
        books_by_title(populated_db, "   ")


def test_books_by_title_strips_whitespace_from_search(populated_db) -> None:
    rows = books_by_title(populated_db, " Zeitmaschine ")
    assert len(rows) == 1


def test_books_by_title_result_has_full_fields(populated_db) -> None:
    rows = books_by_title(populated_db, "Zeitmaschine")
    row = rows[0]
    assert "isbn13" in row
    assert "cover_ref" in row
    assert "room" in row
    assert "tags" in row


# ---------------------------------------------------------------------------
# books_by_author()
# ---------------------------------------------------------------------------

def test_books_by_author_finds_all_books_by_one_author(populated_db) -> None:
    rows = books_by_author(populated_db, "Wells")
    assert _titles(rows) == {"Der Krieg der Welten", "Die Zeitmaschine"}


def test_books_by_author_substring_on_first_name(populated_db) -> None:
    rows = books_by_author(populated_db, "Lew")
    assert len(rows) == 1
    assert rows[0]["title"] == "Krieg und Frieden"


def test_books_by_author_case_insensitive(populated_db) -> None:
    rows_lower = books_by_author(populated_db, "wells")
    rows_upper = books_by_author(populated_db, "WELLS")
    assert _titles(rows_lower) == _titles(rows_upper)


def test_books_by_author_ordered_by_shelf_position(populated_db) -> None:
    # Both Wells books are in rack 02 / box 01: Welten at pos 1.0, Zeitmaschine at pos 2.0.
    rows = books_by_author(populated_db, "Wells")
    assert rows[0]["title"] == "Der Krieg der Welten"
    assert rows[1]["title"] == "Die Zeitmaschine"


def test_books_by_author_tags_included(populated_db) -> None:
    rows = books_by_author(populated_db, "Wells")
    tags_by_title = {r["title"]: r["tags"] for r in rows}
    assert "Klassiker" in tags_by_title["Der Krieg der Welten"]
    assert "SciFi" in tags_by_title["Der Krieg der Welten"]
    assert tags_by_title["Die Zeitmaschine"] == "Klassiker"


def test_books_by_author_no_match_returns_empty(populated_db) -> None:
    assert books_by_author(populated_db, "Kafka") == []


def test_books_by_author_raises_on_blank(populated_db) -> None:
    with pytest.raises(ValueError, match="search string"):
        books_by_author(populated_db, "")


def test_books_by_author_raises_on_whitespace_only(populated_db) -> None:
    with pytest.raises(ValueError, match="search string"):
        books_by_author(populated_db, "   ")


def test_books_by_author_strips_whitespace_from_search(populated_db) -> None:
    rows = books_by_author(populated_db, " Tolstoi ")
    assert len(rows) == 1


def test_books_by_author_result_has_full_fields(populated_db) -> None:
    rows = books_by_author(populated_db, "Wells")
    row = rows[0]
    assert "isbn13" in row
    assert "cover_ref" in row
    assert "room" in row
    assert "tags" in row


# ---------------------------------------------------------------------------
# books_by_tags()
# ---------------------------------------------------------------------------

def test_books_by_tags_match_any_single_tag(populated_db) -> None:
    rows = books_by_tags(populated_db, ["SciFi"], match_all=False)
    assert _titles(rows) == {"Der Krieg der Welten"}


def test_books_by_tags_match_any_two_tags_union(populated_db) -> None:
    # SciFi OR Thriller → Krieg der Welten (SciFi) + Book A (Thriller)
    rows = books_by_tags(populated_db, ["SciFi", "Thriller"], match_all=False)
    assert _titles(rows) == {"Der Krieg der Welten", "Book A"}


def test_books_by_tags_match_any_returns_all_tagged_books(populated_db) -> None:
    # All four tags covers every book that has any tag at all.
    rows = books_by_tags(populated_db, ["Klassiker", "SciFi", "Thriller", "Krimi"],
                         match_all=False)
    # Book A (Thriller), photo (Krimi), Welten (SciFi+Klassiker),
    # Zeitmaschine (Klassiker), Frieden (Klassiker) — 5 books
    assert len(rows) == 5


def test_books_by_tags_match_all_single_tag_same_as_match_any(populated_db) -> None:
    any_rows = books_by_tags(populated_db, ["Klassiker"], match_all=False)
    all_rows = books_by_tags(populated_db, ["Klassiker"], match_all=True)
    assert _titles(any_rows) == _titles(all_rows)


def test_books_by_tags_match_all_two_tags_intersection(populated_db) -> None:
    # Klassiker AND SciFi → only "Der Krieg der Welten" has both
    rows = books_by_tags(populated_db, ["Klassiker", "SciFi"], match_all=True)
    assert _titles(rows) == {"Der Krieg der Welten"}


def test_books_by_tags_match_all_impossible_returns_empty(populated_db) -> None:
    # No book has both SciFi and Thriller.
    rows = books_by_tags(populated_db, ["SciFi", "Thriller"], match_all=True)
    assert rows == []


def test_books_by_tags_result_ordered_by_shelf_position(populated_db) -> None:
    # Klassiker books: Welten (rack 02/box 01/pos 1.0), Zeitmaschine (rack 02/box 01/pos 2.0),
    # Frieden (rack 02/box 02/pos 1.0) — physical order, not alphabetical.
    rows = books_by_tags(populated_db, ["Klassiker"], match_all=False)
    titles = [r["title"] for r in rows]
    assert titles.index("Der Krieg der Welten") < titles.index("Die Zeitmaschine")
    assert titles.index("Die Zeitmaschine") < titles.index("Krieg und Frieden")


def test_books_by_tags_result_has_all_tags_not_just_matched(populated_db) -> None:
    # Query by SciFi, but the tags field for Krieg der Welten must show ALL its tags.
    rows = books_by_tags(populated_db, ["SciFi"], match_all=False)
    row = rows[0]
    assert "Klassiker" in row["tags"]
    assert "SciFi" in row["tags"]


def test_books_by_tags_result_has_full_fields(populated_db) -> None:
    rows = books_by_tags(populated_db, ["SciFi"], match_all=False)
    row = rows[0]
    assert "isbn13" in row
    assert "cover_ref" in row
    assert "room" in row


def test_books_by_tags_duplicate_input_does_not_corrupt_match_all(populated_db) -> None:
    # ["Klassiker", "Klassiker"] must behave as ["Klassiker"] — not require two
    # distinct matches (which would return nothing).
    rows_deduped = books_by_tags(populated_db, ["Klassiker"],             match_all=True)
    rows_duped   = books_by_tags(populated_db, ["Klassiker", "Klassiker"], match_all=True)
    assert _titles(rows_deduped) == _titles(rows_duped)


def test_books_by_tags_unknown_tag_match_any_returns_empty(populated_db) -> None:
    assert books_by_tags(populated_db, ["Nonexistent"], match_all=False) == []


def test_books_by_tags_unknown_tag_match_all_returns_empty(populated_db) -> None:
    rows = books_by_tags(populated_db, ["Klassiker", "Nonexistent"], match_all=True)
    assert rows == []


def test_books_by_tags_raises_on_empty_list(populated_db) -> None:
    with pytest.raises(ValueError, match="non-empty tag"):
        books_by_tags(populated_db, [], match_all=False)


def test_books_by_tags_raises_on_list_of_blank_strings(populated_db) -> None:
    with pytest.raises(ValueError, match="non-empty tag"):
        books_by_tags(populated_db, ["", "  "], match_all=False)


def test_books_by_tags_blank_entries_silently_dropped(populated_db) -> None:
    # Mixed blank and valid: blanks stripped, query proceeds on valid tags only.
    rows = books_by_tags(populated_db, ["", "SciFi", "  "], match_all=False)
    assert _titles(rows) == {"Der Krieg der Welten"}

# ---------------------------------------------------------------------------
# books_by_ids
# ---------------------------------------------------------------------------

def test_books_by_ids_returns_correct_books(populated_db) -> None:
    # Fetch a known subset by id — use books_by_bin to get their ids first.
    all_books_in_bin = books_by_bin(populated_db, "Magazin", "rack 01", "box 01")
    ids = [b["book_id"] for b in all_books_in_bin]
    assert len(ids) >= 2

    result = books_by_ids(populated_db, ids)
    assert [r["book_id"] for r in result] == ids


def test_books_by_ids_preserves_caller_order(populated_db) -> None:
    # Fetch books in reverse id order and assert the result matches that order —
    # this is the key invariant: IN query order is not guaranteed by SQLite.
    all_books_in_bin = books_by_bin(populated_db, "Magazin", "rack 01", "box 01")
    ids_reversed = list(reversed([b["book_id"] for b in all_books_in_bin]))
    assert len(ids_reversed) >= 2

    result = books_by_ids(populated_db, ids_reversed)
    assert [r["book_id"] for r in result] == ids_reversed


def test_books_by_ids_includes_tags(populated_db) -> None:
    all_books_in_bin = books_by_bin(populated_db, "Magazin", "rack 01", "box 01")
    book_a = next(b for b in all_books_in_bin if b["tags"] is not None)
    result = books_by_ids(populated_db, [book_a["book_id"]])
    assert result[0]["tags"] == book_a["tags"]


def test_books_by_ids_raises_on_empty_list(populated_db) -> None:
    with pytest.raises(ValueError, match="at least one book_id"):
        books_by_ids(populated_db, [])

# ---------------------------------------------------------------------------
# tag_stats
# ---------------------------------------------------------------------------

def test_tag_stats_returns_correct_counts(proto_db) -> None:
    # Insert two books; tag A on both, tag B on one only.
    cur = proto_db.execute(
        "INSERT INTO book (isbn13, room, space_label, bin_label, position, "
        "book_status, preferred_cover_id, created_at) VALUES (?,?,?,?,?,?,NULL,?)",
        ("9780000000010", "Magazin", "rack 01", "box 01", 1.0, "ready", "2026-01-01T00:00:00"),
    )
    book1 = cur.lastrowid
    cur = proto_db.execute(
        "INSERT INTO book (isbn13, room, space_label, bin_label, position, "
        "book_status, preferred_cover_id, created_at) VALUES (?,?,?,?,?,?,NULL,?)",
        ("9780000000011", "Magazin", "rack 01", "box 01", 2.0, "ready", "2026-01-01T00:00:00"),
    )
    book2 = cur.lastrowid
    tag_a = proto_db.execute("INSERT INTO tag (name) VALUES (?)", ("Alpha",)).lastrowid
    tag_b = proto_db.execute("INSERT INTO tag (name) VALUES (?)", ("Beta",)).lastrowid
    proto_db.execute("INSERT INTO book_tag (book_id, tag_id) VALUES (?,?)", (book1, tag_a))
    proto_db.execute("INSERT INTO book_tag (book_id, tag_id) VALUES (?,?)", (book2, tag_a))
    proto_db.execute("INSERT INTO book_tag (book_id, tag_id) VALUES (?,?)", (book1, tag_b))
    proto_db.commit()

    result = tag_stats(proto_db)
    result_dict = dict(result)
    assert result_dict["Alpha"] == 2
    assert result_dict["Beta"] == 1


def test_tag_stats_ordered_by_count_desc_then_name_asc(proto_db) -> None:
    # Insert three tags: Zebra(2), Apple(2), Mango(1).
    # Expected order: Apple(2), Zebra(2), Mango(1) — tiebreaker is name asc.
    cur = proto_db.execute(
        "INSERT INTO book (isbn13, room, space_label, bin_label, position, "
        "book_status, preferred_cover_id, created_at) VALUES (?,?,?,?,?,?,NULL,?)",
        ("9780000000020", "Magazin", "rack 01", "box 01", 1.0, "ready", "2026-01-01T00:00:00"),
    )
    book1 = cur.lastrowid
    cur = proto_db.execute(
        "INSERT INTO book (isbn13, room, space_label, bin_label, position, "
        "book_status, preferred_cover_id, created_at) VALUES (?,?,?,?,?,?,NULL,?)",
        ("9780000000021", "Magazin", "rack 01", "box 01", 2.0, "ready", "2026-01-01T00:00:00"),
    )
    book2 = cur.lastrowid
    tag_z = proto_db.execute("INSERT INTO tag (name) VALUES (?)", ("Zebra",)).lastrowid
    tag_a = proto_db.execute("INSERT INTO tag (name) VALUES (?)", ("Apple",)).lastrowid
    tag_m = proto_db.execute("INSERT INTO tag (name) VALUES (?)", ("Mango",)).lastrowid
    for tag_id in (tag_z, tag_a):
        proto_db.execute("INSERT INTO book_tag (book_id, tag_id) VALUES (?,?)", (book1, tag_id))
        proto_db.execute("INSERT INTO book_tag (book_id, tag_id) VALUES (?,?)", (book2, tag_id))
    proto_db.execute("INSERT INTO book_tag (book_id, tag_id) VALUES (?,?)", (book1, tag_m))
    proto_db.commit()

    result = tag_stats(proto_db)
    assert result == [("Apple", 2), ("Zebra", 2), ("Mango", 1)]


def test_tag_stats_includes_orphans_with_count_zero(proto_db) -> None:
    # An orphan tag (no book_tag rows) must appear with count 0.
    proto_db.execute("INSERT INTO tag (name) VALUES (?)", ("Orphan",))
    cur = proto_db.execute(
        "INSERT INTO book (isbn13, room, space_label, bin_label, position, "
        "book_status, preferred_cover_id, created_at) VALUES (?,?,?,?,?,?,NULL,?)",
        ("9780000000030", "Magazin", "rack 01", "box 01", 1.0, "ready", "2026-01-01T00:00:00"),
    )
    book_id = cur.lastrowid
    tag_id = proto_db.execute("INSERT INTO tag (name) VALUES (?)", ("Active",)).lastrowid
    proto_db.execute("INSERT INTO book_tag (book_id, tag_id) VALUES (?,?)", (book_id, tag_id))
    proto_db.commit()

    result = tag_stats(proto_db)
    result_dict = dict(result)
    assert result_dict["Active"] == 1
    assert result_dict["Orphan"] == 0
    # Orphan sorts after Active (lower count)
    assert result.index(("Active", 1)) < result.index(("Orphan", 0))


def test_tag_stats_empty_when_no_tags(proto_db) -> None:
    assert tag_stats(proto_db) == []


def test_tag_stats_alphabetical_order(proto_db) -> None:
    # order_by_count=False: tags come back purely by name, ignoring count.
    cur = proto_db.execute(
        "INSERT INTO book (isbn13, room, space_label, bin_label, position, "
        "book_status, preferred_cover_id, created_at) VALUES (?,?,?,?,?,?,NULL,?)",
        ("9780000000040", "Magazin", "rack 01", "box 01", 1.0, "ready", "2026-01-01T00:00:00"),
    )
    book_id = cur.lastrowid
    for name in ["Zebra", "Apple", "Mango"]:
        tag_id = proto_db.execute("INSERT INTO tag (name) VALUES (?)", (name,)).lastrowid
        proto_db.execute("INSERT INTO book_tag (book_id, tag_id) VALUES (?,?)", (book_id, tag_id))
    proto_db.commit()

    result = tag_stats(proto_db, order_by_count=False)
    assert [name for name, _ in result] == ["Apple", "Mango", "Zebra"]


# ---------------------------------------------------------------------------
# all_books()
# ---------------------------------------------------------------------------

def test_all_books_returns_all_books(db) -> None:
    # Standard seed has 4 books across two rooms.
    result = all_books(db)
    assert len(result) == 4


def test_all_books_empty_when_no_books(proto_db) -> None:
    assert all_books(proto_db) == []


def test_all_books_returns_list_of_dicts(db) -> None:
    result = all_books(db)
    assert isinstance(result, list)
    assert all(isinstance(r, dict) for r in result)


def test_all_books_shelf_order(db) -> None:
    # Seed order: Magazin/rack 01/box 01 pos 1 (Book A), pos 2 (Book B),
    #             Magazin/rack 01/box 02 pos 1 (photo), Wohnzimmer (Book D, NULLs).
    result = all_books(db)
    titles = [r["title"] for r in result]
    assert titles[0] == "Book A"
    assert titles[1] == "Book B"
    assert titles[2] is None      # photo book has no revision → no title
    # Book D (Wohnzimmer, NULL space/bin) sorts last
    assert result[3]["isbn13"] == "9780306406157"


def test_all_books_null_location_sorts_last(db) -> None:
    # Book D has room=Wohnzimmer but space_label=NULL, bin_label=NULL.
    # NULLs sort after non-NULLs in SQLite ASC — it must be the last row.
    result = all_books(db)
    assert result[-1]["isbn13"] == "9780306406157"


def test_all_books_contains_expected_fields(db) -> None:
    result = all_books(db)
    row = result[0]
    for field in ("book_id", "isbn13", "title", "authors", "room",
                  "space_label", "bin_label", "position",
                  "cover_ref", "cover_source", "cover_status", "tags"):
        assert field in row, f"missing field: {field}"


def test_all_books_tags_field_present_and_correct(db) -> None:
    result = all_books(db)
    book_a = next(r for r in result if r["title"] == "Book A")
    assert book_a["tags"] == "Schweden, Thriller"


def test_all_books_tags_none_for_untagged_book(db) -> None:
    result = all_books(db)
    book_b = next(r for r in result if r["title"] == "Book B")
    assert book_b["tags"] is None


def test_all_books_revisionless_book_included(db) -> None:
    # The photo book has no revision — it must still appear with NULL bib fields.
    result = all_books(db)
    photo = next(r for r in result if r["isbn13"] is None)
    assert photo["title"] is None
    assert photo["revision_source"] is None
    assert photo["cover_ref"] == "rack_01 2026-02-16 21.29.43.jpg"
