# Haddolib -- Design & Decisions

*The living orientation doc for haddolib. It carries the **current architecture**, what is
**contract**, what is **settled** (and why), and what is **open**. The five-grain "dream"
model that preceded the current build is preserved here as a bounded appendix (§8), not the
spine. Start here to understand the project; drop into the code or the frozen decision-records
for depth.*

---

## 0. How to read the docs

| Doc | Role | In the dump? |
|---|---|---|
| **`haddolib-design.md`** (this) | Living orientation: contract / settled / open / why | yes |
| **`README.md`** | Current state -- how the pieces hang together, how to run | yes |
| **`GOALS.md`** | Direction: the "Current Session Pointer" + roadmap | yes |
| **`TODO.md`** | Scratchpad: pending work, parked ideas, the import-hardening backlog | yes |
| the **code** + `data/haddolib_prototype.sql` | The behavioural / exact-column source of truth | yes |

A naming note carried throughout: the current architecture was built under the working name
**"prototype."** It has earned its keep and will do the heavy lifting for a long time, so in
prose we call it **the current architecture**. The word *prototype* survives only as **code
symbols** (`proto_db` fixture, `data/haddolib_prototype.sql`) -- renaming working, tested code
buys nothing and is deliberately not done.

---

## 1. Project & vision

**Haddolib** catalogues a private library -- ~3,200 books in "the Magazin" (a dedicated basement
room) plus ~400 elsewhere in the house -- belonging to Frank and his wife.

Two phases run in parallel: a **physical track** (scan barcodes → enrich via the ISBNdb API →
pre-curate in `racks.xlsm`), which is the bulk of the human work; and a **foundation track** --
a local SQLite database that becomes the master record, with Excel staying the frontend via
PyXLL. The working sessions are the foundation track.

Guiding philosophy: **human-curated, tool-assisted.** Excel stays the primary interface for the
foreseeable future -- it is comfortable and powerful, and the real end-user experience (Frank and
his wife browsing and tagging together, Mac cast to the TV) is itself shaping what any eventual
app should be. Crucially, the goal is **not** a generic library-management system. It is a tool
for ~2 people (≤5 with close friends/family), and within that scope it may end up *more* tailored
than any off-the-shelf LMS, precisely because it fits exactly one collection and one workflow.
"No over-engineering" and "fits us exactly" are the same instruction.

---

## 2. Physical structure of the Magazin

Books live in IKEA Kallax units ("racks"), each subdivided into boxes (numbered top-to-bottom,
left-to-right when facing the rack). Configurations in use: 4×4 (16 boxes), 5×5 (25), 3×4 (12),
2×4 (8), 2×5 (10), 2×2 (4). Racks 1–8 are freestanding and loaded from **both sides** (front and
back are independent racks with their own box numbering); the rest stand against walls (front
only). A book's physical address is **rack + box** (and, within a box, an order that matters for
browsing). ~15 racks / ~256 boxes are indexed.

**Scale (June 2026):** ~2,620 books with ISBNs scanned, +~329 with cover photos (no usable
barcode), + rack 15 (~8 boxes of cookbooks) still to input → **~3,200 in the Magazin**, plus
**~400** in yet-to-be-numbered spaces elsewhere. A lot of scanning remains; many photos are not
yet looked up. The data model must therefore stay friendly to **continuous bulk inflow**, not
assume a finished catalogue.

**The one duplicate.** Across the whole collection there is exactly **one** retained physical
duplicate -- *Optionen und Futures verstehen* (`9783423058087`), where a heavily-annotated older
edition is kept beside the newer one. It sits on a special shelf, formally re-admitted later.
This single case is the entire justification a distinct *copy* layer would ever have had -- and
the reason there isn't one yet (see §6, the dreamland heuristic).

---

## 3. Current architecture (the spine)

### 3.1 Schema -- five tables and one view

`data/haddolib_prototype.sql` is the exact-column source of truth; the concepts:

