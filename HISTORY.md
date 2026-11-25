# haddolib -- History

(Note: "I" in the following paragraphs refer to the user, "you" to you as the AI model.)

- The resolved-work record: what was built and when (note date, or have the points in roughly reverse-chronological order).
- This is the trophy case -- kept in the repo, **out of the per-session filesdump** (so it no longer rides along every session).
- For _forward_ work see `TODO.md`; for direction see `GOALS.md`; for the architecture as it stands see `README.md`.
- See "Workflow for the Whole Session (CRITICAL)" in `LLM_INSTRUCTIONS.md` for the interplay between `TODO.md` and this file.

---

- **2026-11-25:** One README tells the whole story: the +/- cycle in Excel, what haddoapp and `pdf-annotations` rely on, and what runs on the Mac and what in the VM. The design document has served its purpose.
- **2026-11-25:** haddolib and haddoapp, read together for the first time. haddolib moves into a fresh public repository, without the raw ISBN scans; the full history stays private in `haddolib-old`.
- **2026-11-25:** The dream retires, and the word "prototype" with it: the five tables and one view the library lives in are simply the schema now, `haddolib_default_schema.sql`.
- **2026-11-25:** "Dump" becomes "snapshot": `make snapshot` writes the whole library at one moment, the start of the next +/- cycle in `racks.xlsm`.
- **2026-11-22:** haddoapp begins: the library, read from a copy of this database, on its way to the iPhone. See haddoapp's `HISTORY.md`.
- **2026-11-21:** Coming back to haddolib. The next present is on its way: the app, for Christmas.
- **2026-07-28:** haddolib helps out a sibling: ISBNdb synopses for the PDF library of `pdf-annotations`, one text file per PDF, found by author and year.
- **2026-07-03:** My wife's birthday, and the present: the two of us in front of the big screen, our library in Excel, rack by rack, cover by cover.
- **2026-06-24:** Tags from Excel: add, change and count the tags of a book right on the shelf, written straight into the database.
- **2026-06-24:** The round trip: the whole library goes out to an xlsx that can be imported again (then called the dump, today the snapshot). Corrections are made in Excel, and the database is rebuilt from them. Every field name is unique, so both directions speak the same language.
- **2026-06-23:** All shelves up and running in Excel: the bookshelf shows a box with its covers, and one click moves to the next or previous box. And the database learns to find books by title, author and tags.
- **2026-06-21:** 2,933 books in the database. And the way back: Excel reads the books from the database, a box at a time.
- **2026-06-20:** The import learns to say no, kindly: every row that cannot go in lands in a rejected xlsx, with the reason and the cell that caused it, ready to fix and import again. ISBNs stay text all the way.
- **2026-06-17:** The bridge works: the first books travel from Excel through PyXLL into the real database.
- **2026-06-16:** Excel and Python shake hands: `hello_haddolib`, the first PyXLL function, answers from inside the workbook. The live database gets its bootstrap and its backup.
- **2026-06-15:** The pivot: instead of the dream, five tables and one view, small enough to be ready for the birthday. Not wrong, just too early, so the dream waited. (This small schema was called "the prototype" until 2026-11-25.)
- **2026-06-13:** One project, two worlds: the same repository works on the Mac and in the Windows VM, with one `Makefile` for both.
- **2026-06-10:** The first SQL schema, the "dream": a rich model with editions, copies, spaces and a movement history, designed over the spring. It never held a real book; its design is kept in `haddolib-old`.
- **2026-03-29:** Racks 01 to 14 scanned.
- **2026-02-23:** The covers come home: every cover URL from ISBNdb downloaded into one folder, ready for Excel.
- **2026-02-22:** ISBNdb joins: in spot checks it finds almost all the books Open Library missed, with dimensions and cover URLs. And the first fight with German Excel, which turns ISBNs into numbers and publication dates into calendar dates.
- **2026-02-21:** For the books without a barcode: a local vision model reads title and author from a photo of the cover.
- **2026-02-20:** haddolib begins. Racks 01 to 06 are scanned already; Open Library looks up their ISBNs and finds about two in three.
- **2026-02-16:** Scanning starts with rack 01, days before the first line of code.
