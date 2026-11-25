-- ============================================================================
--  haddolib — SQLite schema (DRAFT for review)
-- ============================================================================
--  Reflects the data model settled in the design session:
--
--    edition  (identity)  ──<  edition_revision   append-only full snapshots
--       │
--       └──<  copy  (physical book)  ──<  location_event   append-only movement log
--                │                              │
--                │                              └──>  space  (rack / cupboard / table …)
--                │
--                ├──<  copy_tag  >──  tag        personal tags (rib)
--                └──<  cover                     own-photo covers (rib)
--       │
--       └──<  cover                              API / edition-level covers (rib)
--
--  Grains (the three identities we separated out):
--    • edition        = a bibliographic record ("which book", FRBR manifestation).
--                       Keyed internally by surrogate edition_id; isbn13 is the
--                       human business key, NULL for photo / pre-1970 books.
--    • copy           = one physical object you own. The movement-log anchor.
--                       Usually 1:1 with edition; the lone exception in your
--                       library (Optionen und Futures, 9783423058087) is two
--                       copy rows under one edition.
--    • location_event = where a copy sits, over time. Append-only. Current
--                       location = the row with valid_to IS NULL.
--
--  Versioning: edition_revision is an append-only chain of FULL snapshots.
--    The newest revision per edition IS the current state (no patch-layering,
--    so a blank field unambiguously means "empty", not "unchanged").
--    Read current state through the edition_current view, never the raw table.
-- ----------------------------------------------------------------------------
--  SQLite notes for review (idioms that differ from other DBs):
--    • STRICT tables (last line of each CREATE) enforce column types instead of
--      SQLite's usual loose affinity. Requires SQLite ≥ 3.37 (2021). Python 3.14
--      bundles a far newer build, so you're fine — but if any tool ever chokes,
--      delete the word STRICT and the table still works (just less type-safe).
--    • SQLite has no DATE or BOOLEAN type. Dates are ISO-8601 TEXT
--      ('2026-06-10T22:14:00'); booleans are INTEGER 0/1. Hence the CHECKs.
--    • "INTEGER PRIMARY KEY" auto-assigns ids on INSERT (it aliases the internal
--      rowid). You do NOT want the AUTOINCREMENT keyword — it only adds overhead
--      and a stricter monotonicity guarantee you don't need.
--    • A UNIQUE column treats NULLs as all-distinct, so isbn13 can be UNIQUE
--      *and* hold many NULL rows (every photo/pre-ISBN edition). This is the
--      behaviour we want and rely on.
--    • Foreign keys are OFF by default in SQLite and must be re-enabled on every
--      connection: run  PRAGMA foreign_keys = ON;  (see bottom of file). Forget
--      it and the REFERENCES below are silently not enforced.
-- ============================================================================


-- ── edition : bibliographic identity (thin anchor, no content) ──────────────
-- One row per book-as-bibliographic-thing. Deliberately holds almost nothing:
-- its job is to be a stable thing for copy and edition_revision to point at.
-- All descriptive fields live in edition_revision, never duplicated here.
CREATE TABLE edition (
    edition_id  INTEGER PRIMARY KEY,          -- surrogate identity; auto-assigned
    isbn13      TEXT UNIQUE,                   -- business key; NULL for no-ISBN books
    created_at  TEXT NOT NULL,                 -- when this edition first entered the DB
    CHECK (isbn13 IS NULL OR length(isbn13) = 13)
) STRICT;


