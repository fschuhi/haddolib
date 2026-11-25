"""
tests/test_roster_import.py — The insert path (insert_book_row), on proto_db.

Synthetic rows built through map_row (so the mapping and the insert are exercised
together, the way the driver will use them). These tests ARE the spec for what
one new book write does. Dedup / decline / batch summary belong to the driver's
test module.
"""

from haddolib.roster import map_row
from haddolib.roster_import import insert_book_row

TS = "2026-06-15T12:00:00+00:00"          # one fixed timestamp for the run


def _one(proto_db, sql, params=()):
    return proto_db.execute(sql, params).fetchone()


def test_full_isbn_book_writes_book_revision_cover_tags(proto_db) -> None:
    row = {
        "isbn13": "9783423058087",
        "room": "Magazin", "space_label": "rack 03", "bin_label": "07", "position": 1.0,
        "book_status": "ready", "book_note": "annotated",
        "revision_source": "isbndb",
        "title": "Optionen und Futures", "authors": "Hull", "publisher": "dtv",
        "edition": "8.", "pages": 320.0, "height_cm": 19.5,
        "cover_ref": "https://images/x.jpg", "cover_source": "isbndb",
        "tags": "finance, derivatives",
    }
    book_id = insert_book_row(proto_db, map_row(row), TS)

    view = _one(proto_db, "SELECT * FROM book_current WHERE book_id = ?", (book_id,))
    assert view["isbn13"] == "9783423058087"
    assert view["title"] == "Optionen und Futures"
    assert view["edition"] == "8."
    assert view["pages"] == 320
    assert view["book_status"] == "ready" and view["book_note"] == "annotated"
    assert view["room"] == "Magazin" and view["bin_label"] == "07"
    assert view["cover_ref"] == "https://images/x.jpg"        # preferred cover resolved
    assert view["cover_source"] == "isbndb"
    assert view["cover_status"] == "unreviewed"               # schema default applied

    tags = {r["name"] for r in proto_db.execute(
        "SELECT t.name FROM tag t JOIN book_tag bt ON bt.tag_id = t.tag_id "
        "WHERE bt.book_id = ?", (book_id,))}
    assert tags == {"finance", "derivatives"}


def test_preferred_cover_id_points_at_the_inserted_cover(proto_db) -> None:
    row = {"isbn13": "9781234567897", "cover_ref": "https://c/1.jpg", "cover_source": "isbndb",
           "revision_source": "isbndb", "title": "X"}
    book_id = insert_book_row(proto_db, map_row(row), TS)
    book = _one(proto_db, "SELECT preferred_cover_id FROM book WHERE book_id = ?", (book_id,))
    cover = _one(proto_db, "SELECT cover_id FROM cover WHERE book_id = ?", (book_id,))
    assert book["preferred_cover_id"] == cover["cover_id"]


def test_photo_book_has_null_isbn_and_own_photo_cover(proto_db) -> None:
    row = {
        "room": "Magazin", "space_label": "rack 01", "bin_label": "02",
        "cover_ref": "rack_01 2026-02-16 21.29.43.jpg", "cover_source": "own_photo",
        "revision_source": "photosearch", "title": "Provisional from VLM",
        "book_status": "needs_data",
    }
    book_id = insert_book_row(proto_db, map_row(row), TS)
    view = _one(proto_db, "SELECT * FROM book_current WHERE book_id = ?", (book_id,))
    assert view["isbn13"] is None
    assert view["title"] == "Provisional from VLM"
    assert view["cover_ref"] == "rack_01 2026-02-16 21.29.43.jpg"
    assert view["cover_source"] == "own_photo"
    assert view["book_status"] == "needs_data"


def test_not_found_isbn_book_is_bare_no_revision_no_cover(proto_db) -> None:
    # isbn13 + location present; every bib field blank; no cover ref.
    row = {
        "isbn13": "9789999999990",
        "room": "Magazin", "space_label": "rack 09", "bin_label": "11",
        "book_status": "needs_data",
        "revision_source": "isbndb",          # a bare source, no real bib
        "title": "", "authors": "", "cover_ref": "",
    }
    book_id = insert_book_row(proto_db, map_row(row), TS)

    # book exists, with identity + location...
    view = _one(proto_db, "SELECT * FROM book_current WHERE book_id = ?", (book_id,))
    assert view["isbn13"] == "9789999999990"
    assert view["book_status"] == "needs_data"
    # ...but it is bare: no revision, no cover (LEFT JOIN shows NULLs).
    assert view["title"] is None
    assert view["revision_source"] is None
    assert view["cover_ref"] is None
    assert _one(proto_db, "SELECT COUNT(*) n FROM book_revision WHERE book_id = ?", (book_id,))["n"] == 0
    assert _one(proto_db, "SELECT COUNT(*) n FROM cover WHERE book_id = ?", (book_id,))["n"] == 0


