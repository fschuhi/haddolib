"""
tests/test_ingest_isbndb.py — Tests for the ISBNdb-sheet → edition/revision ingest.

Built test-first, one behaviour at a time. The specimen rows are synthetic and
deliberately fake-looking, keyed by the same field names the ISBNdb sheet uses
(i.e. what `extract_record` produces, plus the sheet's `found` flag). They are
the executable spec for the ingest: each specimen exists to drive one assertion.

Behaviours, added incrementally:
  1. A normal ISBN13 row creates exactly one edition.            <-- this step
  2. (next) it also writes one rev0 isbndb revision snapshot.
  3. re-running the same row is an idempotent no-op.
  4. a not-found row (found == 0) is skipped entirely.
  5. a sparse row (PyXLL native types) stores NULLs, not "", for absent fields,
     and native floats land as the right stored types.            <-- this step
"""

from haddolib.ingest_isbndb import ingest_isbndb_row

# Fixed timestamps so tests are deterministic (we inject them; the function
# would otherwise use "now"). ISO-8601 UTC. FIXED_LATER is used to prove a
# re-import writes nothing at all — not even a new-timestamped revision.
FIXED_NOW = "2026-06-14T00:00:00+00:00"
FIXED_LATER = "2026-07-01T12:00:00+00:00"

# ── Specimen: a normal, fully-populated ISBNdb row ──────────────────────────
# Values are strings because that is what the sheet/extract_record yield.
SPECIMEN_NORMAL = {
    "isbn13":         "9781234567897",   # fake but length-13 (passes the CHECK)
    "found":          1,
    "title":          "Specimen One",
    "title_long":     "Specimen One: A Test Fixture",
    "authors":        "Ada Tester,Grace Fixture",
    "publisher":      "Synthetic Press",
    "date_published": "2020-09",
    "edition":        "1st",             # maps to DB column print_edition
    "pages":          "320",
    "binding":        "Hardcover",
    "language":       "en",
    "dimensions":     "Height: 20 cm, Width: 13 cm",
    "height_cm":      "20.0",
    "length_cm":      "",                # absent -> must become NULL later
    "width_cm":       "13.0",
    "weight_kg":      "0.5",
    "subjects":       "Testing,Fixtures",
    "cover_url":      "https://example.invalid/cover.jpg",
    "dewey_decimal":  "005.1",
    "isbn10":         "1234567897",
}

# ── Specimen: a failed ISBNdb lookup ────────────────────────────────────────
# Note it DOES carry the isbn13 that was looked up — the skip must hinge on
# found == 0, not on a missing ISBN, so a present ISBN here must still insert
# nothing.
SPECIMEN_NOT_FOUND = {
    "isbn13": "9789999999992",
    "found":  0,
    "title":  "",
}

# ── Specimen: a sparse found row, as PyXLL would deliver it ─────────────────
# Blanks arrive as None (not ""), and the two present numerics arrive as native
# floats — pages as 946.0 (Excel has no integer type) must store as int 946,
# weight as a true float. This mirrors the real sheet-via-PyXLL contract, not
# the seed CSV's strings.
SPECIMEN_SPARSE = {
    "isbn13":         "9780000000000",
    "found":          1,
    "title":          "Sparse Specimen",
    "title_long":     None,
    "authors":        None,
    "publisher":      None,
    "date_published": None,
    "edition":        None,
    "pages":          946.0,          # native float -> must store int 946
    "binding":        None,
    "language":       None,
    "dimensions":     None,
    "height_cm":      None,
    "length_cm":      None,
    "width_cm":       None,
    "weight_kg":      1.2927,         # native float -> stored as-is
    "subjects":       None,
    "cover_url":      None,
    "dewey_decimal":  None,
    "isbn10":         None,
}


# ── Behaviour 1: a normal row creates exactly one edition ───────────────────

def test_normal_row_creates_one_edition(db) -> None:
    result = ingest_isbndb_row(db, SPECIMEN_NORMAL, created_at=FIXED_NOW)

    # The result reports an edition was created...
    assert result.edition_created is True

    # ...and the database holds exactly one edition, with our ISBN.
    rows = db.execute("SELECT edition_id, isbn13 FROM edition").fetchall()
    assert len(rows) == 1
    assert rows[0]["isbn13"] == "9781234567897"

    # ...and the result's edition_id points at that row.
    assert result.edition_id == rows[0]["edition_id"]


# ── Behaviour 2: the same row writes exactly one rev0 isbndb revision ───────