-- ── edition_revision : append-only full snapshots of the descriptive fields ─
-- Each row is a COMPLETE picture of the edition's metadata at one point in time.
-- Columns mirror the ISBNdb / photosearch sheets (they share one schema), so an
-- API result lands as one revision unchanged; a manual correction lands as the
-- next revision. Reads go through edition_current (below), not this table.
CREATE TABLE edition_revision (
    revision_id    INTEGER PRIMARY KEY,
    edition_id     INTEGER NOT NULL REFERENCES edition(edition_id),

    -- provenance of THIS revision (authoring agent, not per-field provenance)
    source         TEXT NOT NULL CHECK (source IN ('isbndb','photosearch','manual')),
    comment        TEXT,                        -- optional: why this revision exists
    created_at     TEXT NOT NULL,

    -- bibliographic snapshot (mirrors the ISBNdb sheet's return fields) --------
    title          TEXT,
    title_long     TEXT,
    subtitle       TEXT,                        -- may differ between editions
    authors        TEXT,                        -- comma-delimited, as the API gives
    publisher      TEXT,
    date_published TEXT,                        -- API returns mixed forms ('2020-09', '2025')
    print_edition  TEXT,                        -- ISBNdb's "edition" field, renamed (edition is taken)
    pages          INTEGER,
    binding        TEXT,
    language       TEXT,
    dimensions     TEXT,                        -- raw dimensions string from API
    height_cm      REAL,
    length_cm      REAL,
    width_cm       REAL,
    weight_kg      REAL,
    subjects       TEXT,                        -- ISBNdb subjects (NB: not your personal tags)
    dewey_decimal  TEXT,
    isbn10         TEXT,                         -- retained for the legacy bridge / reference
    cover_url      TEXT                          -- as-returned API cover; managed covers live in `cover`
) STRICT;

CREATE INDEX ix_revision_edition ON edition_revision(edition_id, created_at);


-- ── copy : a physical book you own (the movement-log anchor) ────────────────
CREATE TABLE copy (
    copy_id     INTEGER PRIMARY KEY,
    edition_id  INTEGER NOT NULL REFERENCES edition(edition_id),
    note        TEXT,                            -- copy-level fact: "annotated, memory lane", "Cover fehlt"
    created_at  TEXT NOT NULL
) STRICT;

CREATE INDEX ix_copy_edition ON copy(edition_id);


-- ── space : a container for books, extensible past the Magazin ──────────────
-- A 5x5 Kallax rack is ONE space with 25 bins; the bin is named on the
-- location_event (bin_label), not here. A table or cupboard may have no bins.
CREATE TABLE space (
    space_id    INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('kallax_rack','cupboard','table','shelf','other')),
    room        TEXT,                            -- 'Magazin', 'Wohnzimmer', …
    label       TEXT NOT NULL,                   -- 'rack 03', 'cupboard A'
    bin_count   INTEGER,                         -- optional: 16/25/12/8 for Kallax; NULL if N/A
    created_at  TEXT NOT NULL
) STRICT;


-- ── location_event : append-only movement log ──────────────────────────────
-- Current location of a copy = the single row with valid_to IS NULL.
-- A move = close the open row (set valid_to) and insert a new open row.
-- position is REAL on purpose: to slot a book between 1.0 and 2.0 you insert
-- 1.5, with no renumbering of the whole bin during reorganisation.
CREATE TABLE location_event (
    loc_id      INTEGER PRIMARY KEY,
    copy_id     INTEGER NOT NULL REFERENCES copy(copy_id),
    space_id    INTEGER NOT NULL REFERENCES space(space_id),
    bin_label   TEXT,                            -- box number e.g. '01'..'25'; NULL if space has no bins
    position    REAL,                            -- sortable order within the bin; NULL if not applicable
    valid_from  TEXT NOT NULL,
    valid_to    TEXT,                            -- NULL = current
    comment     TEXT
) STRICT;

CREATE INDEX ix_locevent_copy ON location_event(copy_id);
-- At most ONE current location per copy (partial index = the temporal invariant):
CREATE UNIQUE INDEX ux_locevent_current ON location_event(copy_id) WHERE valid_to IS NULL;