```
book ──< book_revision     append-only FULL bibliographic snapshots (words only)
  │
  ├──> cover (preferred)    book.preferred_cover_id points at ONE cover row
  ├──< cover                zero-to-many cover images (rows, not slots)
  └──< book_tag >── tag     personal tags, many-to-many (case-insensitive)
```

- **`book`** -- one row per physical book. Identity (`book_id` surrogate = the merge anchor;
  `isbn13` nullable + `UNIQUE`), inline location (`room / space_label / bin_label / position`),
  workflow `status`, free `note`, and `preferred_cover_id`.
- **`book_revision`** -- append-only full metadata snapshots, **words only** (no cover fields).
  Newest revision per book is "current." A blank field means *empty*, not *unchanged*.
- **`cover`** -- one row per image (`ref`, `source`, `status`); zero-to-many per book.
- **`tag` + `book_tag`** -- many-to-many; case-insensitive via a `NOCASE` unique index, first
  spelling stored.
- **`book_current`** -- the read layer; everything reads here, never the base tables. **Implemented
  as a `LEFT JOIN`** to the newest-revision subquery and to the preferred cover, so a
  freshly-scanned, revisionless, or coverless book still shows (NULL bib/cover fields). *(This is
  a deliberate deviation from `PROTOTYPE_SCHEMA_DECISION.md` §3, which shows an inner `JOIN`; the
  LEFT JOIN is the current truth.)*

### 3.2 The write path -- crossing 1 (import)

Data reaches the DB through **four PyXLL "bridge crossings"**; only the first is batch-driven and
it is **insert-only** (proven live: books, revisions, tags, covers, `preferred_cover_id`
auto-promotion all verified in the VM):

```
roster.py        pure mapping: one roster row → book/revision/cover/tag buckets (map_row,
   │             FIELD_MAP, split_tags, unknown_headers). No DB, no PyXLL -- testable on macOS.
   ▼
roster_import.py insert_book_row (per-row write) + import_roster (the driver: dedup pre-load,
   │             validators, per-row commit + error isolation, ImportSummary).
   ▼
bridge_core.py   pure orchestration (macOS-tested): parse the block, write the rejected file,
   │             pack the summary string. One "now" stamps created_at AND the filename.
   ▼
pyxll_bridge.py  thin @xl_macro("var[][] data") wrapper; opens/closes the live connection per call.
   ▼
VBA (modHaddoImport)  the button sub that knows display semantics; calls Python, shows the summary.
```

Dedup is **staggered on isbn13-presence**: a book with an `isbn13` dedups on that (a wrong-checksum
ISBN is declined as `invalid_isbn13` *before* it can enter the dedup set); a photo book (no isbn13)
dedups on its cover `ref`, against photo books only (so shared ISBNdb placeholder URLs never
false-decline); a row with neither key is declined `no_key`. Newly-inserted keys join the in-memory
sets, so within-batch duplicates are caught too. Each insert commits on its own; a row that raises is
rolled back and recorded -- one bad row never aborts the run.

### 3.3 The validators -- two slots, by necessity

Per-row checks are small `(...) -> (reason_code, detail) | None` functions, first hit rejects.
They live in two slots:

- **BEFORE `map_row`** -- checks that must pre-empt eager coercion. `_check_numeric_types`
  (`non_numeric_value`) catches a text cell in a numeric column (e.g. a German-comma `"21,59"`)
  that `as_real` would otherwise crash on *outside* the per-row try/except.
- **The identity decision** -- `invalid_isbn13`, then dedup (`duplicate_isbn13` /
  `duplicate_photo` / `no_key`).
- **AFTER the identity decision** -- checks free of the coercion constraint, placed late so an
  identity reason wins and they only reach a row that would otherwise insert:
  `_check_status_blank` (`status_blank`) and `_check_incomplete_location` (`incomplete_location`).

`ImportSummary` itemises every outcome (inserted / declined-by-reason / errors / ignored columns)
and captures every non-insert as `(reason, detail, raw values)` -- the durable source the bridge
turns into the **rejected file** (see §4).