def test_normal_row_writes_one_isbndb_revision(db) -> None:
    result = ingest_isbndb_row(db, SPECIMEN_NORMAL, created_at=FIXED_NOW)

    assert result.revision_created is True

    revs = db.execute("SELECT * FROM edition_revision").fetchall()
    assert len(revs) == 1
    r = revs[0]

    # provenance of the snapshot
    assert r["edition_id"] == result.edition_id
    assert r["source"] == "isbndb"
    assert r["created_at"] == FIXED_NOW

    # every bibliographic field mapped to its column
    assert r["title"] == "Specimen One"
    assert r["title_long"] == "Specimen One: A Test Fixture"
    assert r["subtitle"] is None                       # no ISBNdb source
    assert r["authors"] == "Ada Tester,Grace Fixture"
    assert r["publisher"] == "Synthetic Press"
    assert r["date_published"] == "2020-09"
    assert r["print_edition"] == "1st"                 # sheet "edition" -> print_edition
    assert r["pages"] == 320                           # coerced str -> int
    assert r["binding"] == "Hardcover"
    assert r["language"] == "en"
    assert r["dimensions"] == "Height: 20 cm, Width: 13 cm"
    assert r["height_cm"] == 20.0                      # coerced str -> float
    assert r["length_cm"] is None                      # "" -> NULL
    assert r["width_cm"] == 13.0
    assert r["weight_kg"] == 0.5
    assert r["subjects"] == "Testing,Fixtures"
    assert r["dewey_decimal"] == "005.1"
    assert r["isbn10"] == "1234567897"
    assert r["cover_url"] == "https://example.invalid/cover.jpg"


def test_pages_and_dimensions_have_numeric_types(db) -> None:
    # Guard the coercion explicitly: these must be stored as numbers, not text,
    # so the STRICT INTEGER/REAL columns accept them and queries can do maths.
    ingest_isbndb_row(db, SPECIMEN_NORMAL, created_at=FIXED_NOW)
    r = db.execute("SELECT pages, height_cm FROM edition_revision").fetchone()
    assert isinstance(r["pages"], int)
    assert isinstance(r["height_cm"], float)


# ── Behaviour 3: re-importing the same row is an idempotent no-op ────────────

def test_reimport_same_row_is_idempotent_noop(db) -> None:
    # First import creates the edition and its rev0.
    first = ingest_isbndb_row(db, SPECIMEN_NORMAL, created_at=FIXED_NOW)
    assert first.edition_created is True
    assert first.revision_created is True

    # Re-import the identical row with a DIFFERENT timestamp. A leaky no-op
    # would append a second, later-timestamped revision; a true no-op writes
    # nothing.
    second = ingest_isbndb_row(db, SPECIMEN_NORMAL, created_at=FIXED_LATER)
    assert second.edition_created is False
    assert second.revision_created is False
    assert second.edition_id == first.edition_id          # same edition reused

    # Still exactly one of each.
    assert db.execute("SELECT COUNT(*) AS n FROM edition").fetchone()["n"] == 1
    assert db.execute("SELECT COUNT(*) AS n FROM edition_revision").fetchone()["n"] == 1

    # The surviving revision is the FIRST one — original timestamp, untouched.
    surviving = db.execute("SELECT created_at FROM edition_revision").fetchone()
    assert surviving["created_at"] == FIXED_NOW


# ── Behaviour 4: a not-found row (found == 0) is skipped entirely ────────────

def test_not_found_row_is_skipped(db) -> None:
    result = ingest_isbndb_row(db, SPECIMEN_NOT_FOUND, created_at=FIXED_NOW)

    assert result.edition_created is False
    assert result.revision_created is False
    assert result.edition_id is None
    assert result.reason == "skipped: not found"

    # Nothing was inserted — not even an edition, despite the row carrying an ISBN.
    assert db.execute("SELECT COUNT(*) AS n FROM edition").fetchone()["n"] == 0
    assert db.execute("SELECT COUNT(*) AS n FROM edition_revision").fetchone()["n"] == 0


# ── Behaviour 5: a sparse PyXLL row stores NULLs and native numeric types ───

def test_sparse_row_stores_nulls_and_native_numbers(db) -> None:
    result = ingest_isbndb_row(db, SPECIMEN_SPARSE, created_at=FIXED_NOW)
    assert result.edition_created is True
    assert result.revision_created is True

    r = db.execute("SELECT * FROM edition_revision").fetchone()

    # The present fields are stored, with native floats coerced to the right types.
    assert r["title"] == "Sparse Specimen"
    assert r["pages"] == 946 and isinstance(r["pages"], int)          # 946.0 -> 946
    assert r["weight_kg"] == 1.2927 and isinstance(r["weight_kg"], float)

    # Every absent field is NULL (None) — never the empty string.
    for col in (
        "title_long", "subtitle", "authors", "publisher", "date_published",
        "print_edition", "binding", "language", "dimensions",
        "height_cm", "length_cm", "width_cm", "subjects",
        "dewey_decimal", "isbn10", "cover_url",
    ):
        assert r[col] is None, f"{col} should be NULL, got {r[col]!r}"
