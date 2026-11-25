# haddolib -- History

(Note: "I" in the following paragraphs refer to the user, "you" to you as the AI model.)

- The resolved-work record: what was built and when (note date, or have the points in roughly reverse-chronological order).
- This is the trophy case -- kept in the repo, **out of the per-session filesdump** (so it no longer rides along every session).
- For _forward_ work see `TODO.md`; for direction see `GOALS.md`; for the architecture as it stands see `README.md`.
- See "Workflow for the Whole Session (CRITICAL)" in `LLM_INSTRUCTIONS.md` for the interplay between `TODO.md` and this file. 

---

## ISBNdb synopsis pipeline for pdf-annotations (-> 324 tests green)

- **`isbndb_utils.py` gains networking and selection.** `select_best()` relocated here from `isbndb_search.py`; `fetch_editions()` extracted as the one shared GET-with-429-retry request; `extract_year()` + `select_best_matching_year()` added for local year-matching (no API year parameter); `RECORD_CSV_FIELDS` centralises the record column list.
- **`scripts/pdf_lst_to_queries.py`** (new) -- parses `(Author[+Author...] YYYY[a]) Title.pdf` filenames from a `*.lst` into a query CSV; malformed filenames are skipped, not fatal.
- **`scripts/isbndb_synopsis.py`** (new) -- resolves each query row, writes one `<pdf_id>.txt` synopsis file (zero-length when not found or empty), `--force` to re-query, skips already-resolved `pdf_id`s by default; output CSV adds `pdf_id` / `year_searched` / `year_matched` / `has_synopsis`.
- **Two new `make` targets** -- `pdf-lst-to-queries`, `isbndb-synopsis`, default paths baked in, overridable via `ARGS`.
- **Verified live** -- 5-PDF batch via the real ISBNdb API, 4/5 found, 3/5 with a non-empty synopsis.

## DB dump / export -- the re-importable round-trip (-> 306 tests green)

- **`query_core.all_books(conn)`** -- full catalogue snapshot in physical shelf order; same `list[dict]` shape as the other list queries (`book_current` columns + `tags`).
- **`export_core.dump_db(conn, dest, now)`** -- pure export layer. Calls `all_books`, maps to `DUMP_FIELDS` (= `FIELD_MAP` keys + `tags`, in table-grouped order), writes via `common.write_xlsx`. An import-time sanity check raises `RuntimeError` if `DUMP_FIELDS`drifts out of sync with `FIELD_MAP`.
- **`export_core.DUMP_FIELDS`** -- the ordered column list for the dump xlsx; every entry is a `FIELD_MAP` key or `TAGS_HEADER`. Load-bearing: import maps by header string, so dump and import must speak the same vocabulary.
- **`tools/dump_db.py`** -- CLI: opens the live DB, stamps `YYYYMMDD_HHMMSS_dump.xlsx`, writes to `data/import/`, reports the book count. **Verified live on the VM.**
- **`make dump`** -- one-liner target.
- **Manual bib-correction workflow** (until crossing 4): `make dump` -> edit the xlsx -> note the change in `revision_comment` -> `make bootstrap` -> re-import.

## Crossing 2 -- tag management (-> 288 tests green)

- **`tag_core.py`** -- pure tag write layer. `set_tags(conn, book_id, tags_csv)`:delete-all-then-reinsert; case-insensitive tag reuse (`COLLATE NOCASE`); auto-creates unknown tags; caller owns the transaction.
- **`haddo_set_tags(book_id, tags_csv)`** -- `@xl_func` wrapper; opens/closes the DB per call; commits; returns `"ok"`.
- **`haddo_refresh_handle(handle)`** -- after a write the snapshot is stale; this UDF re-fetches all rows for the handle's `book_id`s via `books_by_ids` and replaces the catalog entry in place. The handle string is unchanged, so VBA holds the same variable.
- **`catalog.replace(handle, data)`** -- new `HandleCatalog` method; updates the stored data and refreshes `last_accessed_at` under the lock.
- **`books_by_ids(conn, book_ids)`** -- single `IN` query + Python reorder to preserve the caller's sequence.
- **`_TAGS_SUBQUERY` alphabetical ordering** -- inner `SELECT … ORDER BY t.name` so `GROUP_CONCAT` always produces alphabetically sorted tag strings.
- **`tag_stats(conn, order_by_count=True)`** -- `LEFT JOIN` so orphans appear with count 0; `order_by_count` switches between count-desc and alpha-asc.
- **`haddo_tag_stats(order_by_count=True)`** -- `@xl_func` returning `var[][]`; header row + data rows. `=haddo_tag_stats(FALSE)` for combobox sources.

## List-returning queries + the first VBA bookshelf sub (-> 261 tests green)