### 3.4 The read path -- live

`query_core.py` (pure, macOS-tested, all tests green) provides two kinds of entry point:

- **`query(conn, name, *params)`** -- the scalar dispatcher. 16 named queries covering location
  hierarchy (`rooms` / `spaces` / `bins` / `space_count` / `location_combo_count`), book counts
  (total, with-bib, photo-only, by-status/source/cover-source/cover-status -- all with optional
  room filter), and vocabulary queries (`distinct_statuses` etc.). Returns `str | int`. Exposed
  via `haddo_query(name, *params)` in `pyxll_bridge.py`.

- **List-returning queries** -- return `list[dict]` (all `book_current` columns + `tags` key,
  tags alphabetically sorted), ordered by physical shelf position (`room, space_label, bin_label,
  position`):
  - `books_by_bin(conn, room, space, bin_label)`
  - `books_by_title(conn, search)` -- case-insensitive substring
  - `books_by_author(conn, search)` -- case-insensitive substring
  - `books_by_tags(conn, tags: list[str], match_all: bool)` -- AND (relational division) or OR
  - `books_by_ids(conn, book_ids: list[int])` -- fetch by id list, result in caller's order
  - `all_books(conn)` -- full catalogue snapshot; the export entry point

  Each of the first five is exposed via a corresponding `@xl_func` in `pyxll_bridge.py` that
  stores the result in the module-level `HandleCatalog` (`catalog.py`) and returns an opaque
  handle string. `all_books` is called directly by `export_core.dump_db` and is not exposed
  as a PyXLL UDF (a full catalogue result set is not a useful Excel range).

- **`tag_stats(conn, order_by_count=True)`** -- returns `list[tuple[str, int]]` of all tags
  (including orphans with count 0). `order_by_count=True`: count desc, name asc as tiebreaker;
  `False`: alphabetical. Exposed via `haddo_tag_stats(order_by_count=True)` returning a `var[][]`
  2D array (`["tag", "count"]` header + data rows). Useful both for curation and as a
  combobox constraint source (`=haddo_tag_stats(FALSE)`).

### 3.5 Tag write path -- live (crossing 2)

`tag_core.py` (pure, macOS-tested) is the write layer for tags:

- **`set_tags(conn, book_id, tags_csv)`** -- replaces all tags for a book atomically
  (delete-all-then-reinsert). Parses `tags_csv` via `split_tags`; case-insensitive tag reuse
  (`COLLATE NOCASE`); auto-creates unknown tags; caller owns the transaction. Exposed via
  `haddo_set_tags(book_id, tags_csv)` which commits and returns `"ok"`.

- **Handle refresh** -- after `haddo_set_tags`, the in-memory snapshot held under the handle is
  stale. `haddo_refresh_handle(handle)` re-fetches all rows via `books_by_ids` and replaces the
  catalog entry in place via `HandleCatalog.replace()`. The handle string is unchanged -- VBA
  holds the same variable and sees updated data on the next `haddo_get_field` call.

### 3.6 Export path -- live

`export_core.py` (pure, macOS-tested) is the dump layer:

- **`dump_db(conn, dest, now)`** -- writes a full `book_current` snapshot (plus tags) to an xlsx
  at `dest`, with headers matching `FIELD_MAP` exactly, so the file is directly re-importable
  via `haddo_import`. Returns the number of books written.
- **`DUMP_FIELDS`** -- the ordered column list (`FIELD_MAP` keys + `TAGS_HEADER`). An import-time
  assertion raises `RuntimeError` if `DUMP_FIELDS` ever drifts out of sync with `FIELD_MAP`.
- **`tools/dump_db.py`** -- CLI wrapper; stamps filename `YYYYMMDD_HHMMSS_dump.xlsx`, writes to
  `data/import/`. Run via `make dump`.
- **Manual bib-correction workflow** (until crossing 4): `make dump` → copy xlsx → edit →
  note change in `revision_comment` → `make bootstrap` → re-import.

