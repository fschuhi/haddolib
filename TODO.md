# haddolib -- TODO

(Note: "I" in the following paragraphs refer to the user, "you" to you as the AI model.)

## Charter

- Forward-looking only -- concrete, startable work: tasks specified well enough that next-session-me can begin within ten minutes, plus investigation items, test specs, and scratchpad ideas awaiting promotion or deletion.
- Items are unordered within their theme sections; open questions are marked _Needs investigation_ in the bullet.
- When an item is completed, record its durable outcome in `HISTORY.md` during the same session while the evidence and rationale are fresh, then strike it through in `TODO.md` with a concise handover note.
- Retain struck-through items through the next session because `TODO.md` is included in the standard filesdump while `HISTORY.md` normally is not; at the end of that next session, remove the already-archived items from `TODO.md`. Strategic direction, ordering, and milestones live in `GOALS.md` -- anything that needs a strategy discussion before it is actionable goes there.
- Architecture and contracts live in `README.md`.

---

## Streamlining -- what is left

- **Comments that point at missing docs.** `bridge_core.py` and `pyxll_bridge.py` refer to sections of `BRIDGE_CONTRACT.md`, which is not in the repo. Point them at `README.md` section 5 instead, or drop the reference.
- **`binl` in the test helpers.** `tests/test_bridge_core.py` and `tests/test_roster_import.py` call the bin label `binl` in their row helpers; rename it to `bin_label`.
- **Three pyflakes warnings.** f-strings without placeholders in `scripts/isbndb_lookup.py` (line 181) and `scripts/isbndb_query.py` (line 138); an unused variable `b2` in `tests/test_roster_import.py` (line 108).
- **Extract `_SHELF_ORDER`.** The five list queries in `query_core.py` each end with `ORDER BY b.room, b.space_label, b.bin_label, b.position`. Write it once as a module-level constant, like `_TAGS_SUBQUERY`. Related: haddoapp sorts with `book_id` as a last tiebreaker and haddolib does not, so two books with the same (or no) `position` in one box can come out in a different order in Excel and in the app.

---

## Synopses