- **`books_by_title` / `books_by_author` / `books_by_tags`** added to `query_core.py`; all return `list[dict]` with full `book_current` fields + `tags`, same shape as `books_by_bin`. The tags query uses relational division (`HAVING COUNT(DISTINCT tag_id) = N`) for AND logic; input dedup via `dict.fromkeys` protects the count. `_TAGS_SUBQUERY` extracted as a shared module-level constant.
- **`haddo_books_by_title` / `haddo_books_by_author` / `haddo_books_by_tags`** added to `pyxll_bridge.py`. Comma-string splitting for tags is done in the bridge, keeping `query_core.py` clean with typed signatures.
- **`haddo_get_field` unknown-field error** -- now raises a `KeyError` with a readable message listing the available fields.
- **`haddo_len` / `haddo_get_field` / `haddo_release` made kind-agnostic** -- all three call `_CATALOG.get(handle)` without `expected_kind`, so they work uniformly across every `haddo_books_by_*` handle. The kind string is preserved in the handle for diagnostics.
- **`clHaddoBookshelf`** -- the first real VBA bookshelf consumer, live: cover display, next/prev rack/box navigation (`RackBoxes.bas`), click-handler with a tag stub.

## Catalog refactor -- `HandleCatalog` extracted (-> 226 tests green)

- **`HandleCatalog` class extracted to `catalog.py`** (pure, stdlib only, no PyXLL). Injectable `now_fn` clock makes sweep / TTL tests deterministic (no `sleep()`). Injectable `session_id` preserves the stale-handle-after-reload signal. Each instance owns its own state -- tests never bleed through a module global.
- **`test_catalog.py`** -- macOS tests: handle format + uniqueness, put/get round-trip, last-accessed refresh, unknown-handle `KeyError`, wrong-kind `TypeError`, release idempotency, sweep-by-age (injected clock), default-TTL fallback, snapshot shape, instance independence, concurrency smoke.
- **`pyxll_bridge.py` rewired** -- the four `_*_catalog` private functions, `_CATALOG_LOCK`, `_SESSION_ID`, and `_DEFAULT_TTL_SECONDS` removed; replaced by one module-level `HandleCatalog()` instance. The six `@xl_func` wrappers are unchanged in signature; VBA sees nothing different. VM smoke confirmed (rack 06 / box 04, 9 books).

## xlsx switch, crossing-1 hardening, read-path direction (crossing 1 verified live: 2,933 books)

- **Rejected file CSV -> xlsx** via `common.write_xlsx`; native cell types, no type forcing (ISBNs stay text -- no `9,78E+12`, no lost leading zeros, no date-guessing). `openpyxl` added to both requirements files.
- **`rejected_detail` column** -- field-level reject detail (`width_cm = '1,2927' is not a number`) in column B alongside the machine code in column A.
- **`non_numeric_value` pre-validator** -- a raw-value check that runs *before* `map_row`'s eager coercion, so a German-comma string becomes a clean, fixable reject instead of crashing the run.
- **Summary key** `rejected_csv` -> `rejected_rows_file`.
- **Crossing 1 verified live** -- 2,933 books imported; rejected xlsx with field-level detail confirmed.
- **Read-path direction set** -- a pure `query_core.py` (16 named queries) -> thin `haddo_query` UDF -> Excel cells. Raw-SQL-from-VBA was considered and rejected, keeping query logic centralised.
- **Handle catalog live** -- `haddo_books_by_bin` / `haddo_get_field` / `haddo_len` / `haddo_release` / `haddo_sweep_handles` / `haddo_handles` proven on real data.

## Earlier prototype-session milestones

The prototype foundation, built before the items above: the prototype schema (`book / book_revision / cover / tag / book_tag` + the `book_current` view) with a `proto_db`fixture beside the dream `db` fixture; the pure roster mapping (`roster.py` -- one row -> typed buckets, free column order, blank-header skip, `""`->NULL coercion, comma-split tags); the insert path (`insert_book_row` -- book -> revision-if-real-bib -> cover-with-auto-preferred ->tags); the import driver (`import_roster` -- staggered dedup, per-row commit, per-row error isolation, `ImportSummary`); and the first live import roundtrip.

## Before the prototype -- the dream and the pivot

A March–May 2026 design settled a richer five-grain model (`edition / edition_revision / copy / space / location_event` + a rich `cover`). A June Scope-Skepticism pass found it *premature* (not wrong) and re-scoped, non-destructively, to the current five-table subset, with a documented growth path back for every omission. The full reasoning, the dream model in detail, and the earlier upstream tooling (ISBNdb integration, local-VLM photo analysis, the cover downloader, the `racks.xlsm` workbench) are preserved in `haddolib-design.md` on the heap.