### 3.7 The remaining crossings (not yet built)

(3) **Cover management** -- dialog *and* batch; the cover workflow. (4) **Bib editing** -- dialog;
the *only* path that writes a second `book_revision`, deferred past the current scope. Import
carries no update logic.

---

## 4. What's contract

These are the boundaries downstream work must honour.

**The VBA↔Python boundary** (full rationale in `BRIDGE_CONTRACT.md`):
- **VBA orchestrates, Python computes.** Data flows VBA → Python → VBA; Python is pure and
  stateless and never touches Excel's object model. The button sub is the *only* layer that knows
  display semantics.
- **A named `Range`, never `UsedRange`** -- self-documenting, and lets one workbench sheet host many
  independently-triggered blocks.
- **Generic `var[][]`, not a DataFrame** -- the boundary stays dumb; `common.as_text/as_int/as_real`
  is the single typing authority (blank/`""`/`Empty` → `None` → NULL). pandas' NaN/dtype model would
  fight that rule.
- **Return channel: a delimited-string scalar** (VBA `Split`s it into a `Scripting.Dictionary`).
  Array-out via `Application.Run` was smoke-tested and found flaky; the delimited string ships
  regardless.
- **Validation lives in the driver, not the bridgehead**, so every decline lands in one unified
  `ImportSummary` / one rejected file. The bridgehead only marshals: strip a leading
  `rejected_reason` column if present, split headers/rows, call `import_roster`, write the rejected
  file, return the summary.

