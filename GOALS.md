# haddolib -- Goals and Roadmap

(Note: "I" in the following paragraphs refer to the user, "you" to you as the AI model.)

**Charter:** This file answers: where is the project going, in what order, and what happens next. It holds the strategic vision, the phased roadmap, and goals that need a strategy discussion before they are actionable. The _Current Session Pointer_ below is the single canonical "where we are / what's next" -- keep it to a few lines, update it, don't grow it; `FIRST_PROMPT.md` sends the reader here first. Concrete, startable work lives in `TODO.md`; the resolved-work record lives in `HISTORY.md` (on the heap, out of the per-session dump); architecture and contract live in `README.md`.

---


## 📍 Current Session Pointer

**Where we are:** Documentation streamlined. `README.md` revamped into the orientation /
architecture / contract / settled-decisions spine -- the crystallisation point a new session
reads first. `HISTORY.md` split out to hold the resolved-work record. `TODO.md` slimmed to
forward-only.

**What's next:** The refactor pass:
0. Review `TODO`. Does it make sense to elevate other items than the following three from the backlog?
1. Flip `DEFAULT_SCHEMA` to the prototype DDL (confirm `bootstrap_db.py` passes it explicitly).
2. Extract `_SHELF_ORDER` in `query_core.py`.
3. `date_published` canonicalizer -- migrate Excel-side date-serial handling down into Python.

*Then, as their own steps:* dispatcher echo-test trim; umlaut-aware search; the `as_int` note.
Detail behind each lives in `TODO.md`.

---

## 🎯 Strategic vision

*(Full version in `README.md` §1–§2; the one-paragraph reminder here.)*

`haddolib` catalogues a shared library of ~3,200 books in the Magazin (plus ~400 elsewhere).
It is deliberately **not** a generic library-management system -- a tool for two people (≤5 with
close friends and family), and within that scope likely *more* tailored than any off-the-shelf
LMS. Two tracks run in parallel: a **physical track** (scanning and pre-curation in
`racks.xlsm`) and a **foundation track** (the SQLite
master record -- the focus of our working sessions). The longer-term goal is to use the
catalogue to gradually reorganise the Magazin so books that belong together migrate towards
each other, recreating the pleasure of browsing a well-organised bookshop.

The foundation track runs on the **prototype** architecture (the active one; the five-grain
"dream" is hibernated, with a non-destructive growth path back). Data reaches the DB through
four PyXLL crossings, only the first batch-driven: **import** (insert-only), **tag
management**, **cover management**, and **bib editing** (deferred). See `README.md` §3.

---

## Phase 1 -- Foundation + cataloguing (current)

**Foundation (working sessions):**

- [ ] **The refactor pass** -- schema-default flip, `_SHELF_ORDER`, the `date_published`
      canonicalizer, then the cleanup steps. See `TODO.md` → Active / Pending.
- [ ] **Cover management (crossing 3)** -- dialog *and* batch; the cover workflow.

**Physical track (Frank, ongoing):**

- [ ] **Scan the remainder** -- rack 15 (cookbooks); then ~400 books elsewhere in the house.
- [ ] **Excel workbench** -- master catalogue curated in `racks.xlsm` through the bulk phase.

*Pre-ISBN / no-barcode books are handled uniformly by the prototype: a `book` row with
`isbn13 = NULL`, location inline, the photo as an `own_photo` cover, and a provisional revision.
It shows in `book_current` like any other book from day one -- no special-casing.*

---

## Phase 2 -- Curation + the dream (future / hibernated)

*The dream schema is not abandoned -- each prototype omission has a documented, non-destructive
growth path (see `haddolib-design.md` on the heap).*

- [ ] **Bib editing (crossing 4)** -- the dialog that writes second+ `book_revision` rows.
- [ ] **Movement history** -- re-add a `location_event` table keyed on `book_id` when curation
      begins (with the corrected *checkout-is-not-a-move* semantics); the inline location
      columns migrate into a first event row.
- [ ] **The `copy` grain** -- re-add only when a second physical copy is formally admitted.
- [ ] **Streamlit app** -- a visual box-by-box browser with cover art and movement tracking.
- [ ] **Synopsis enrichment** -- a dedicated `synopsis` table (0..n per book, own source +
      quality status).
- [ ] **LibraryThing export** (optional) -- CSV with rack/box as tags; virtual ISBN13s minted
      lazily at export.
