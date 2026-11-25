#!/usr/bin/env python3
"""
roster.py — Roster-sheet import: turn one physical-book row into the database.

The roster sheet (in racks.xlsm) is ONE ROW PER PHYSICAL BOOK. Each row carries
the book's identity (isbn13, or blank for a photo book), its inline location, the
ISBNdb metadata XLOOKUP'd in beside it, an optional cover ref, and a
comma-delimited tag list. Excel does the lookups; Python just writes the
prototype database (book / book_revision / cover / tag / book_tag).

This module is the PURE mapping layer: no database, no pyxll, importable and
testable anywhere (including macOS). It answers one question per row — "what does
this row mean, as book / revision / cover / tags?" — and nothing else. The
DB-writing layers (insert, update, the import driver) and the PyXLL COM bridge
build on top of it.

Header vocabulary — column ORDER is free; the header STRING is what maps:
  • All columns use unique, unambiguous names (no dot-qualified names needed).
  • A column with a blank / missing header is a deliberately-empty column: skipped.
  • An unrecognized non-blank header is reported by unknown_headers() — never fatal.
  • A blank CELL in a recognized column becomes NULL (Excel UDFs return "" rather
    than an empty cell, so "" -> NULL; see as_text/as_int/as_real in common.py).

NB on validation: this layer does NOT validate (isbn13 length/checksum, required
location, etc.). It maps. Validation lives in the import DRIVER (roster_import.py
import_roster) — e.g. is_valid_isbn13 declines a bad checksum as invalid_isbn13,
before dedup — so every decline lands in one unified ImportSummary. The bridgehead
stays thin (strip a leading decline_reason column, split header from rows, hand
off). The schema's own CHECK/NOT NULL constraints are the backstop.
"""

from dataclasses import dataclass, field

from haddolib.common import as_int, as_real, as_text

# Which table a column belongs to.
BOOK = "book"
REVISION = "revision"
COVER = "cover"

# The one header handled specially (comma-split into a list, not a column).
TAGS_HEADER = "tags"

# canonical header  ->  (bucket, column, coerce)
FIELD_MAP = {
    # ── book ──────────────────────────────────────────────────────────────────
    "isbn13":            (BOOK,     "isbn13",           as_text),
    "room":              (BOOK,     "room",             as_text),
    "space_label":       (BOOK,     "space_label",      as_text),
    "bin_label":         (BOOK,     "bin_label",        as_text),
    "position":          (BOOK,     "position",         as_real),
    "book_status":       (BOOK,     "book_status",      as_text),
    "book_note":         (BOOK,     "book_note",        as_text),
    # ── book_revision ─────────────────────────────────────────────────────────
    "revision_source":   (REVISION, "source",           as_text),
    "revision_comment":  (REVISION, "revision_comment", as_text),
    "title":             (REVISION, "title",            as_text),
    "title_long":        (REVISION, "title_long",       as_text),
    "subtitle":          (REVISION, "subtitle",         as_text),
    "authors":           (REVISION, "authors",          as_text),
    "publisher":         (REVISION, "publisher",        as_text),
    "date_published":    (REVISION, "date_published",   as_text),
    "edition":           (REVISION, "edition",          as_text),
    "pages":             (REVISION, "pages",            as_int),
    "binding":           (REVISION, "binding",          as_text),
    "language":          (REVISION, "language",         as_text),
    "dimensions":        (REVISION, "dimensions",       as_text),
    "height_cm":         (REVISION, "height_cm",        as_real),
    "length_cm":         (REVISION, "length_cm",        as_real),
    "width_cm":          (REVISION, "width_cm",         as_real),
    "weight_kg":         (REVISION, "weight_kg",        as_real),
    "subjects":          (REVISION, "subjects",         as_text),
    "dewey_decimal":     (REVISION, "dewey_decimal",    as_text),
    "isbn10":            (REVISION, "isbn10",           as_text),
    # ── cover ─────────────────────────────────────────────────────────────────
    "cover_ref":         (COVER,    "cover_ref",        as_text),
    "cover_source":      (COVER,    "cover_source",     as_text),
    "cover_status":      (COVER,    "cover_status",     as_text),
    # "tags" is handled specially in map_row (comma-split into ParsedRow.tags).
}


@dataclass
class ParsedRow:
    """One roster row, sorted into the buckets the DB layer will write.

    book / revision / cover are each {column: value} dicts containing ONLY the
    columns that were present (recognized, non-blank header) in the row. An
    absent column is simply not a key — so the DB layer can distinguish "not
    supplied" from "supplied as NULL" should it ever need to. tags is the parsed,
    de-duplicated, order-preserving tag list (possibly empty).
    """
    book: dict = field(default_factory=dict)
    revision: dict = field(default_factory=dict)
    cover: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


def split_tags(value) -> list[str]:
    """Comma-delimited tag string -> clean list.

    Blank/None -> []. Whitespace is trimmed per tag, empty tags dropped,
    duplicates removed while preserving first-seen order.
    """
    s = as_text(value)
    if s is None:
        return []
    ordered = {}                          # dict preserves insertion order, de-dups
    for part in s.split(","):
        name = part.strip()
        if name:
            ordered.setdefault(name, None)
    return list(ordered)


def map_row(row: dict) -> ParsedRow:
    """Sort one {header: value} row into a ParsedRow. Pure; no database.

    Blank-header keys are skipped (deliberately-empty columns). Unrecognized
    non-blank headers are ignored here and audited once, at the header level, by
    unknown_headers(). A blank cell in a recognized column becomes NULL.
    """
    parsed = ParsedRow()
    targets = {BOOK: parsed.book, REVISION: parsed.revision, COVER: parsed.cover}
    for header, value in row.items():
        key = (header or "").strip()
        if not key:
            continue                      # deliberately-empty column
        if key == TAGS_HEADER:
            parsed.tags = split_tags(value)
            continue
        spec = FIELD_MAP.get(key)
        if spec is None:
            continue                      # unrecognized header — see unknown_headers()
        bucket, column, coerce = spec
        targets[bucket][column] = coerce(value)
    return parsed


def unknown_headers(headers) -> list[str]:
    """Non-blank header strings that map to nothing — reported, never fatal.

    A property of the HEADER ROW (compute once in the import driver), not of each
    row. Blank/missing headers are NOT unknown — they are deliberately-empty
    columns. Order-preserving and de-duplicated.
    """
    known = set(FIELD_MAP) | {TAGS_HEADER}
    out = []
    for header in headers:
        key = (header or "").strip()
        if key and key not in known and key not in out:
            out.append(key)
    return out
