# haddolib -- TODO

(Note: "I" in the following paragraphs refer to the user, "you" to you as the AI model.)

## Charter

- Forward-looking only -- concrete, startable work: tasks specified well enough that next-session-me can begin within ten minutes, plus investigation items, test specs, and scratchpad ideas awaiting promotion or deletion.
- Items are unordered within their theme sections; open questions are marked _Needs investigation_ in the bullet.
- When an item is completed, record its durable outcome in `HISTORY.md` during the same session while the evidence and rationale are fresh, then strike it through in `TODO.md` with a concise handover note.
- Retain struck-through items through the next session because `TODO.md` is included in the standard filesdump while `HISTORY.md` normally is not; at the end of that next session, remove the already-archived items from `TODO.md`. Strategic direction, ordering, and milestones live in `GOALS.md` -- anything that needs a strategy discussion before it is actionable goes there.
- Architecture, contract, and settled decisions live in `README.md`.

---

## Active — the refactor pass (next foundation work)

- **Flip `DEFAULT_SCHEMA` to the prototype DDL.** `database.DEFAULT_SCHEMA` currently points
  at the dream schema (`haddolib_schema.sql`); every live code path needs the prototype
  (`haddolib_prototype.sql`). First confirm `tools/bootstrap_db.py` passes the prototype path
  explicitly — it must, since the live import works — then flip the default so a bare
  `apply_schema(connect())` can never silently build the dream schema. ("Prototype" is a
  version moniker now, not a thing to retire.)
- **Extract `_SHELF_ORDER`.** The `ORDER BY b.room, b.space_label, b.bin_label, b.position`
  clause is written longhand in five list queries (`books_by_bin` / `books_by_title` /
  `books_by_author` / `books_by_tags` / `all_books`). Extract it to a shared module-level
  constant in `query_core.py`, mirroring `_TAGS_SUBQUERY`. DRY today; one edit-site instead
  of five when the `location_event` migration eventually re-points shelf ordering.

---

## Pending — crossing 1 hardening

- **`date_published` canonicalizer.** The planned Python-side home for date normalisation — a
  *canonicalizer*, sibling to the validators (coerce-and-normalise rather than reject).
  Reconciliation: Excel date serials are currently normalised upstream during import
  preparation (Excel-side); the standing direction is to migrate that logic *down* into Python
  as this canonicalizer, where it is testable and shared. Cases:
  - float-year string where `1800 ≤ int(float(v)) ≤ 2100` → store as plain year string
  - serial > 2100 → Excel date serial → `YYYY-MM-DD`
  - `YYYY-MM` / `YYYY-MM-DD` strings → pass through unchanged
  - anything else → decline with `invalid_date_published`
- **Remaining validators** (lower priority): `invalid_isbn10` + `isbn_pair_mismatch`
  (`isbn10_to_isbn13(isbn10) != isbn13`); `noncanonical_location` (a safety net once
  canonical-on-write is fully relied upon).

*The validator / canonicalizer sibling-slot model and the Excel→Python migration direction
are described in `README.md` §3.4.*

---

## Pending — quality / cleanup

- **Trim dispatcher echo tests.** ~12–14 tests (number correct?) in `test_query_core.py` re-assert, via
  `query(db, name, …)`, the same values the direct-function tests already prove. The
  dispatcher's genuine spec is only routing + arity / optional-room handling + the unknown-name
  guard — keep a representative per arity class, drop the value-echoes. Run this as **its own
  step, after the refactor pass lands**, so the suite is stable when touched. (Trim only
  echoes; never trim to hit a number.)
- **Umlaut-aware title/author search.** `lower()` / `NOCASE` are ASCII-only, so `müller` does
  not match `Müller`. Decide the fix path (load the ICU extension, or maintain a folded shadow
  column) or accept-and-document. Real and visible for a German collection; not urgent.
- **`as_int` float truncation** (low prio). `as_int` truncates a genuine float (`int(3.9) → 3`)
  rather than rejecting, and `_check_numeric_types` only catches *string* cells in numeric
  columns. Only `pages` uses `as_int`, so stakes are near-zero — a know-it-exists note, not a
  fix.
- **`isbn10` text prefix.** Apply `ISBN_TEXT_PREFIX` in `extract_record` in `isbndb_utils.py`
  so Excel treats ISBN-10 values as text, consistent with `isbn13`. Affects all three lookup
  tools.
- **`pyxll.cfg`:** decide committed-vs-machine-local (it is machine-specific).
- **`lookup_one()` duplication.** `isbndb_search.py` and `isbndb_lookup.py` each still carry their own inline POST-with-429-retry copy of the single-ISBN lookup request. `fetch_editions()` in `isbndb_utils.py` (the GET-side equivalent, extracted this session) shows the shape a shared version could take.
- **`COVER_PLACEHOLDER` heuristic.** _Needs investigation._ `select_best()`'s cover-placeholder detection (`isbndb_utils.py`) assumes ISBNdb consistently marks a missing cover with one specific placeholder image. Real-world use this session suggests that assumption doesn't hold reliably -- the heuristic may need a different signal, or dropping in favour of always preferring a year match where one exists.

---

## Pending — later crossings (dialog-driven; their own sessions)

- **Crossing 3 — cover management:** dialog *and* batch; the cover workflow. The engaging part
  for Frank's wife.
- **Crossing 4 — bib editing:** dialog that writes second+ `book_revision` rows. The only path
  that versions bibliography. Deferred past the current scope.

---

## Prototype open decisions (mirror of `haddolib-design.md` open topics)

- **`book_status` vocabulary:** open `TEXT` for now (e.g. `needs_data / needs_cover / ready`);
  a `CHECK` can be added once it stabilises through use.
- **`cover_status` vocabulary:** open `TEXT` (`beautiful / from_thalia / wrong / missing / …`);
  default `'unreviewed'` on ingest.
- **`cover_ref` path resolution:** relative vs. absolute file paths, and the URL→file caching
  association, pushed to the Excel/PyXLL layer (a cross-boundary DevOps detail).
- **Cover delete → preferred pointer:** `ON DELETE SET NULL` handles the dangle structurally;
  decide whether the delete logic auto-promotes the next cover to preferred (crossing 3).
- **PyXLL integration tests:** the pure-Python suite runs in the VM via `make test`; how/whether
  *PyXLL* integration tests run is still open.
- **Photo-naming convention:** `rack_01 2026-02-16 21.29.43.jpg` is now the photo-book dedup
  key — confirm it is stable/unique enough, or whether a rename step is needed.

---

## Parked / Later

- **Tag pruning** — `haddo_prune_tags()` removes `tag` rows with no `book_tag` references.
  Callable from VBA with a confirm dialog. Low urgency: orphans are visible via
  `haddo_tag_stats()` and harmless until a cleanup pass is wanted.
- **Named handles** — today's handles are opaque random tokens, which is right for sub-driven
  use. User-chosen "speaking" handles (`SHELF-01`, …) are a future affordance if sheet-level
  reuse is ever wanted; the `kind` discriminator is already there. No action now.
- **`.pre-commit-config.yaml`** — Black + basic linting hooks, at a natural pause.
- **Tests for `extract_dimensions` / `extract_record`.** `select_best`, `extract_year`, and `select_best_matching_year` (all in `isbndb_utils.py`) now have coverage via `test_isbn_utils.py`; `extract_dimensions` and `extract_record` in the same module still don't.
- **Anthropic SDK** — add to `requirements.txt` if a Claude API fallback for photo analysis
  lands.