-- ── tag + copy_tag : personal tags (rib, many-to-many) ──────────────────────
-- The master tag list (your "Tags" sheet) lives in `tag`; copies carry tags via
-- copy_tag. We attach tags to the COPY, as decided. If genre tags ever feel
-- edition-level, they can be re-homed later — copy is the chosen home for now.
CREATE TABLE tag (
    tag_id   INTEGER PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE copy_tag (
    copy_id  INTEGER NOT NULL REFERENCES copy(copy_id),
    tag_id   INTEGER NOT NULL REFERENCES tag(tag_id),
    PRIMARY KEY (copy_id, tag_id)
) STRICT, WITHOUT ROWID;          -- pure junction table; WITHOUT ROWID is the tidy idiom here


-- ── cover : cover images (rib) — references on disk/URL, never image bytes ──
-- An edition-level cover (a stock image: isbndb / amazon / zvab) sets
-- edition_id; a copy-level cover (your own photo of THAT physical book) sets
-- copy_id. Exactly one of the two. `kind` separates URLs from file paths
-- (retiring the quick-and-dirty moniker-mixing). The view honours both
-- `preferred` and `status`.
--
-- status is a MANUAL judgement — source and URL cannot tell us quality (the API
-- may return a desk snapshot, a publisher logo, or an interior page just as
-- readily as a real cover):
--   unreviewed = fetched but not yet judged (ingest default)
--   ok         = usable
--   missing    = a "no cover" placeholder        (your "Cover fehlt")
--   wrong      = shows something, but not the cover (your "Cover falsch")
-- A non-ok row is KEPT (the durable record of the judgement) but not shown; the
-- book then falls back to the next preferred ok cover, else the app placeholder.
-- "Needs a cover" = an edition with no ok cover row at all (covers cases 1/2/3).
--
-- local_path = where the image is cached on disk once downloaded. The URL→file
-- association lives HERE, in data, not in the xlsm. View resolution rule:
-- show local_path if present, else ref. "Not yet cached" = local_path IS NULL
-- (that predicate is the downloader's worklist). Relative-vs-absolute path is
-- deferred to the cross-boundary DevOps step.
CREATE TABLE cover (
    cover_id    INTEGER PRIMARY KEY,
    edition_id  INTEGER REFERENCES edition(edition_id),
    copy_id     INTEGER REFERENCES copy(copy_id),
    kind        TEXT NOT NULL CHECK (kind IN ('url','file')),
    ref         TEXT NOT NULL,                   -- origin: the URL, or a directly-supplied file path
    local_path  TEXT,                            -- cached file on disk; NULL = not (yet) downloaded
    status      TEXT NOT NULL DEFAULT 'unreviewed'
                     CHECK (status IN ('unreviewed','ok','missing','wrong')),
    preferred   INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0,1)),
    source      TEXT,                            -- 'isbndb','amazon','zvab','own_photo','manual', …
    created_at  TEXT NOT NULL,
    CHECK ((edition_id IS NULL) <> (copy_id IS NULL))   -- exactly one owner
) STRICT;

CREATE INDEX ix_cover_edition ON cover(edition_id);
CREATE INDEX ix_cover_copy    ON cover(copy_id);


-- ============================================================================
--  VIEWS — the read layer. Everything (shelf/list views, PyXLL) reads here,
--  never the append-only base tables directly.
-- ============================================================================

-- edition_current : the newest revision per edition, joined to its identity.
-- ROW_NUMBER() numbers revisions newest-first within each edition; we keep #1.
-- This one window query is written ONCE; downstream just SELECTs from the view.
CREATE VIEW edition_current AS
SELECT e.edition_id,
       e.isbn13,
       r.source, r.comment, r.created_at AS revised_at,
       r.title, r.title_long, r.subtitle, r.authors, r.publisher,
       r.date_published, r.print_edition, r.pages, r.binding, r.language,
       r.dimensions, r.height_cm, r.length_cm, r.width_cm, r.weight_kg,
       r.subjects, r.dewey_decimal, r.isbn10, r.cover_url
FROM edition AS e
JOIN (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY edition_id
               ORDER BY created_at DESC, revision_id DESC   -- revision_id breaks created_at ties
           ) AS rn
    FROM edition_revision
) AS r ON r.edition_id = e.edition_id AND r.rn = 1;


-- book_current : illustrative convenience view for the shelf/list layer —
-- one row per COPY with its current bibliographic data and current location.
-- (Sketch: columns/shape will firm up when we wire the views to the DB. A
-- photo/pre-ISBN copy appears here exactly like any other — its provisional
-- edition simply has NULL isbn13 and VLM-sourced title/author.)
CREATE VIEW book_current AS
SELECT c.copy_id,
       c.edition_id,
       ec.isbn13,
       ec.title,
       ec.subtitle,
       ec.authors,
       c.note,
       le.space_id,
       sp.label   AS space_label,
       sp.room,
       le.bin_label,
       le.position
FROM copy AS c
JOIN edition_current AS ec ON ec.edition_id = c.edition_id
LEFT JOIN location_event AS le ON le.copy_id = c.copy_id AND le.valid_to IS NULL
LEFT JOIN space AS sp ON sp.space_id = le.space_id;


-- ============================================================================
--  Reminder for whoever connects (script, PyXLL, sqlite3 CLI):
--      PRAGMA foreign_keys = ON;        -- per connection; OFF by default
--  Seeding (spaces for the Magazin racks, the tag master list) and the
--  ingest of Protocol/Photos/ISBNdb belong to tomorrow's session, not here.
-- ============================================================================