**The rejected file** (supersedes `BRIDGE_CONTRACT.md` §5's CSV):
- An **xlsx** written by Python with **typed cells** (German-Excel safe -- ISBNs stay text, no
  `9,78E+12`, no `02. Mai` date-guessing, no lost leading zeros).
- Columns: **`rejected_reason`** (stable token, or the exception message for an errored row), then
  **`rejected_detail`** (free text naming the offending cell for field-level checks; blank for
  identity checks/errors), then the original row **verbatim**. Open it, read the reason, fix the
  cell, re-import.
- Path `data/import/YYYYMMDD_HHMMSS_rejected.<ext>`; `data/import/` is a dedicated, git-ignored
  directory created and owned outside the engine (which assumes it exists). Create-per-run, never
  append.

**The header vocabulary** (`roster.FIELD_MAP`): column *order* is free, the header *string* maps.
All column names are unique and unambiguous -- there are no dot-qualified names (e.g. no
`book.status` / `cover.status` disambiguation is needed because the field names themselves are
distinct: `book_status`, `cover_status`, `revision_source`, `cover_source`, etc.). This
uniqueness is **load-bearing**: the dump (`export_core.DUMP_FIELDS`) and the import (`FIELD_MAP`)
must speak the same vocabulary, and any future field addition to the schema must preserve
uniqueness across the full set. `tags` is comma-split (a semicolon would be two Excel columns in
Germany). Blank header = skipped column; unrecognised header = reported (`unknown_headers`), never
fatal; blank cell = NULL.

**The read path:** a pure `query_core.py` (tested on `proto_db`) → thin `@xl_func` UDFs in
`pyxll_bridge.py`. Scalar queries dispatched as `haddo_query(name, …params)`; list queries return
opaque handles consumed via `haddo_len` / `haddo_get_field` / `haddo_release`. Raw-SQL-from-VBA
was considered and rejected -- query logic and schema-coupling stay centralised in `query_core`.
All list-returning queries order by physical shelf position (zero-padded labels, so text-sort ==
natural-sort).

**Handle contract:** handles are opaque strings (`haddo:{session_id}:{kind}:{token}`); the kind
(`books_by_bin`, `books_by_title`, etc.) is diagnostic only. `haddo_len` / `haddo_get_field` /
`haddo_release` are kind-agnostic -- VBA does not need to know which query produced a handle.
`haddo_get_field` raises a descriptive `KeyError` (listing available fields) for unknown field
names. TTL 600 s; `haddo_sweep_handles` evicts stale entries.

---

## 5. Settled decisions (with the one-line why)

- **`edition` + `copy` collapse into `book`** -- the dreamland heuristic (§8): a structural layer
  whose real population is *one* belongs in a `note`, not a table.
- **Location is inline on `book`, anchored by the surrogate `book_id`** -- *not* the Protocol col-`I`
  mistake (which fused identity with position); here editing a location is a plain `UPDATE` and the
  id never moves.
- **Revisions are append-only, words-only snapshots; reads go through `book_current`** -- one source
  of truth for the words, a blank means *empty* not *unchanged*.
- **Covers are rows (not fixed slots), and "which to show" is `book.preferred_cover_id` FK (not a
  `preferred` flag)** -- rows give zero-to-many with no schema change; a pointer can't be set on two
  rows at once the way a flag can. `ON DELETE SET NULL` prevents a dangling pointer.
- **`source` and `status` are open `TEXT` everywhere; no `CHECK` enums** -- provider and vocabulary
  churn (ISBNdb → Open Library / Thalia / …) costs nothing.
- **`isbn13` nullable + `UNIQUE`** -- unlimited NULLs coexist (photo / pre-ISBN books); the UNIQUE is
  the guard against double-adding the same book during messy incremental ingest.
- **`book.status` blank → hard reject** (semantics A: guard a *present* column; a missing column is
  the abort-tier concern in §6). Fail-loud over a silent DDL default; vocabulary stays open.
- **Locations are canonicalised on write, in Python/`roster`** (`f"rack {n:02d}"` / `f"box {n:02d}"`
  from the Protocol integers) -- the engine owns the space/bin vocabulary; zero-padding makes
  text-sort == natural-sort, so queries stay dumb exact-match `WHERE` (no `LIKE`, no query-time
  normalisation). All list-returning queries rely on this: `ORDER BY room, space_label, bin_label,
  position` is correct precisely because labels are zero-padded consistently.
- **Tags case-insensitive** (`NOCASE` unique index, first spelling stored).
- **DB at `C:\SQLite\haddolib\haddolib.db`** (native Windows, not the `Y:` share), never in git,
  backup = periodic copy to `Y:` while idle. **Journal = DELETE** (rollback), not WAL.
  `PRAGMA foreign_keys = ON` per connection (OFF by default in SQLite).
- **Value coercion (`as_text/as_int/as_real`) lives in `common.py`** -- one shared definition; blank
  → NULL is the single rule the whole boundary trusts.
- **Field names are globally unique across the full import/export vocabulary** -- the refactoring
  that unified `book_status` / `cover_status` / `revision_source` / `cover_source` etc. was not
  cosmetic. Unique names mean the dump and import speak the same language with no disambiguation
  layer. Any future schema addition must preserve this property.

---

## 6. Open topics

Deliberately unsettled -- don't guess the structure.

- **Remaining per-row validators** (backlog in `TODO.md`): `invalid_isbn10` + `isbn_pair_mismatch`
  (`isbn10_to_isbn13(isbn10) != isbn13`); `invalid_date_published` -- not a pure validator but a
  **coercing canonicalizer**: float string with `1800 ≤ int(float(v)) ≤ 2100` → store as plain year
  string; float string > 2100 → Excel date serial → convert to `YYYY-MM-DD`; `YYYY-MM` / `YYYY-MM-DD`
  strings pass through; anything else declines with `invalid_date_published`.
  Also: `noncanonical_location` (a safety net once canonical-on-write is relied upon).
- **The abort tier** (whole-block, in `bridge_core`; no warn tier): `missing_required_column`
  -- and **this is where "B" lands**: treating a *missing* `book.status` column as an error is
  status joining the required-column set once this abort exists. Also `duplicate_header`,
  `empty_block`.
- **`book.status` / `cover.status` vocabularies** -- open `TEXT`, discovered through use; a `CHECK`
  may be added once each stabilises (a starting `needs_data / needs_cover / ready` for book;
  `beautiful / from_thalia / wrong / missing / placeholder` for cover).
- **`ref` path resolution** -- relative vs. absolute paths and the URL→file caching association are
  pushed to the Excel/PyXLL layer (a cross-boundary macOS/Windows-VM DevOps detail, not a schema
  concern).
- **Photo-naming convention** -- `rack_01 2026-02-16 21.29.43.jpg` is now the photo-book dedup key;
  confirm it is stable/unique enough or whether a rename step is needed.
- **PyXLL operational** -- array-out reliability (smoke-tested; delimited string ships either way);
  `pyxll.cfg` committed-vs-machine-local; whether/how to run PyXLL *integration* tests in the VM
  (pure-Python tests already run via `make test`).
- **`book_current` columns exposed** -- the view does not surface `created_at`, `preferred_cover_id`,
  or `cover_id` (the cover table's own PK). If any of these are needed downstream (e.g. for cover
  management in crossing 3), they must be added to the view's SELECT list explicitly.

---

## 7. Tests

Two suites run under `make test`. The **active** suite is the current architecture's (the
`proto_db` fixture): the mapping, the insert path, the import driver, and the validators are its
spec -- a check is added by appending a small pure validator plus one test, never by growing an
if-wall. The **dream** suite stays green against `data/haddolib_schema.sql` with its own `db`
fixture: it is **hibernated**, a runnable specification of where haddolib is eventually going, not
developed against. Nothing green is ever broken silently -- tests are retired deliberately.