def test_tags_are_case_insensitive_within_and_across_rows(proto_db) -> None:
    # within a row: 'Fiction' and 'fiction' collapse to one tag + one link
    b1 = insert_book_row(proto_db, map_row(
        {"isbn13": "9781111111113", "revision_source": "isbndb", "title": "A",
         "tags": "Fiction, fiction, SciFi"}), TS)
    links1 = proto_db.execute(
        "SELECT COUNT(*) n FROM book_tag WHERE book_id = ?", (b1,)).fetchone()["n"]
    assert links1 == 2                                  # Fiction + SciFi, not 3

    # across rows: 'FICTION' reuses the existing tag, no new tag row
    b2 = insert_book_row(proto_db, map_row(
        {"isbn13": "9782222222226", "revision_source": "isbndb", "title": "B",
         "tags": "FICTION"}), TS)
    total_tags = proto_db.execute("SELECT COUNT(*) n FROM tag").fetchone()["n"]
    assert total_tags == 2                              # Fiction, SciFi — FICTION reused

    # the stored spelling is the first one seen
    fiction = _one(proto_db, "SELECT name FROM tag WHERE name = 'fiction' COLLATE NOCASE")
    assert fiction["name"] == "Fiction"


def test_bibliographic_data_without_source_raises(proto_db) -> None:
    # title present (real bib) but no revision_source -> loud failure
    import pytest
    row = {"isbn13": "9783333333339", "title": "Has title, no source"}
    with pytest.raises(ValueError, match="revision_source"):
        insert_book_row(proto_db, map_row(row), TS)


def test_cover_status_respects_supplied_value(proto_db) -> None:
    row = {"isbn13": "9784444444442", "revision_source": "isbndb", "title": "C",
           "cover_ref": "https://c/2.jpg", "cover_status": "beautiful"}
    book_id = insert_book_row(proto_db, map_row(row), TS)
    view = _one(proto_db, "SELECT cover_status FROM book_current WHERE book_id = ?", (book_id,))
    assert view["cover_status"] == "beautiful"


# ---------------------------------------------------------------------------
# The batch driver (import_roster) — dedup, decline reasons, error isolation.
# ---------------------------------------------------------------------------

from haddolib.roster_import import ImportSummary, import_roster   # noqa: E402

# A header order on purpose NOT matching schema/field order, to prove order is free.
HEADERS = ["tags", "isbn13", "title", "revision_source", "cover_ref", "cover_source",
           "room", "space_label", "bin_label"]


def _row(isbn13="", title="", source="", ref="", cover_source="",
         room="Magazin", space="rack 01", binl="01", tags=""):
    # built in HEADERS order
    return [tags, isbn13, title, source, ref, cover_source, room, space, binl]


def _count(proto_db, table):
    return proto_db.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()["n"]


def test_fresh_batch_all_inserted(proto_db) -> None:
    rows = [
        _row(isbn13="9783423058087", title="A", source="isbndb", ref="https://c/a.jpg",
             cover_source="isbndb", tags="finance"),
        _row(isbn13="9781234567897", title="B", source="isbndb"),
    ]
    s = import_roster(proto_db, HEADERS, rows, TS)
    assert (s.inserted, s.declined, len(s.errors)) == (2, 0, 0)
    assert s.total == 2
    assert _count(proto_db, "book") == 2


def test_duplicate_isbn13_within_batch_declined(proto_db) -> None:
    rows = [
        _row(isbn13="9783423058087", title="first", source="isbndb"),
        _row(isbn13="9783423058087", title="again", source="isbndb", tags="x"),
    ]
    s = import_roster(proto_db, HEADERS, rows, TS)
    assert s.inserted == 1 and s.duplicate_isbn13 == 1
    assert _count(proto_db, "book") == 1


