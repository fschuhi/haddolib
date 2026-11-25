"""
tests/test_roster.py — The roster mapping layer (pure; no database).

These tests ARE the spec for map_row / split_tags / unknown_headers. They use
synthetic rows only; no fixture, no DB. Behaviour that touches the database
(insert, cover/tag update, the import driver) is specified in later test modules.
"""

from haddolib.roster import map_row, split_tags, unknown_headers


def test_full_row_sorts_into_buckets_with_correct_types() -> None:
    row = {
        "isbn13": "9783423058087",
        "room": "Magazin", "space_label": "rack 03", "bin_label": "07", "position": 1.0,
        "book_status": "ready", "book_note": "annotated",
        "revision_source": "isbndb", "revision_comment": "bulk import",
        "title": "Optionen und Futures", "authors": "Hull", "publisher": "dtv",
        "pages": 320.0, "height_cm": 19.5, "weight_kg": 0.4,
        "cover_ref": "https://images/x.jpg", "cover_source": "isbndb", "cover_status": "unreviewed",
        "tags": "finance, derivatives, finance",
    }
    p = map_row(row)

    assert p.book == {
        "isbn13": "9783423058087", "room": "Magazin", "space_label": "rack 03",
        "bin_label": "07", "position": 1.0, "book_status": "ready", "book_note": "annotated",
    }
    assert p.revision["source"] == "isbndb"
    assert p.revision["revision_comment"] == "bulk import"
    assert p.revision["title"] == "Optionen und Futures"
    # numeric coercion: pages -> int, dims/weight -> float
    assert p.revision["pages"] == 320 and isinstance(p.revision["pages"], int)
    assert p.revision["height_cm"] == 19.5 and isinstance(p.revision["height_cm"], float)
    assert p.revision["weight_kg"] == 0.4
    assert p.cover == {"cover_ref": "https://images/x.jpg", "cover_source": "isbndb", "cover_status": "unreviewed"}
    assert p.tags == ["finance", "derivatives"]   # order preserved, de-duplicated


def test_ambiguous_headers_route_to_the_right_table() -> None:
    row = {
        "book_status": "needs_data", "cover_status": "wrong",
        "revision_source": "manual", "cover_source": "own_photo",
    }
    p = map_row(row)
    assert p.book["book_status"] == "needs_data"
    assert p.cover["cover_status"] == "wrong"
    assert p.revision["source"] == "manual"
    assert p.cover["cover_source"] == "own_photo"
    # the names must NOT bleed across tables
    assert "cover_status" not in p.book
    assert "book_status" not in p.revision


def test_blank_cell_becomes_null() -> None:
    row = {"title": "   ", "authors": "", "pages": "", "isbn13": None}
    p = map_row(row)
    assert p.revision["title"] is None
    assert p.revision["authors"] is None
    assert p.revision["pages"] is None
    assert p.book["isbn13"] is None


def test_blank_header_columns_are_skipped() -> None:
    row = {"": "junk", "   ": "more junk", None: "x", "title": "Real"}
    p = map_row(row)
    assert p.revision == {"title": "Real"}
    assert p.book == {} and p.cover == {} and p.tags == []


def test_unrecognized_header_ignored_by_map_row() -> None:
    row = {"title": "Real", "mystery_col": "?"}
    p = map_row(row)
    assert p.revision == {"title": "Real"}
    assert "mystery_col" not in p.book
    assert "mystery_col" not in p.revision
    assert "mystery_col" not in p.cover


def test_photo_book_row_has_no_isbn_and_a_cover_ref() -> None:
    row = {
        "room": "Magazin", "space_label": "rack 01", "bin_label": "02",
        "cover_ref": "rack_01 2026-02-16 21.29.43.jpg", "cover_source": "own_photo",
        "title": "Provisional title from VLM", "revision_source": "photosearch",
    }
    p = map_row(row)
    assert "isbn13" not in p.book                  # absent, not even NULL
    assert p.cover["cover_ref"] == "rack_01 2026-02-16 21.29.43.jpg"
    assert p.cover["cover_source"] == "own_photo"
    assert p.revision["source"] == "photosearch"


def test_empty_row_yields_empty_buckets() -> None:
    p = map_row({})
    assert p.book == {} and p.revision == {} and p.cover == {} and p.tags == []


def test_split_tags_variants() -> None:
    assert split_tags("a, b ,c") == ["a", "b", "c"]
    assert split_tags("x, , x, y") == ["x", "y"]   # de-dup, drop empties
    assert split_tags("") == []
    assert split_tags(None) == []
    assert split_tags("   ") == []
    assert split_tags("solo") == ["solo"]


def test_unknown_headers_reports_nonblank_unrecognized_only() -> None:
    headers = ["isbn13", "title", "", "   ", "mystery", "tags",
               "another_mystery", "mystery", None]
    # blanks/None skipped; known (isbn13/title/tags) skipped; deduped; order kept
    assert unknown_headers(headers) == ["mystery", "another_mystery"]


def test_unknown_headers_empty_when_all_recognized() -> None:
    assert unknown_headers(["isbn13", "title", "cover_ref", "tags", ""]) == []
