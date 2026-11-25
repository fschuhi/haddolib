-- ============================================================================
--  haddolib -- the database schema
-- ----------------------------------------------------------------------------
--  book ──< book_revision     append-only FULL bibliographic snapshots
--    │
--    ├──> cover (preferred)    book.preferred_cover_id points at ONE cover row
--    │
--    ├──< cover                zero-to-many cover images (rows, not slots)
--    │
--    └──< book_tag >── tag     personal tags, many-to-many
--
--  Grain: ONE row in `book` = one physical book in the Magazin.
--  Location lives inline on `book` as mutable attributes -- safe, because the
--  identity anchor is the surrogate book_id, not the location.
--
--  SQLite notes (idioms that differ from other DBs):
--    - STRICT tables enforce column types (SQLite >= 3.37, 2021). If any tool
--      ever chokes, delete the word STRICT and the table still works.
--    - No DATE/BOOLEAN type -- dates are ISO-8601 TEXT, booleans INTEGER 0/1.
--    - "INTEGER PRIMARY KEY" auto-assigns ids on INSERT (aliases rowid).
--    - A UNIQUE column treats NULLs as all-distinct, so isbn13 can be UNIQUE
--      *and* hold many NULL rows (every photo / pre-ISBN book).
--    - Foreign keys are OFF by default and must be re-enabled per connection:
--      PRAGMA foreign_keys = ON;  (see foot of file).
-- ============================================================================


-- ── book : the physical book, its identity, location, and workflow status ───
-- The surrogate book_id is the MERGE ANCHOR: it survives import, correction,
-- and (later) relocation. A ||PH|| placeholder graduates into a resolved book
-- by UPDATE on THIS row + a new revision -- the id, location, and cover stay put.
--
-- NOTE on the forward reference: preferred_cover_id references `cover`, which is
-- defined further down. SQLite permits this circular reference; at runtime you
-- insert a book (preferred_cover_id NULL), insert its covers, then UPDATE the
-- pointer. ON DELETE SET NULL keeps it from dangling if a cover row is removed.
CREATE TABLE book (
    book_id            INTEGER PRIMARY KEY,        -- surrogate identity / merge anchor
    isbn13             TEXT UNIQUE,                -- business key; NULL for photo / pre-ISBN books
                                                   -- UNIQUE guards against accidental double-adds
    book_note          TEXT,                       -- free fact: "annotated", "Cover fehlt" -- edited in place, spawns no row
    book_status        TEXT,                       -- OPEN-TEXT non-cover workflow indicator (the "pile shrinking" field)

    -- location, fused inline (no movement history) ----------------------------
    room               TEXT,                       -- 'Magazin', 'Wohnzimmer', ...
    space_label        TEXT,                       -- 'rack 03', 'cupboard A'
    bin_label          TEXT,                       -- box '01'..'25'; NULL where the space has no bins
    position           REAL,                       -- sortable order within the bin; REAL so 1.5 slots between 1 and 2

    preferred_cover_id INTEGER REFERENCES cover(cover_id) ON DELETE SET NULL,  -- which cover the views show
    created_at         TEXT NOT NULL,
    CHECK (isbn13 IS NULL OR length(isbn13) = 13)
) STRICT;

CREATE INDEX ix_book_isbn13 ON book(isbn13);


-- ── book_revision : append-only FULL bibliographic snapshots (words only) ───
-- Each row is a COMPLETE picture of the metadata at one point in time. An API
-- result lands as one revision unchanged; a manual correction lands as the next
-- revision (newest wins). NO cover field -- covers live in `cover`. Reads go
-- through book_current, never this table.
CREATE TABLE book_revision (
    revision_id        INTEGER PRIMARY KEY,
    book_id            INTEGER NOT NULL REFERENCES book(book_id),

    source             TEXT NOT NULL,              -- OPEN TEXT: 'isbndb','openlibrary','photosearch','manual', ...
    revision_comment   TEXT,                       -- optional: why this revision exists
    created_at         TEXT NOT NULL,

    -- bibliographic snapshot (mirrors the ISBNdb / photosearch sheet fields) --
    title              TEXT,
    title_long         TEXT,
    subtitle           TEXT,
    authors            TEXT,                       -- comma-delimited, as the API gives
    publisher          TEXT,
    date_published     TEXT,                       -- mixed forms from the API ('2020-09', '2025')
    edition            TEXT,                       -- ISBNdb's "edition" field
    pages              INTEGER,
    binding            TEXT,
    language           TEXT,
    dimensions         TEXT,                       -- raw dimensions string
    height_cm          REAL,
    length_cm          REAL,
    width_cm           REAL,
    weight_kg          REAL,
    subjects           TEXT,                       -- ISBNdb subjects (NB: not your personal tags)
    dewey_decimal      TEXT,
    isbn10             TEXT                        -- retained for the legacy bridge / reference
) STRICT;