def test_duplicate_isbn13_against_existing_db_row(proto_db) -> None:
    insert_book_row(proto_db, map_row({"isbn13": "9783423058087",
                                       "revision_source": "isbndb", "title": "pre"}), TS)
    proto_db.commit()
    s = import_roster(proto_db, HEADERS,
                      [_row(isbn13="9783423058087", title="dup", source="isbndb")], TS)
    assert s.inserted == 0 and s.duplicate_isbn13 == 1
    assert _count(proto_db, "book") == 1


def test_photo_ref_duplicate_declined(proto_db) -> None:
    photo = "rack_01 2026-02-16 21.29.43.jpg"
    rows = [
        _row(title="photo one", source="photosearch", ref=photo, cover_source="own_photo"),
        _row(title="photo dup", source="photosearch", ref=photo, cover_source="own_photo"),
    ]
    s = import_roster(proto_db, HEADERS, rows, TS)
    assert s.inserted == 1 and s.duplicate_photo == 1
    assert _count(proto_db, "book") == 1


def test_shared_placeholder_url_does_NOT_decline_isbn_books(proto_db) -> None:
    # THE catch: two different ISBN books sharing one API 'missing cover' URL.
    placeholder = "https://isbndb/placeholder-missing.png"
    rows = [
        _row(isbn13="9783423058087", title="X", source="isbndb",
             ref=placeholder, cover_source="isbndb"),
        _row(isbn13="9781234567897", title="Y", source="isbndb",
             ref=placeholder, cover_source="isbndb"),
    ]
    s = import_roster(proto_db, HEADERS, rows, TS)
    assert s.inserted == 2 and s.duplicate_photo == 0       # NOT treated as dup
    assert _count(proto_db, "book") == 2
    assert _count(proto_db, "cover") == 2                   # both covers kept


def test_no_identity_key_row_declined(proto_db) -> None:
    rows = [_row(title="orphan", source="isbndb")]          # no isbn13, no ref
    s = import_roster(proto_db, HEADERS, rows, TS)
    assert s.inserted == 0 and s.no_key == 1
    assert _count(proto_db, "book") == 0


def test_bad_row_is_isolated_not_fatal(proto_db) -> None:
    # middle row errors AT INSERT for a non-ISBN reason: it carries real
    # bibliographic data (a title) but no revision_source, so insert_book_row
    # raises ValueError. The driver rolls it back and records it as an error;
    # neighbours survive. (A malformed isbn13 no longer reaches the insert — it is
    # now an invalid_isbn13 decline; see test_invalid_isbn13_checksum_declined.)
    rows = [
        _row(isbn13="9783423058087", title="good 1", source="isbndb"),
        _row(isbn13="9780306406157", title="bad: bib data, no source", source=""),
        _row(isbn13="9781234567897", title="good 2", source="isbndb"),
    ]
    s = import_roster(proto_db, HEADERS, rows, TS)
    assert s.inserted == 2
    assert len(s.errors) == 1
    assert s.errors[0][0] == 2                              # 1-based data row index
    assert _count(proto_db, "book") == 2                    # the bad row left nothing behind


def test_invalid_isbn13_checksum_declined(proto_db) -> None:
    # 13 digits, 978-prefixed, but a WRONG check digit (the valid form ends 087).
    # The schema's length-only CHECK would let this through; the driver's
    # is_valid_isbn13 guard catches it FIRST and declines it as invalid_isbn13 —
    # before dedup, and without ever reaching the insert.
    rows = [_row(isbn13="9783423058088", title="bad checksum", source="isbndb")]
    s = import_roster(proto_db, HEADERS, rows, TS)
    assert s.invalid_isbn13 == 1
    assert s.inserted == 0
    assert len(s.errors) == 0                               # a clean decline, not an error
    assert _count(proto_db, "book") == 0                    # nothing written


