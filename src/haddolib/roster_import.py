#!/usr/bin/env python3
"""
roster_import.py — Writing a roster row into the prototype database.

roster.py (pure) decides what a row MEANS; this module WRITES it. Still no pyxll
— plain sqlite3, testable on macOS through the proto_db fixture.

Scope — the FIRST bridge crossing, IMPORT, is INSERT-ONLY. A row is either
inserted as a new book or declined as a duplicate by the batch driver; import
never updates an existing book. Managing tags, covers, and bibliography are
separate, later, dialog-driven bridge crossings — none of their machinery lives
here.

This slice is the per-row INSERT (insert_book_row). The batch driver — dedup
pre-load, decline/insert loop, per-row commit, summary — is the next slice and
lives alongside this once built.
"""

from dataclasses import dataclass, field

from haddolib.common import as_int, as_real, as_text, is_valid_isbn13
from haddolib.roster import FIELD_MAP, ParsedRow, map_row, unknown_headers

# Revision keys that are metadata, not bibliography. Their presence alone does
# NOT justify writing a book_revision row — a not-found book may carry a bare
# source with every real field blank, and should stay revisionless (it then
# shows "bare" through book_current's LEFT JOIN, which is the point).
_REVISION_NON_BIB = frozenset({"source", "revision_comment"})


def _has_bibliographic_data(revision: dict) -> bool:
    """True if the revision bucket carries real bibliography.

    Value-based, not key-based: a revision of {source: 'isbndb', title: None,
    authors: None} (a not-found ISBN book whose sheet happened to include the
    empty columns) is NOT bibliographic data and writes no revision. At least one
    non-source/revision_comment field must hold an actual (non-NULL) value.
    """
    return any(
        key not in _REVISION_NON_BIB and value is not None
        for key, value in revision.items()
    )


