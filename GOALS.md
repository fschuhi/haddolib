# haddolib -- Goals and Roadmap

(Note: "I" in the following paragraphs refer to the user, "you" to you as the AI model.)

**Charter:** This file answers: where is the project going, in what order, and what happens next. It holds the strategic vision, the phased roadmap, and goals that need a strategy discussion before they are actionable. The _Current Session Pointer_ below is the single canonical "where we are / what's next" -- keep it to a few lines, update it, don't grow it; `FIRST_PROMPT.md` sends the reader here first. Concrete, startable work lives in `TODO.md`; the resolved-work record lives in `HISTORY.md` (on the heap, out of the per-session dump); architecture and contracts live in `README.md`.

---

## 📍 Current Session Pointer

**Where we are:** Synopses are on disk (2026-11-26): 1,415 of the 2,723 ISBNdb books have one, saved verbatim in `data/synopses/<isbn13>.txt` by `make isbndb-synopsis-isbn13`. The data side is done; the empty rest is a gap at ISBNdb, worst for German books. `make bootstrap` now writes a snapshot before it deletes the database. haddoapp refreshes `books.json` reliably now. All tests green.

**What's next:** haddoapp first needs its other book-page fields; that decides the layout, and then the synopsis follows. Its plan is ready in `TODO.md` under _Synopses_. Other candidates: the small streamlining leftovers in `TODO.md`; cover management (crossing 3); or one of the three strategy topics below. haddoapp has its own pointer and a Christmas deadline.

---

## 📍 Current Session Pointer

**Where we are:** Streamlined, together with haddoapp (2026-11-25). One schema (`data/haddolib_default_schema.sql`); "dump" is now "snapshot"; the code is plain ASCII and named by the naming rules; `README.md` is the one orientation document, and `HISTORY.md` is a dated trophy case. The Excel import is checked live. All tests green.

**What's next:** Pick at session start. Candidates: the small streamlining leftovers in `TODO.md`; `stable_book_id`, which synopses in the app would need; cover management (crossing 3); or one of the two strategy topics below. haddoapp has its own pointer and a Christmas deadline.

---

## 🎯 Strategic vision

*(Full version in `README.md` sections 1-2; the one-paragraph reminder here.)*

`haddolib` catalogues a shared library of ~3,200 books in the Magazin (plus ~400 elsewhere). It is **not** a generic library-management system -- a tool for two people (at most five with close friends and family), and within that scope likely *more* tailored than any off-the-shelf system. Two tracks run in parallel: a **physical track** (scanning and pre-curation in `racks.xlsm`) and a **foundation track** (the SQLite master record -- the focus of our working sessions). The longer-term goal is to use the catalogue to gradually reorganise the Magazin so books that belong together move towards each other, recreating the pleasure of browsing a well-organised bookshop.

Data reaches the database through four PyXLL crossings, only the first batch-driven: **import** (insert-only), **tag management**, **cover management** and **bib editing**; the last two are not built yet. haddoapp shows the library on the iPhone, read from a copy of the database. See `README.md` sections 3-5.

---

## Needs a strategy discussion

- **Help with curation, without sharing the catalogue.** Which books we own says a lot about my wife and me, so the real data stays at home. Ways to still get help with the workbench, the data quality (wrong covers, author spellings, missing ISBNs) and some automation: a local model (Ollama already runs here), or a made-up look-alike workbook to show the workflow. An own conversation.
- **Who is the master: the sheets or the database?** Import is insert-only, so edits made only in the database (the tag dialog) are lost when it is wiped and re-imported. A forgotten `make snapshot` before `make bootstrap` lost six books' tags once; the bootstrap guard now takes the snapshot itself. The "checkpoint" idea: a snapshot sheet (`checkpoint 5`) with its own import range; rebuild from the newest checkpoint plus the +/- parts after it, the older parts are archive. Not settled: it replaces "the database can be rebuilt from the first import", and a snapshot sheet with an import button is a different thing from a +/- part. Related questions: an update-mode import (needs `stable_book_id`), a back-channel from haddoapp for tags, and where the database lives (today: the VM disk, with a manual copy to the Mac for haddoapp). A Postgres on the NAS would not have prevented the tag loss and means rewriting the database layer. An own conversation, together with "Mac first".
- **Mac first.** Move as much as possible from the Windows VM to the Mac (`README.md` section 6.1 lists what runs where). Today Excel, PyXLL and the live database need the VM. Longer term: is Excel still the right workbench? An own conversation.

---

## Phase 1 -- Foundation + cataloguing (current)

**Foundation (working sessions):**

- **Streamlining leftovers** -- the small items in `TODO.md`.
- **Cover management (crossing 3)** -- dialog *and* batch; the cover workflow.

**Physical track (Frank, ongoing):**

- **Scan the remainder** -- rack 15 (cookbooks); then ~400 books elsewhere in the house.
- **Excel workbench** -- the catalogue curated in `racks.xlsm`, in +/- cycles (`README.md` section 4).

*Books without an ISBN barcode are no special case: a `book` row with `isbn13 = NULL`, the location on the row, the photo as an `own_photo` cover, and a revision when there is bibliographic data. They show in `book_current` like any other book.*

---

## Phase 2 -- Curation (future)

- **Synopses in the app** -- one text file per book, keyed by `isbn13`, shown on haddoapp's book page (data side done, see the pointer; app side planned in `TODO.md`). Books without an ISBN get none until another source or `stable_book_id` helps.
- **Bib editing (crossing 4)** -- the dialog that writes second and later `book_revision` rows.
- **Movement history** -- once books start moving between boxes, record each move (a book taken to another room for reading is not a move). The location columns on `book` would become the first entry.
- **A second copy of a book** -- the schema has one row per physical book and `isbn13` is unique; a second physical copy with the same ISBN needs a change there.
- **LibraryThing export** (optional) -- CSV with rack/box as tags.