def test_non_numeric_string_in_numeric_column_declined(proto_db) -> None:
    # A numeric column (height_cm) holding a STRING is declined as non_numeric_value
    # — even a string that WOULD parse ("21.59"). A genuine Excel number reaches us
    # as a float and inserts; a blank cell is fine (it becomes NULL, never a reject —
    # empty dimension cells are the common case in real data). The check runs on the
    # RAW row before map_row, so the German-comma "21,59" — which as_real would crash
    # on, OUTSIDE the per-row try/except — is turned into a clean, fixable reject
    # instead of aborting the whole run.
    headers = ["isbn13", "title", "revision_source", "height_cm"]
    rows = [
        ["9783423058087", "native number", "isbndb", 21.59],    # float            -> inserted
        ["9781234567897", "empty cell",     "isbndb", ""],      # blank            -> inserted (NULL)
        ["9780306406157", "german text",    "isbndb", "21,59"], # str (crashes coercion) -> reject
        ["9784444444442", "dotted text",    "isbndb", "21.59"], # str (would parse)      -> reject
    ]
    s = import_roster(proto_db, headers, rows, TS)

    assert s.inserted == 2
    assert s.non_numeric_value == 2
    assert s.declined == 2
    assert len(s.errors) == 0                  # a clean decline, NOT a crash mid-run
    assert _count(proto_db, "book") == 2

    # both rejects carry the stable code AND a detail naming the offending cell.
    by_isbn = {vals[0]: (reason, detail) for reason, detail, vals in s.rejected_rows}
    assert by_isbn["9780306406157"] == ("non_numeric_value", "height_cm = '21,59' is not a number")
    assert by_isbn["9784444444442"] == ("non_numeric_value", "height_cm = '21.59' is not a number")


def test_unknown_headers_reported_in_summary(proto_db) -> None:
    headers = HEADERS + ["mystery", "another"]
    rows = [_row(isbn13="9783423058087", title="A", source="isbndb") + ["?", "?"]]
    s = import_roster(proto_db, headers, rows, TS)
    assert s.inserted == 1
    assert s.unknown_headers == ["mystery", "another"]


def test_summary_line_and_derived_fields() -> None:
    s = ImportSummary(inserted=10, duplicate_isbn13=2, duplicate_photo=1, no_key=1,
                      errors=[(5, "boom")], unknown_headers=["mystery"])
    assert s.declined == 4
    assert s.total == 15
    line = s.summary_line()
    assert "10 inserted" in line and "4 declined" in line
    assert "1 error(s)" in line and "ignored columns: mystery" in line


# ---------------------------------------------------------------------------
# rejected_rows — the durable capture the bridge turns into the rejected file.
# ---------------------------------------------------------------------------

def test_rejected_rows_capture_reason_detail_and_verbatim_values(proto_db) -> None:
    # One row per non-insert outcome (plus two clean inserts), so each reason
    # appears exactly once and we can key by it.
    photo = "rack_01 2026-02-16 21.29.43.jpg"
    invalid_row = _row(isbn13="9783423058088", title="bad cksum", source="isbndb")
    rows = [
        _row(isbn13="9783423058087", title="ok", source="isbndb"),           # inserted
        invalid_row,                                                          # invalid_isbn13
        _row(isbn13="9783423058087", title="dup", source="isbndb"),          # duplicate_isbn13
        _row(title="photo", source="photosearch", ref=photo, cover_source="own_photo"),      # inserted
        _row(title="photo dup", source="photosearch", ref=photo, cover_source="own_photo"),  # duplicate_photo
        _row(title="orphan", source="isbndb"),                               # no_key (no isbn13, no ref)
        _row(isbn13="9780306406157", title="bib, no source", source=""),     # error (ValueError at insert)
    ]
    s = import_roster(proto_db, HEADERS, rows, TS)

    # the four clean declines carry their stable token; their detail is "" (these
    # are identity checks — the code alone says enough).
    by_reason = {reason: (detail, values) for reason, detail, values in s.rejected_rows}
    for token in ("invalid_isbn13", "duplicate_isbn13", "duplicate_photo", "no_key"):
        assert token in by_reason
        assert by_reason[token][0] == ""                 # blank detail for identity checks

    # ...values are stored VERBATIM, in sheet order (a "" stays "", uncoerced).
    assert by_reason["invalid_isbn13"][1] == tuple(invalid_row)

    # the errored row's reason is the exception MESSAGE (actionable at the bench),
    # not a bare token — its detail is blank, and it is NOT one of the decline tokens.
    decline_tokens = {"invalid_isbn13", "duplicate_isbn13", "duplicate_photo", "no_key"}
    error_entries = [(reason, detail, vals) for reason, detail, vals in s.rejected_rows
                     if reason not in decline_tokens]
    assert len(error_entries) == 1
    err_reason, err_detail, err_vals = error_entries[0]
    assert "revision_source" in err_reason               # the real, fixable cause
    assert err_detail == ""                              # errors leave column B blank
    assert err_vals == tuple(_row(isbn13="9780306406157", title="bib, no source", source=""))