def _resolve_tags(conn, names) -> list[int]:
    """Resolve tag names to ids, auto-adding unknown tags. Case-insensitive.

    Matching uses COLLATE NOCASE (the tag table's unique index), so 'Fiction' and
    'fiction' resolve to one tag and the first spelling seen is the one stored.
    De-duplicates by resolved tag_id, so a row listing the same tag twice (in any
    case) yields one book_tag link rather than a primary-key clash.
    """
    ids: list[int] = []
    for name in names:
        row = conn.execute(
            "SELECT tag_id FROM tag WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row is None:
            tag_id = conn.execute(
                "INSERT INTO tag (name) VALUES (?)", (name,)
            ).lastrowid
        else:
            tag_id = row["tag_id"]
        if tag_id not in ids:
            ids.append(tag_id)
    return ids


def insert_book_row(conn, parsed: ParsedRow, created_at: str) -> int:
    """Insert ONE new book and its satellites; return the new book_id.

    Writes, in this order (the order matters for the circular FK — book first
    with preferred_cover_id NULL, then the cover, then point the book at it):

      • book          — always (identity + inline location + book_status + book_note).
      • book_revision — only if there is real bibliographic data; a source is
                        then required (raises ValueError if bib data is present
                        without one — that's a roster-setup error, surfaced loud).
      • cover         — only if a cover_ref is present. The first cover becomes the
                        book's preferred_cover_id (auto-promote). cover_source /
                        cover_status are written only when supplied, so a blank
                        cover_status falls through to the schema default ('unreviewed').
      • book_tag      — one link per resolved tag (unknown tags auto-added).

    Does NOT commit and does NOT check for duplicates — the batch driver owns
    dedup and the per-row commit. created_at is supplied by the caller so a whole
    import run shares one timestamp.
    """
    book = parsed.book
    cur = conn.execute(
        """
        INSERT INTO book (isbn13, book_note, book_status, room, space_label, bin_label,
                          position, preferred_cover_id, created_at)
        VALUES (:isbn13, :book_note, :book_status, :room, :space_label, :bin_label,
                :position, NULL, :created_at)
        """,
        {
            "isbn13":      book.get("isbn13"),
            "book_note":   book.get("book_note"),
            "book_status": book.get("book_status"),
            "room":        book.get("room"),
            "space_label": book.get("space_label"),
            "bin_label":   book.get("bin_label"),
            "position":    book.get("position"),
            "created_at":  created_at,
        },
    )
    book_id = cur.lastrowid

    # book_revision — only when there's real bibliography to record.
    revision = parsed.revision
    if _has_bibliographic_data(revision):
        source = revision.get("source")
        if source is None:
            raise ValueError(
                f"book_id {book_id}: bibliographic data present but no "
                f"revision_source — cannot write a revision"
            )
        cols = ["book_id", "source", "created_at"]
        vals = {"book_id": book_id, "source": source, "created_at": created_at}
        for key, value in revision.items():
            if key == "source":
                continue
            cols.append(key)
            vals[key] = value
        placeholders = ", ".join(f":{col}" for col in cols)
        conn.execute(
            f"INSERT INTO book_revision ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )

    # cover — only when there's a cover_ref; first cover becomes preferred.
    cover = parsed.cover
    cover_ref = cover.get("cover_ref")
    if cover_ref is not None:
        cols = ["book_id", "cover_ref", "created_at"]
        vals = {"book_id": book_id, "cover_ref": cover_ref, "created_at": created_at}
        if cover.get("cover_source") is not None:
            cols.append("cover_source")
            vals["cover_source"] = cover["cover_source"]
        if cover.get("cover_status") is not None:        # else schema default applies
            cols.append("cover_status")
            vals["cover_status"] = cover["cover_status"]
        placeholders = ", ".join(f":{col}" for col in cols)
        cur = conn.execute(
            f"INSERT INTO cover ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        cover_id = cur.lastrowid
        conn.execute(
            "UPDATE book SET preferred_cover_id = ? WHERE book_id = ?",
            (cover_id, book_id),
        )

    # tags — resolve (auto-add unknown), then link.
    for tag_id in _resolve_tags(conn, parsed.tags):
        conn.execute(
            "INSERT INTO book_tag (book_id, tag_id) VALUES (?, ?)",
            (book_id, tag_id),
        )

    return book_id


# ---------------------------------------------------------------------------
# Per-row field validators — pure, raw-value checks the driver runs around the
# identity decision. The pattern: a small (raw_row) -> (reason_code, detail) |
# None function, first hit rejects. reason_code is the stable, greppable token
# (column A of the rejected file); detail is free text naming the offending cell
# (column B) so the fix-loop knows *which* cell to touch.
#
# Two slots, by necessity not taste:
#   • BEFORE map_row — checks that must pre-empt map_row's eager coercion (a
#     non-numeric cell would crash as_real OUTSIDE the per-row try/except).
#     _check_numeric_types lives here.
#   • AFTER the identity decision — checks free of that constraint, placed late
#     so a row's identity reason (duplicate / no-key / invalid-ISBN) wins and
#     these checks only reach a row that would otherwise insert.
#     _check_status_blank and _check_incomplete_location live here.
# Adding the next hardening check (see TODO.md) is one function here and one
# branch in the right slot — not growing an if-wall in-line.
# ---------------------------------------------------------------------------

# Headers whose value must be a native number (or blank). Derived from FIELD_MAP
# so a newly-added numeric column is covered automatically, with no second list
# to keep in sync. (FIELD_MAP stores the very as_int/as_real functions imported
# from common, so identity comparison is exact.)
_NUMERIC_HEADERS = frozenset(
    header for header, (_bucket, _column, coerce) in FIELD_MAP.items()
    if coerce in (as_int, as_real)
)


def _check_numeric_types(raw_row: dict) -> tuple[str, str] | None:
    """Reject a row whose numeric column holds a non-blank STRING (raw value).

    A genuine Excel number reaches Python as int/float (German Excel only
    *displays* 21.59 as "21,59"; the stored value is the float). A *text* cell
    reaches it as str — and is wrong regardless of whether it would parse: both a
    German-comma "21,59" (which as_real would crash on) and a dotted "21.59"
    (which as_real would silently accept) are caught here as one stable reason.

    Blank is fine: None or "" (or whitespace-only) becomes NULL downstream, never
    a reject — empty dimension cells are the common case in real data.

    Runs on the RAW row, BEFORE map_row, so a bad cell is declined cleanly and
    never reaches map_row's eager coercion (which is not inside the per-row
    try/except and would otherwise abort the whole run on a German comma).

    Returns (reason_code, detail) on a hit — the detail names the offending cell,
    e.g. "height_cm = '21,59' is not a number" — or None when the row is clean.
    """
    for header, value in raw_row.items():
        key = (header or "").strip()
        if key not in _NUMERIC_HEADERS:
            continue
        if isinstance(value, str) and value.strip():
            return "non_numeric_value", f"{key} = '{value}' is not a number"
    return None


def _check_status_blank(raw_row: dict) -> tuple[str, str] | None:
    """Reject a row whose PRESENT book_status cell is blank — status is required.

    Semantics A: this guards a book_status column that is actually present. A sheet
    that omits book_status entirely is a separate, header-level concern (see
    TODO.md: 'required status column') and is NOT caught here. When the column is
    present, a blank cell (None / "" / whitespace — folded to None by as_text) is
    a hard reject, not a NULL: book_status is the pile-shrinking workflow field, so
    an unset value is a roster gap to fix, not a default to accept.

    The check reads HEADER PRESENCE in the raw row, not the mapped value: an
    absent column and a blank cell both map to None, so only the raw header tells
    "column missing" (semantics B, not ours) apart from "column present, blank".

    Unlike _check_numeric_types this need not precede map_row (it cannot crash
    coercion), so the driver calls it LATE — after the identity decision — so a
    duplicate / no-key / invalid-ISBN row reports its own reason first.

    Returns (reason_code, detail) on a hit, else None.
    """
    for header, value in raw_row.items():
        if (header or "").strip() != "book_status":
            continue
        if as_text(value) is None:
            return "status_blank", "book_status is required and was left blank"
    return None


def _check_incomplete_location(parsed: ParsedRow) -> tuple[str, str] | None:
    """Reject a row whose location hierarchy is PARTIAL (a child without parent).

    The chain is room > space_label > bin_label. Two rules, innermost first
    (first hit wins):
      • bin_label present but space_label absent → a bin with no space.
      • space_label present but room absent       → a space with no room.

    Reads the MAPPED book bucket, not the raw row: a parent that is blank and a
    parent whose column is simply absent both read as None, and either orphans
    the present child — a hierarchy is broken regardless of WHY the parent is
    missing. This is a deliberate asymmetry with _check_status_blank, where
    column presence was the opt-in signal to a required-field gate; here there is
    no opt-in, only structure.

    A FULLY-blank location (all three absent) is fine: "elsewhere in the house"
    books carry no shelf location and pass untouched — only a PARTIAL hierarchy
    rejects. `position` is intentionally NOT guarded (a space may have no bins,
    so a position could legitimately order within a space; see TODO.md).

    Returns (reason_code, detail) on a hit, else None.
    """
    book = parsed.book
    room = book.get("room")
    space = book.get("space_label")
    bin_label = book.get("bin_label")

    if bin_label is not None and space is None:
        return ("incomplete_location",
                f"bin_label = '{bin_label}' present but space_label is blank")
    if space is not None and room is None:
        return ("incomplete_location",
                f"space_label = '{space}' present but room is blank")
    return None


# ---------------------------------------------------------------------------
# The batch driver (2d) — the FIRST bridge crossing: import, insert-only.
# ---------------------------------------------------------------------------

@dataclass
class ImportSummary:
    """The outcome of one import run, for the bridge's MessageBox and for tests.

    Every data row ends up in exactly one bucket: inserted, declined (for a known
    reason), or errored (it raised while being written). declined/total are
    derived so they can't drift from the parts.

    rejected_rows captures every row that did NOT insert, as a (reason, detail,
    raw values) triple in sheet order:
      • reason — the stable, greppable token for a clean decline
        ('non_numeric_value', 'invalid_isbn13', …); for an errored row it is the
        exception MESSAGE (the actionable thing to fix at the workbench).
      • detail — free text naming the offending cell for a FIELD-level check
        ("height_cm = '21,59' is not a number"); empty "" for identity checks and
        errors, where the reason alone says enough.
      • raw values — the row's values verbatim, as received (a blank stays blank,
        uncoerced), so the bridgehead can write them back out unchanged for
        fix-and-re-import.
    This record is values-only on purpose: the column HEADERS live one layer up,
    at the bridgehead that holds them, which zips them against these values (with
    reason + detail prepended) to build the rejected-rows file.

    Invariant: len(rejected_rows) == declined + len(errors).
    """
    inserted: int = 0
    duplicate_isbn13: int = 0
    invalid_isbn13: int = 0
    non_numeric_value: int = 0
    status_blank: int = 0
    incomplete_location: int = 0
    duplicate_photo: int = 0
    no_key: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)   # (1-based data row, message)
    unknown_headers: list[str] = field(default_factory=list)
    rejected_rows: list[tuple[str, str, tuple]] = field(default_factory=list)  # (reason, detail, raw values), sheet order

    @property
    def declined(self) -> int:
        return (self.duplicate_isbn13 + self.invalid_isbn13 + self.non_numeric_value
                + self.status_blank + self.incomplete_location
                + self.duplicate_photo + self.no_key)

    @property
    def total(self) -> int:
        return self.inserted + self.declined + len(self.errors)

    def summary_line(self) -> str:
        """One-line human summary (the bridge shows this in a MessageBox)."""
        line = (f"{self.inserted} inserted, {self.declined} declined "
                f"({self.duplicate_isbn13} dup ISBN, {self.invalid_isbn13} invalid ISBN, "
                f"{self.non_numeric_value} non-numeric, "
                f"{self.status_blank} blank status, "
                f"{self.incomplete_location} partial location, "
                f"{self.duplicate_photo} dup photo, "
                f"{self.no_key} no-key)")
        if self.errors:
            line += f", {len(self.errors)} error(s)"
        if self.unknown_headers:
            line += f"; ignored columns: {', '.join(self.unknown_headers)}"
        return line


def _load_dedup_keys(conn) -> tuple[set, set]:
    """Pre-load the two dedup key sets once (not per row).

    existing_isbn13    — every non-NULL book.isbn13.
    existing_photo_ref — cover.cover_ref of covers on books that have NO isbn13,
        i.e. PHOTO books only. API placeholder URLs ride on ISBN books, which are
        excluded by the WHERE, so a shared 'missing cover' URL can never poison
        the photo-dedup set.
    """
    existing_isbn13 = {
        r[0] for r in conn.execute(
            "SELECT isbn13 FROM book WHERE isbn13 IS NOT NULL")
    }
    existing_photo_ref = {
        r[0] for r in conn.execute(
            "SELECT cov.cover_ref FROM cover cov "
            "JOIN book b ON b.book_id = cov.book_id "
            "WHERE b.isbn13 IS NULL")
    }
    return existing_isbn13, existing_photo_ref


def import_roster(conn, headers, rows, created_at: str) -> ImportSummary:
    """Import a roster sheet: one row per physical book, INSERT-ONLY.

    headers — the sheet's header row (column ORDER is free; the STRING maps).
    rows    — an iterable of value sequences, one per book (no header row).
    created_at — one timestamp for the whole run, supplied by the caller (the
                 bridge); relayed unchanged to every insert.

    Per row, the numeric field check runs FIRST — before map_row's eager
    coercion, which a non-numeric cell would crash. Survivors are mapped, then
    the dedup decision is STAGGERED on isbn13-presence:
      • has isbn13   → duplicate iff that isbn13 already exists (cover_ref is irrelevant);
      • no isbn13    → duplicate iff that cover_ref already exists; and a row with
                       neither isbn13 nor cover_ref has no identity key → declined.
    Once identity is settled, LATE content checks run (status_blank, then
    incomplete_location): placed here so an identity reason wins for a row that is
    also blank-on-status or partial-on-location, and so such a row is rejected
    BEFORE its key joins the dedup set (it must never shadow a later, valid row
    carrying the same isbn13).
    Newly-inserted keys are added to the in-memory sets, so duplicates WITHIN the
    same batch are caught too. Each successful insert is committed on its own; a
    row that raises is rolled back and recorded as an error, so one bad row never
    aborts the run.

    Every row that does NOT insert is also appended to summary.rejected_rows as
    (reason, detail, raw values) — the durable source for the rejected-rows file
    the bridge writes (see ImportSummary).
    """
    summary = ImportSummary(unknown_headers=unknown_headers(headers))
    existing_isbn13, existing_photo_ref = _load_dedup_keys(conn)

    for index, values in enumerate(rows, start=1):
        raw_row = dict(zip(headers, values))

        # --- BEFORE-slot field check: must pre-empt map_row's eager coercion ---
        numeric = _check_numeric_types(raw_row)
        if numeric is not None:
            reason, detail = numeric
            summary.non_numeric_value += 1
            summary.rejected_rows.append((reason, detail, tuple(values)))
            continue

        parsed = map_row(raw_row)
        isbn13 = parsed.book.get("isbn13")
        cover_ref = parsed.cover.get("cover_ref")

        # --- staggered dedup decision ---
        if isbn13 is not None:
            if not is_valid_isbn13(isbn13):
                summary.invalid_isbn13 += 1
                summary.rejected_rows.append(("invalid_isbn13", "", tuple(values)))
                continue
            if isbn13 in existing_isbn13:
                summary.duplicate_isbn13 += 1
                summary.rejected_rows.append(("duplicate_isbn13", "", tuple(values)))
                continue
            new_key = ("isbn13", isbn13)
        else:
            if cover_ref is None:
                summary.no_key += 1
                summary.rejected_rows.append(("no_key", "", tuple(values)))
                continue
            if cover_ref in existing_photo_ref:
                summary.duplicate_photo += 1
                summary.rejected_rows.append(("duplicate_photo", "", tuple(values)))
                continue
            new_key = ("cover_ref", cover_ref)

        # --- required-field check (LATE) ---
        blank = _check_status_blank(raw_row)
        if blank is not None:
            reason, detail = blank
            summary.status_blank += 1
            summary.rejected_rows.append((reason, detail, tuple(values)))
            continue

        location = _check_incomplete_location(parsed)
        if location is not None:
            reason, detail = location
            summary.incomplete_location += 1
            summary.rejected_rows.append((reason, detail, tuple(values)))
            continue

        # --- insert (isolated: a bad row is recorded, not fatal) ---
        try:
            insert_book_row(conn, parsed, created_at)
            conn.commit()
        except Exception as exc:        # noqa: BLE001 — per-row isolation is the point
            conn.rollback()
            summary.errors.append((index, str(exc)))
            summary.rejected_rows.append((str(exc), "", tuple(values)))
            continue

        # commit succeeded → the key is now real; guard the rest of the batch.
        if new_key[0] == "isbn13":
            existing_isbn13.add(new_key[1])
        else:
            existing_photo_ref.add(new_key[1])
        summary.inserted += 1

    return summary