- ~~**Download the synopses of all ISBNdb books.**~~ -- done 2026-11-26: `make isbndb-synopsis-isbn13` reads the newest snapshot, takes the rows with `revision_source` = `isbndb` and an `isbn13` (2,723 books), fetches them in 28 bulk calls and writes `data/synopses/<isbn13>.txt` verbatim (UTF-8 with BOM; empty file = looked up, nothing found; README section 5.7). Result: 1,415 with a synopsis, 1,308 empty. Sampled empty files also have no synopsis on the ISBNdb website, so the gap is ISBNdb's, not ours; German books (`9783...`) are much worse than US (`9781...`) and UK (`97810...`) ones. Keyed by `isbn13`, so `stable_book_id` is not needed for synopses.
- **Fill the gaps from other catalogues** (later; the 52% will do for Christmas). The German National Library is a candidate: one synopsis already seen has a `(via https://deposit.dnb.de/...)` source note, which is plain text in the file. Same file contract, so the app does not change.
- **Synopses in the app (haddoapp) -- waits for the book-page fields.** haddoapp first needs its other fields on the book page; that decides where the synopsis goes (a row of the description list, as ISBNdb's own page lays it out, or a block of its own below the cover). The implementation, once that is settled:
  - `src/synopsis.js`: a pure `parseSynopsis(text) -> blocks` (paragraph with plain/bold/italic runs, or bullet list), tested with vitest.
  - What the files contain (tag survey 2026-11-26): `<br>` (994), `<p>`, `<i>`, `<b>`, `<br/>`, `<li>`, `<ul>`, a few `<em>`. Entities: `&quot;`, `&hyphen;`, `&amp;`, `&#160;`, `&#8212;`. Decode numeric entities and a small map of named ones; leave unknown ones as they are.
  - Do not use `innerHTML`. Recognise only the known tags and show everything else as literal text: a few German synopses contain literal angle brackets (`<Augusta Victoria>`, `<<, sagt Lazy. >`, apparently guillemets that were converted), which an HTML parser would swallow as unknown tags. Rendering React elements needs no sanitiser.
  - Loading: `fetch('synopses/' + isbn13 + '.txt', { cache: 'no-cache' })` when the book page opens. Show the text only if the response is OK, has content type `text/plain`, and the text is not empty after `trim()` (nginx answers 404 for a missing file, but the Vite dev server answers 200 with `index.html`). `fetch().text()` should strip the BOM; untested, `trim()` covers it.
  - Dev: symlink `public/synopses` -> `~/Projects/haddolib/data/synopses` (like covers and photos; `make deploy` leaves `public/` out of `dist/`).
  - NAS, as for covers and photos: copy `data/synopses/` to `docker/haddolib/synopses/`, create the empty mount point `docker/haddoapp/synopses/` first (the app folder is mounted read-only), add the third read-only mount `/volume1/docker/haddolib/synopses` -> `/usr/share/nginx/html/synopses`, recreate the container (about 2 minutes).
  - `data/synopses/` goes into `.gitignore`.
- **Synopses through an nginx proxy instead of files** (a fork to revisit, not planned). The app only ever shows one synopsis at a time, so nginx could proxy `/synopsis/<isbn13>` to ISBNdb and add the `Authorization` header: no files, no copying, no mount. Costs: a config file mounted into the container, the app depends on ISBNdb being reachable and on the daily quota, no offline copy, and the German gap stays.
- **`isbndb_synopsis.py` records failures as "nothing found".** It uses `fetch_editions()`, which returns `[]` when a request fails, so a VPN or quota failure becomes a zero-length file that later runs skip. `fetch_by_isbn13()` raises instead. Give `fetch_editions()` the same behaviour and let the script stop, like `isbndb_synopsis_isbn13.py`.
- **`--force` run to count the cases** (optional). The script now counts "returned without a synopsis" and "not returned by ISBNdb" separately, but the first run predates that. A `--force` run is 28 of 5,000 daily calls.

---

## Pending -- import checks

- **Remaining validators** (low priority): `invalid_isbn10`, and `isbn_pair_mismatch` (`isbn10_to_isbn13(isbn10) != isbn13`).
- **Import block counted by column B.** The defined name of each import sheet counts its rows in column B (`room`). A row with an empty `room` shortens the block, and the last rows are silently left out. _Needs investigation_ (Excel side): count by a column that is never empty, or check the count against the sheet.

---

## Pending -- quality / cleanup

- **Trim dispatcher echo tests.** Some tests in `test_query_core.py` re-check, via `query(seeded_db, name, ...)`, values the direct-function tests already check. The dispatcher's own job is routing, the number of parameters, the optional room filter and the unknown-name error; keep one test per kind of call and drop the repeats. Do it as its own step.
- **Umlaut-aware title/author search.** `lower()` and `NOCASE` handle ASCII only, so `müller` does not find `Müller`. Options: load the ICU extension, or keep a folded copy of the column. Visible for a German collection; not urgent.
- **`as_int` truncates floats** (low priority). `as_int` turns `3.9` into `3` instead of rejecting it, and `_check_numeric_types` only catches text cells in numeric columns. Only `pages` uses `as_int`.
- **`isbn10` text prefix.** Apply `ISBN_TEXT_PREFIX` in `extract_record` in `isbndb_utils.py`, so Excel treats ISBN-10 values as text, like `isbn13`. Affects all three ISBNdb lookup scripts.
- **`pyxll.cfg`:** committed or machine-local? It is machine-specific.
- **`lookup_one()` duplication.** `isbndb_search.py`, `isbndb_query.py` and `isbndb_lookup.py` each carry their own POST-with-429-retry copy of the request. `fetch_by_isbn13()` in `isbndb_utils.py` (2026-11-26) is the shared version for a bulk POST; `lookup_batch()` could use it (it would have to handle the exception, where it returns "not found" rows today) and drop its own `BATCH_SIZE`.
- **Status vocabulary.** Write down what the `revision_source` and status values mean and which scripts set them (`isbndb`, `not_in_isbndb`, `needs_manual_edit`, `needs_further_search`, `search_done`, `missing_fixed`, ...). Explained so far by how the counts arise (2,723 ISBNdb books, 67 ISBN not found, 5 with ISBN and own cover but manual bibliographic data, 133 without ISBN or title); 43 `missing_fixed` rows are still unexplained.
- **`COVER_PLACEHOLDER` heuristic.** _Needs investigation._ `select_best()` in `isbndb_utils.py` assumes ISBNdb marks a missing cover with one specific placeholder image. Real use suggests it doesn't do so reliably; the check may need a different signal, or a year match could always win.

---

## Pending -- schema and ids

- **`stable_book_id`.** `book_id` changes with every bootstrap and re-import, so nothing outside the database can refer to a book by it. A second id in the style of `pdf_id` -- author(s) + year + a letter if needed, e.g. `(Haas 2006a)` -- minted once, stored in `book`, carried in the snapshot and the import vocabulary. It can change in rare cases; then a file named after it (e.g. a synopsis) is renamed by hand. Not needed for synopses after all: they are keyed by `isbn13`. Still the way to refer to a book from outside the database, e.g. for books without an ISBN. _Needs investigation:_ books without author or year.
- **`book_revision.source` vs `revision_source`.** The column is called `source` in the table and `revision_source` in the view and the import vocabulary. Renaming the column changes the schema; do it together with `stable_book_id`, if at all.

---

## Pending -- later crossings (dialog-driven; their own sessions)

- **Crossing 3 -- cover management:** dialog *and* batch; the cover workflow. The part my wife enjoys most.
- **Crossing 4 -- bib editing:** a dialog that writes second and later `book_revision` rows. The only path that versions bibliographic data.

---

## Open questions

- **`book_status` vocabulary:** open `TEXT` (e.g. `needs_data / needs_cover / ready`); a `CHECK` could follow once it settles through use.
- **`cover_status` vocabulary:** open `TEXT` (`beautiful / from_thalia / wrong / missing / missing_fixed / ...`); `'unreviewed'` when nothing is supplied.
- **`cover_ref` paths:** relative or absolute file paths, and how a URL maps to a downloaded file -- today the rule lives in `cover_download.py` and in haddoapp's `export_books.py` (README section 5.5).
- **Deleting a cover:** `ON DELETE SET NULL` clears `preferred_cover_id`; should the next cover become preferred automatically? (crossing 3)
- **`book_current` columns:** the view does not show `created_at`, `preferred_cover_id` or `cover_id`. Cover management (crossing 3) will probably need some of them.
- **Whole-block import checks:** a missing required column, a duplicate header, a block with headers but no rows -- none of these is checked as such today.
- **PyXLL integration tests:** the pure-Python suite runs in the VM via `make test`; whether and how to test the PyXLL layer itself is open.
- **Photo file names as keys:** `rack_01 2026-02-16 21.29.43.jpg` is how a photo book is found again on import; is that name stable and unique enough?

---

## Parked / Later

- **Tag pruning** -- `haddo_prune_tags()` removes tags no book uses, called from VBA with a confirm dialog. Low urgency: unused tags show up in `haddo_tag_stats()` with count 0.
- **Named handles** -- handles are random tokens today, which suits VBA subs. Readable names (`SHELF-01`, ...) only if handles are ever reused from sheet formulas.
- **`.pre-commit-config.yaml`** -- Black and basic linting hooks, at a natural pause.
- **Tests for `extract_dimensions` / `extract_record`.** `select_best`, `extract_year` and `select_best_matching_year` are covered in `test_isbndb_utils.py`; `extract_dimensions` and `extract_record` are not.
- **Authors separator.** `extract_record` joins ISBNdb's author list with `,`. A `/` would read better next to "Last, First" names; it only affects the CSV and the sheet, not the database.
- **Anthropic SDK** -- add to `requirements.txt` if a Claude API fallback for photo analysis comes.