**Test count (June 2026): 306 green.** Key files: `test_query_core.py` (128 tests) covers the
full read layer including all list-returning queries, `books_by_ids`, `tag_stats`, and `all_books`;
`test_export_core.py` (9 tests) covers the dump layer; `test_tag_core.py` (14 tests) covers the
tag write layer (`set_tags`); `test_catalog.py` (23 tests) covers the handle catalog including
`replace`; `test_bridge_core.py` covers the import pipeline.

---

## 8. Where this is going -- the five-grain dream (bounded appendix)

Before the current architecture, a March–May 2026 design settled a richer five-grain model --
`edition / edition_revision / copy / space / location_event` + a rich `cover`. A June
Scope-Skepticism pass found it *premature* (not wrong): sized for the full ambition while the
near-term need was far smaller -- show basically all the books and their covers, Excel as frontend.
The runway for a giftable artifact was being spent on groundwork. So the model was re-scoped to the
current five-table subset, **non-destructively** -- every omission has a growth path back.

**The dreamland heuristic, worth keeping as a reusable rule:** *a structural layer whose real
population is one belongs in a `note`, not a table.* (The `copy` grain existed to model one
annotated duplicate.) When in doubt elsewhere: how many rows would actually use this distinction?
If the honest answer is "one," collapse it.

| Dream construct (hibernated) | Current shape | Re-add when… |
|---|---|---|
| `edition` + `copy` split, XOR cover ownership | `book` (collapsed) | a second physical copy is formally admitted (the deferred *Optionen und Futures*) |
| `location_event` (append-only history) | inline `room/space_label/bin_label/position` | curation begins and movement history starts to matter |
| richer `cover` (`kind` / `local_path` / `preferred` flag / XOR) | `cover` rows + `book.preferred_cover_id` FK | a viewing scenario needs the richer attributes |
| `synopsis` table | not present | synopsis enrichment is scheduled |
| virtual-ISBN13 scheme | not present | an export needs it (LibraryThing, etc.) |

**A correction the dream itself recorded, worth carrying forward:** a *checkout* (a book taken to
another room) is **not** a move -- its home stays the box; checkout is a temporary overlay
(`checked_out` flag, date, borrower), not a `location_event`. The old treatment of checkout as a
location change was a genuine modelling error this architecture avoids.

For the full reasoning behind the pivot and each growth path, see the frozen
`PROTOTYPE_SCHEMA_DECISION.md`; for the bridge boundary in full, `BRIDGE_CONTRACT.md`.