def test_rejected_rows_invariant_equals_declined_plus_errors(proto_db) -> None:
    # The capture must account for exactly the non-inserts: declines (clean) plus
    # errors (raised). Inserts never appear.
    photo = "rack_01 2026-02-16 21.29.43.jpg"
    rows = [
        _row(isbn13="9783423058087", title="ok", source="isbndb"),           # inserted
        _row(isbn13="9783423058088", title="bad cksum", source="isbndb"),    # invalid_isbn13
        _row(title="orphan", source="isbndb"),                               # no_key
        _row(title="p", source="photosearch", ref=photo, cover_source="own_photo"),   # inserted
        _row(title="p dup", source="photosearch", ref=photo, cover_source="own_photo"),  # duplicate_photo
        _row(isbn13="9780306406157", title="bib, no source", source=""),     # error
    ]
    s = import_roster(proto_db, HEADERS, rows, TS)
    assert len(s.rejected_rows) == s.declined + len(s.errors)
    assert s.inserted == 2                                # sanity: inserts excluded


# ---------------------------------------------------------------------------
# status_blank — the LATE required-field check. book_status is required WHEN
# the column is present (semantics A); a missing column is a separate, header-
# level concern (see TODO.md). Placed after the identity decision, so identity
# reasons win and a blanked row never claims a dedup key.
# ---------------------------------------------------------------------------

def test_status_blank_declined(proto_db) -> None:
    # Column present: a filled cell inserts; a blank ("") or whitespace-only cell
    # is a hard reject (as_text folds both to None). Each reject carries the
    # stable token AND the field-level detail naming the column.
    headers = ["isbn13", "title", "revision_source", "book_status"]
    rows = [
        ["9783423058087", "filled",     "isbndb", "ready"],   # present    -> inserted
        ["9781234567897", "blank",      "isbndb", ""],        # blank      -> reject
        ["9780306406157", "whitespace", "isbndb", "   "],     # whitespace -> reject
    ]
    s = import_roster(proto_db, headers, rows, TS)

    assert s.inserted == 1
    assert s.status_blank == 2
    assert s.declined == 2
    assert len(s.errors) == 0
    assert _count(proto_db, "book") == 1
    assert len(s.rejected_rows) == s.declined + len(s.errors)   # invariant holds

    by_isbn = {vals[0]: (reason, detail) for reason, detail, vals in s.rejected_rows}
    detail = "book_status is required and was left blank"
    assert by_isbn["9781234567897"] == ("status_blank", detail)
    assert by_isbn["9780306406157"] == ("status_blank", detail)


def test_status_blank_loses_to_identity_reason(proto_db) -> None:
    # The LATE slot is the point: a row that is blank-on-status AND fails an
    # identity check reports the IDENTITY reason, because that decision runs
    # first. Three such rows, each also status-blank, each reporting its own
    # token — never status_blank.
    headers = ["isbn13", "title", "revision_source", "cover_ref", "cover_source",
               "book_status"]
    rows = [
        ["9783423058087", "seed", "isbndb", "", "", "ready"],  # has status -> inserts, seeds key
        ["9783423058087", "dup",  "isbndb", "", "", ""],       # dup isbn13 + blank -> duplicate_isbn13
        ["9783423058088", "bad",  "isbndb", "", "", ""],       # bad checksum + blank -> invalid_isbn13
        ["",              "orph", "isbndb", "", "", ""],        # no key + blank -> no_key
    ]
    s = import_roster(proto_db, headers, rows, TS)

    assert s.inserted == 1
    assert s.status_blank == 0                  # never reached for these rows
    assert s.duplicate_isbn13 == 1
    assert s.invalid_isbn13 == 1
    assert s.no_key == 1

    reasons = {reason for reason, _detail, _vals in s.rejected_rows}
    assert reasons == {"duplicate_isbn13", "invalid_isbn13", "no_key"}