CREATE INDEX ix_revision_book ON book_revision(book_id, created_at);


-- ── cover : cover images -- one row per image, references not bytes ──────────
-- Owner is a single book_id. `cover_ref`
-- holds the URL or a file path; the filename/where-to-find-it resolution is
-- pushed to Excel/PyXLL, not stored here. `cover_source` and `cover_status` are
-- OPEN TEXT so the cover workflow can evolve. A book may have zero covers;
-- cover_source may be unset.
CREATE TABLE cover (
    cover_id           INTEGER PRIMARY KEY,
    book_id            INTEGER NOT NULL REFERENCES book(book_id),
    cover_ref          TEXT NOT NULL,              -- the URL, or a directly-supplied file path
    cover_source       TEXT,                       -- OPEN TEXT: 'isbndb','amazon','thalia','own_photo', ... (optional)
    cover_status       TEXT DEFAULT 'unreviewed',  -- OPEN TEXT cover workflow; default is just the import entry state
    created_at         TEXT NOT NULL
) STRICT;

CREATE INDEX ix_cover_book ON cover(book_id);


-- ── tag + book_tag : personal tags, many-to-many ───────────────────────────
-- The master tag list (your "Tags" sheet) lives in `tag`; books carry tags via
-- the junction. This is the ONE genuine relational exception we keep -- "books
-- by tag, sorted by location" is on the wanted list and tags are many-to-many.
CREATE TABLE tag (
    tag_id   INTEGER PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE book_tag (
    book_id  INTEGER NOT NULL REFERENCES book(book_id),
    tag_id   INTEGER NOT NULL REFERENCES tag(tag_id),
    PRIMARY KEY (book_id, tag_id)
) STRICT, WITHOUT ROWID;          -- pure junction; WITHOUT ROWID is the tidy idiom


-- ============================================================================
--  VIEW -- the read layer. Everything (shelf/list views, PyXLL) reads here,
--  never the append-only base tables directly.
-- ============================================================================

-- book_current : newest revision per book + identity + inline location +
-- preferred cover ref. The shelf/list views and PyXLL read HERE.
--
-- LEFT JOIN to the revision subquery: a freshly-scanned or
-- not-found book has NO revision yet, and the view that is meant to show *all*
-- the books must still show it -- with NULL bibliographic fields. The
-- ROW_NUMBER() rn = 1 predicate lives in the ON clause so a book with zero
-- revisions yields one row with NULLs rather than being filtered out.
-- A coverless book likewise yields NULL cover_ref (no fabricated placeholder).
CREATE VIEW book_current AS
SELECT b.book_id,
       b.isbn13,
       r.source             AS revision_source,
       r.revision_comment,
       r.created_at         AS revised_at,
       r.title, r.title_long, r.subtitle, r.authors, r.publisher,
       r.date_published, r.edition, r.pages, r.binding, r.language,
       r.dimensions, r.height_cm, r.length_cm, r.width_cm, r.weight_kg,
       r.subjects, r.dewey_decimal, r.isbn10,
       b.book_note, b.book_status,
       b.room, b.space_label, b.bin_label, b.position,
       cov.cover_ref,
       cov.cover_source,
       cov.cover_status
FROM book AS b
LEFT JOIN (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY book_id
               ORDER BY created_at DESC, revision_id DESC
           ) AS rn
    FROM book_revision
) AS r ON r.book_id = b.book_id AND r.rn = 1
LEFT JOIN cover AS cov ON cov.cover_id = b.preferred_cover_id;


-- ============================================================================
--  Reminder for whoever connects (script, PyXLL, sqlite3 CLI):
--      PRAGMA foreign_keys = ON;        -- per connection; OFF by default
-- ============================================================================