def test_status_blank_ignored_when_column_absent(proto_db) -> None:
    # Semantics A: when the sheet omits book_status entirely, the gate is silent —
    # every row passes it. (A missing column is the header-level concern parked in
    # TODO.md.) The module HEADERS carry no book_status, so a clean batch inserts
    # with zero status_blank.
    rows = [
        _row(isbn13="9783423058087", title="a", source="isbndb"),
        _row(isbn13="9781234567897", title="b", source="isbndb"),
    ]
    s = import_roster(proto_db, HEADERS, rows, TS)
    assert s.inserted == 2
    assert s.status_blank == 0
    assert _count(proto_db, "book") == 2


def test_status_blank_row_does_not_claim_the_dedup_key(proto_db) -> None:
    # Late rejection happens BEFORE the key joins the in-batch dedup set, so a
    # blanked row must not shadow a LATER valid row with the same isbn13: the
    # second row still inserts — it is not seen as a duplicate of the rejected one.
    headers = ["isbn13", "title", "revision_source", "book_status"]
    rows = [
        ["9783423058087", "first, blank status", "isbndb", ""],      # rejected: status_blank
        ["9783423058087", "second, has status",  "isbndb", "ready"], # inserts: key was never claimed
    ]
    s = import_roster(proto_db, headers, rows, TS)
    assert s.status_blank == 1
    assert s.inserted == 1
    assert s.duplicate_isbn13 == 0          # the rejected row did NOT seed the key
    assert _count(proto_db, "book") == 1


# ---------------------------------------------------------------------------
# incomplete_location — the second LATE check. A PARTIAL location hierarchy
# (child without parent) rejects; a full or a fully-absent location passes.
# Reads mapped values, so a blank parent and an absent parent column are alike.
# ---------------------------------------------------------------------------

def test_incomplete_location_declined(proto_db) -> None:
    headers = ["isbn13", "title", "revision_source", "room", "space_label", "bin_label"]
    rows = [
        ["9783423058087", "full",          "isbndb", "Magazin", "rack 03", "07"],  # full     -> inserted
        ["9781234567897", "bin no space",  "isbndb", "Magazin", "",        "07"],  # bin/space -> reject
        ["9780306406157", "space no room", "isbndb", "",        "rack 03", ""],    # space/room-> reject
    ]
    s = import_roster(proto_db, headers, rows, TS)

    assert s.inserted == 1
    assert s.incomplete_location == 2
    assert s.declined == 2
    assert _count(proto_db, "book") == 1
    assert len(s.rejected_rows) == s.declined + len(s.errors)   # invariant holds

    by_isbn = {vals[0]: (reason, detail) for reason, detail, vals in s.rejected_rows}
    assert by_isbn["9781234567897"] == (
        "incomplete_location", "bin_label = '07' present but space_label is blank")
    assert by_isbn["9780306406157"] == (
        "incomplete_location", "space_label = 'rack 03' present but room is blank")


def test_blank_or_absent_location_passes(proto_db) -> None:
    # Two ways to have "no location": every location cell blank, or the columns
    # absent entirely. Both map to None — not a partial hierarchy — so the
    # "elsewhere in the house" book inserts untouched in either case.
    headers_blank = ["isbn13", "title", "revision_source",
                     "room", "space_label", "bin_label"]
    s1 = import_roster(proto_db, headers_blank,
                       [["9783423058087", "all blank", "isbndb", "", "", ""]], TS)
    assert s1.inserted == 1 and s1.incomplete_location == 0

    headers_absent = ["isbn13", "title", "revision_source"]
    s2 = import_roster(proto_db, headers_absent,
                       [["9781234567897", "no loc cols", "isbndb"]], TS)
    assert s2.inserted == 1 and s2.incomplete_location == 0


def test_incomplete_location_loses_to_identity_reason(proto_db) -> None:
    # Late slot again: a row that is partial-on-location AND a duplicate reports
    # the IDENTITY reason — the location check is never reached.
    headers = ["isbn13", "title", "revision_source", "room", "space_label", "bin_label"]
    rows = [
        ["9783423058087", "seed", "isbndb", "Magazin", "rack 03", "07"],  # full -> inserts, seeds key
        ["9783423058087", "dup",  "isbndb", "Magazin", "",        "07"],  # dup + partial -> duplicate_isbn13
    ]
    s = import_roster(proto_db, headers, rows, TS)

    assert s.inserted == 1
    assert s.duplicate_isbn13 == 1
    assert s.incomplete_location == 0                       # never reached
    assert {reason for reason, _d, _v in s.rejected_rows} == {"duplicate_isbn13"}
