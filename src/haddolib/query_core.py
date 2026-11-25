#!/usr/bin/env python3
"""
query_core.py -- The pure read layer for haddolib.

All queries read from `book_current` (the view), never the base tables.
No PyXLL, no Excel -- testable on macOS via the empty_db fixture.

Two kinds of public entry points:

  query(conn, name, *params) -- the scalar dispatcher used by haddo_query.
    Returns str | int. All named queries registered in _DISPATCH live here.

  books_by_bin(conn, room, space_label, bin_label) -- list-returning query by location.
  books_by_title(conn, search)               -- list-returning query by title.
  books_by_author(conn, search)              -- list-returning query by author.
  books_by_tags(conn, tags, match_all)       -- list-returning query by tags.
  all_books(conn)                            -- full catalogue, read by write_snapshot().

    All list-returning functions return list[dict]: one dict per book, all
    book_current columns plus a 'tags' key (comma-separated tag names, or
    None when the book has no tags). Called directly from pyxll_bridge.py --
    not via the dispatcher, as a different return type warrants a different
    call path.

Return types for query():
  - Scalar counts  -> int
  - Delimited lists -> str  (comma + space separated, e.g. "rack 01, rack 02")
  - Empty lists     -> ""   (not None -- a cell formula gets an empty string)

Room filter convention (queries 6-12):
  - room="" or room=None -> no filter, count across ALL rooms
  - room="Magazin"      -> WHERE room = 'Magazin'

Vocabulary queries (distinct_*):
  Return the set of values actually present in the database for a given
  field -- useful for building the param lists for the count queries above.
  No room filter: always the full vocabulary across all rooms.
"""

from __future__ import annotations

import sqlite3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _room_clause(room: str | None) -> tuple[str, list]:
    """Return (sql_fragment, params) for an optional room filter.

    An empty or None room means "all rooms" -- no WHERE clause on room.
    """
    if room:
        return "WHERE room = ?", [room]
    return "", []


def _join_room_clause(room: str | None, prefix: str = "WHERE") -> tuple[str, list]:
    """Like _room_clause but lets the caller specify the keyword (WHERE / AND)."""
    if room:
        return f"{prefix} room = ?", [room]
    return "", []


# The tags subquery is shared by all list-returning functions.
# The inner SELECT orders by t.name so GROUP_CONCAT always produces an
# alphabetically sorted, comma-separated tag string regardless of insertion order.
_TAGS_SUBQUERY = """(SELECT GROUP_CONCAT(name, ', ')
                     FROM (SELECT t.name
                           FROM book_tag AS bt
                           JOIN tag AS t ON t.tag_id = bt.tag_id
                           WHERE bt.book_id = b.book_id
                           ORDER BY t.name)) AS tags"""


# ---------------------------------------------------------------------------
# Location hierarchy (queries 1-5)
# ---------------------------------------------------------------------------

def rooms(conn: sqlite3.Connection) -> str:
    """Distinct room values, sorted, as a comma-separated string.

    Used to spot canonical-label anomalies (e.g. a stray 'Magazin ' with a
    trailing space, or a 'Wohnzimmer' that should be something else).
    Returns "" when no books have a room set.
    """
    rows = conn.execute(
        "SELECT DISTINCT room FROM book_current "
        "WHERE room IS NOT NULL ORDER BY room"
    ).fetchall()
    return ", ".join(r["room"] for r in rows)


def spaces(conn: sqlite3.Connection, room: str) -> str:
    """Distinct space_label values within a room, sorted.

    Raises ValueError if room is blank -- a blank room would silently return
    all spaces across all rooms, which is never what the caller wants here.
    Returns "" when no books have a space_label set in that room.
    """
    if not room:
        raise ValueError("spaces() requires a non-empty room")
    rows = conn.execute(
        "SELECT DISTINCT space_label FROM book_current "
        "WHERE room = ? AND space_label IS NOT NULL ORDER BY space_label",
        (room,),
    ).fetchall()
    return ", ".join(r["space_label"] for r in rows)


def bins(conn: sqlite3.Connection, room: str, space_label: str) -> str:
    """Distinct bin_label values within a room+space, sorted.

    Raises ValueError if either room or space_label is blank.
    Returns "" when no books have a bin_label set in that room/space.
    """
    if not room:
        raise ValueError("bins() requires a non-empty room")
    if not space_label:
        raise ValueError("bins() requires a non-empty space_label")
    rows = conn.execute(
        "SELECT DISTINCT bin_label FROM book_current "
        "WHERE room = ? AND space_label = ? AND bin_label IS NOT NULL "
        "ORDER BY bin_label",
        (room, space_label),
    ).fetchall()
    return ", ".join(r["bin_label"] for r in rows)


def space_count(conn: sqlite3.Connection, room: str) -> int:
    """Number of distinct space_labels in a room.

    Raises ValueError if room is blank.
    """
    if not room:
        raise ValueError("space_count() requires a non-empty room")
    row = conn.execute(
        "SELECT COUNT(DISTINCT space_label) AS n FROM book_current "
        "WHERE room = ? AND space_label IS NOT NULL",
        (room,),
    ).fetchone()
    return row["n"]


def location_combo_count(conn: sqlite3.Connection) -> int:
    """Number of distinct (room, space_label, bin_label) triples.

    This is the total number of populated boxes across all racks and rooms.
    Rows where any component is NULL are excluded -- a book with no location
    set does not constitute a box.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM ("
        "  SELECT DISTINCT room, space_label, bin_label FROM book_current "
        "  WHERE room IS NOT NULL AND space_label IS NOT NULL AND bin_label IS NOT NULL"
        ")"
    ).fetchone()
    return row["n"]


# ---------------------------------------------------------------------------
# Book counts (queries 6-12), all accept optional room filter
# ---------------------------------------------------------------------------

def book_count(conn: sqlite3.Connection, room: str = "") -> int:
    """Total number of books, optionally filtered to one room."""
    clause, params = _room_clause(room)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM book_current {clause}", params
    ).fetchone()
    return row["n"]


def book_count_with_bib(conn: sqlite3.Connection, room: str = "") -> int:
    """Books that have at least one book_revision (bibliographic data).

    Uses revision_source IS NOT NULL as the proxy -- book_current exposes
    it from the LEFT JOIN, so NULL means no revision exists yet.
    """
    clause, params = _room_clause(room)
    base = "WHERE revision_source IS NOT NULL"
    if clause:
        combined = f"{clause} AND revision_source IS NOT NULL"
    else:
        combined = base
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM book_current {combined}", params
    ).fetchone()
    return row["n"]


def book_count_photo_only(conn: sqlite3.Connection, room: str = "") -> int:
    """Books without an ISBN (own_photo books -- no bibliographic data yet).

    isbn13 IS NULL is the canonical signal: these are the ||PH|| books
    scanned with a photo rather than a barcode.
    """
    clause, params = _room_clause(room)
    base = "WHERE isbn13 IS NULL"
    if clause:
        combined = f"{clause} AND isbn13 IS NULL"
    else:
        combined = base
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM book_current {combined}", params
    ).fetchone()
    return row["n"]


def count_by_status(conn: sqlite3.Connection, status: str, room: str = "") -> int:
    """Books whose book_status matches the given value."""
    if not status:
        raise ValueError("count_by_status() requires a non-empty status")
    room_frag, room_params = _join_room_clause(room, "AND")
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM book_current WHERE book_status = ? {room_frag}",
        [status, *room_params],
    ).fetchone()
    return row["n"]


def count_by_revision_source(conn: sqlite3.Connection, source: str, room: str = "") -> int:
    """Books whose most recent revision_source matches the given value."""
    if not source:
        raise ValueError("count_by_revision_source() requires a non-empty source")
    room_frag, room_params = _join_room_clause(room, "AND")
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM book_current "
        f"WHERE revision_source = ? {room_frag}",
        [source, *room_params],
    ).fetchone()
    return row["n"]


def count_by_cover_source(conn: sqlite3.Connection, source: str, room: str = "") -> int:
    """Books whose preferred cover's cover_source matches the given value."""
    if not source:
        raise ValueError("count_by_cover_source() requires a non-empty source")
    room_frag, room_params = _join_room_clause(room, "AND")
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM book_current "
        f"WHERE cover_source = ? {room_frag}",
        [source, *room_params],
    ).fetchone()
    return row["n"]


def count_by_cover_status(conn: sqlite3.Connection, status: str, room: str = "") -> int:
    """Books whose preferred cover's cover_status matches the given value."""
    if not status:
        raise ValueError("count_by_cover_status() requires a non-empty status")
    room_frag, room_params = _join_room_clause(room, "AND")
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM book_current "
        f"WHERE cover_status = ? {room_frag}",
        [status, *room_params],
    ).fetchone()
    return row["n"]


# ---------------------------------------------------------------------------
# Vocabulary queries -- distinct values actually present in the database
# ---------------------------------------------------------------------------

def distinct_statuses(conn: sqlite3.Connection) -> str:
    """Distinct book_status values in use, sorted, comma-separated.

    Feed the result into count_by_status() to enumerate what's actually
    in the database without hard-coding the vocabulary.
    Returns "" when no books have a book_status set.
    """
    rows = conn.execute(
        "SELECT DISTINCT book_status FROM book_current "
        "WHERE book_status IS NOT NULL ORDER BY book_status"
    ).fetchall()
    return ", ".join(r["book_status"] for r in rows)


def distinct_revision_sources(conn: sqlite3.Connection) -> str:
    """Distinct revision_source values in use, sorted, comma-separated.

    Returns "" when no books have a revision source set.
    """
    rows = conn.execute(
        "SELECT DISTINCT revision_source FROM book_current "
        "WHERE revision_source IS NOT NULL ORDER BY revision_source"
    ).fetchall()
    return ", ".join(r["revision_source"] for r in rows)


def distinct_cover_sources(conn: sqlite3.Connection) -> str:
    """Distinct cover_source values in use (preferred cover only), sorted, comma-separated.

    Reads cover_source from book_current, which reflects the preferred cover.
    Returns "" when no books have a cover source set.
    """
    rows = conn.execute(
        "SELECT DISTINCT cover_source FROM book_current "
        "WHERE cover_source IS NOT NULL ORDER BY cover_source"
    ).fetchall()
    return ", ".join(r["cover_source"] for r in rows)


def distinct_cover_statuses(conn: sqlite3.Connection) -> str:
    """Distinct cover_status values in use (preferred cover only), sorted, comma-separated.

    Reads cover_status from book_current, which reflects the preferred cover.
    Returns "" when no books have a cover status set.
    """
    rows = conn.execute(
        "SELECT DISTINCT cover_status FROM book_current "
        "WHERE cover_status IS NOT NULL ORDER BY cover_status"
    ).fetchall()
    return ", ".join(r["cover_status"] for r in rows)


# ---------------------------------------------------------------------------
# List-returning queries -- return list[dict], not str | int
#
# All five functions return the same shape:
#   list[dict]  -- one dict per matched book, all book_current columns plus
#                 a 'tags' key (comma-separated tag names, alphabetically
#                 sorted, or None when the book has no tags).
#
# The ordering convention:
#   All five functions -> physical shelf order (room, space_label, bin_label, position)
#   This means a tags bookshelf or title/author search result reads in the same
#   sequence the books physically sit on the shelves.
# ---------------------------------------------------------------------------

def books_by_bin(
    conn: sqlite3.Connection,
    room: str,
    space_label: str,
    bin_label: str,
) -> list[dict]:
    """Return all books in one specific bin, ordered by physical position.

    Each element is a dict of all book_current columns plus a 'tags' key
    (comma-separated tag names in alphabetical order, or None when the book
    has no tags). The list preserves shelf order: room -> space_label ->
    bin_label -> position.

    Python dicts preserve insertion order (3.7+), so the order flows through
    to callers (VBA, tests) unchanged -- books come out in the sequence they
    physically sit in the box.

    All three location parameters are required and must be non-empty strings.
    An empty or blank parameter is never treated as a wildcard -- pass a genuine
    value or get a ValueError. This keeps the result set bounded: a bin holds
    tens of books, not thousands.

    Raises ValueError if any parameter is missing or blank.
    """
    if not room or not room.strip():
        raise ValueError("books_by_bin() requires a non-empty room")
    if not space_label or not space_label.strip():
        raise ValueError("books_by_bin() requires a non-empty space_label")
    if not bin_label or not bin_label.strip():
        raise ValueError("books_by_bin() requires a non-empty bin_label")

    rows = conn.execute(
        f"""
        SELECT b.*,
               {_TAGS_SUBQUERY}
        FROM book_current AS b
        WHERE b.room        = ?
          AND b.space_label = ?
          AND b.bin_label   = ?
        ORDER BY b.room, b.space_label, b.bin_label, b.position
        """,
        (room.strip(), space_label.strip(), bin_label.strip()),
    ).fetchall()

    return [dict(r) for r in rows]


def books_by_title(
    conn: sqlite3.Connection,
    search: str,
) -> list[dict]:
    """Return all books whose title contains the search string (case-insensitive).

    Matches against the `title` column of book_current (i.e. the most recent
    revision's title). The match is a substring match: "krieg" matches
    "Der Krieg der Welten". Returns an empty list when nothing matches.

    Raises ValueError if search is blank -- a blank string would match every
    book in the database, which is never useful and likely a caller error.
    """
    if not search or not search.strip():
        raise ValueError("books_by_title() requires a non-empty search string")

    rows = conn.execute(
        f"""
        SELECT b.*,
               {_TAGS_SUBQUERY}
        FROM book_current AS b
        WHERE lower(b.title) LIKE '%' || lower(?) || '%'
        ORDER BY b.room, b.space_label, b.bin_label, b.position
        """,
        (search.strip(),),
    ).fetchall()

    return [dict(r) for r in rows]


def books_by_author(
    conn: sqlite3.Connection,
    search: str,
) -> list[dict]:
    """Return all books whose authors field contains the search string (case-insensitive).

    Matches against the `authors` column of book_current (comma-delimited
    author string as stored from the API). The match is a substring match:
    "rowling" matches "J.K. Rowling". Returns an empty list when nothing matches.

    Raises ValueError if search is blank -- a blank string would match every
    book that has any author set, which is never useful and likely a caller error.
    """
    if not search or not search.strip():
        raise ValueError("books_by_author() requires a non-empty search string")

    rows = conn.execute(
        f"""
        SELECT b.*,
               {_TAGS_SUBQUERY}
        FROM book_current AS b
        WHERE lower(b.authors) LIKE '%' || lower(?) || '%'
        ORDER BY b.room, b.space_label, b.bin_label, b.position
        """,
        (search.strip(),),
    ).fetchall()

    return [dict(r) for r in rows]


def books_by_ids(
    conn: sqlite3.Connection,
    book_ids: list[int],
) -> list[dict]:
    """Return books for the given book_ids, in the same order as book_ids.

    Fetches all rows in a single IN query, then reorders to match the caller's
    sequence. This preserves the snapshot order when refreshing a handle --
    the display order stays identical to the original query.

    Each returned dict has all book_current columns plus a 'tags' key
    (comma-separated tag names in alphabetical order, or None when the book
    has no tags).

    Raises ValueError if book_ids is empty.
    """
    if not book_ids:
        raise ValueError("books_by_ids() requires at least one book_id")

    placeholders = ", ".join("?" * len(book_ids))
    rows = conn.execute(
        f"""
        SELECT b.*,
               {_TAGS_SUBQUERY}
        FROM book_current AS b
        WHERE b.book_id IN ({placeholders})
        """,
        book_ids,
    ).fetchall()

    # The IN query does not guarantee order -- restore the caller's sequence.
    by_id = {row["book_id"]: dict(row) for row in rows}
    return [by_id[bid] for bid in book_ids if bid in by_id]


def books_by_tags(
    conn: sqlite3.Connection,
    tags: list[str],
    match_all: bool,
) -> list[dict]:
    """Return books matching the given tags.

    tags        -- list of tag name strings (must be non-empty; duplicates are
                   removed before the query runs).
    match_all   -- True:  only books that carry ALL of the given tags (AND logic).
                   False: books that carry ANY of the given tags (OR logic).

    Each returned dict has all book_current columns plus a 'tags' key
    (all tags for that book, alphabetically sorted and comma-separated --
    not just the matched ones).
    Results are ordered by physical shelf position.

    Raises ValueError if tags is empty or contains only blank strings.

    Implementation note -- match_all uses relational division:
      HAVING COUNT(DISTINCT matched_tag_id) = N
    where N is the number of distinct tags passed. This is correct as long as
    all tag names in the input list are distinct (enforced here by dedup).
    """
    # Normalise: strip, drop blanks, deduplicate while preserving order.
    cleaned = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
    if not cleaned:
        raise ValueError("books_by_tags() requires at least one non-empty tag name")

    placeholders = ", ".join("?" * len(cleaned))

    if match_all:
        # Relational division: book must have ALL tags in the list.
        where = f"""b.book_id IN (
            SELECT bt.book_id
            FROM book_tag AS bt
            JOIN tag AS t ON t.tag_id = bt.tag_id
            WHERE t.name IN ({placeholders})
            GROUP BY bt.book_id
            HAVING COUNT(DISTINCT bt.tag_id) = ?
        )"""
        params: list = [*cleaned, len(cleaned)]
    else:
        # Any-match: book must have at least one tag in the list.
        where = f"""b.book_id IN (
            SELECT bt.book_id
            FROM book_tag AS bt
            JOIN tag AS t ON t.tag_id = bt.tag_id
            WHERE t.name IN ({placeholders})
        )"""
        params = [*cleaned]

    rows = conn.execute(
        f"""
        SELECT b.*,
               {_TAGS_SUBQUERY}
        FROM book_current AS b
        WHERE {where}
        ORDER BY b.room, b.space_label, b.bin_label, b.position
        """,
        params,
    ).fetchall()

    return [dict(r) for r in rows]


def all_books(conn: sqlite3.Connection) -> list[dict]:
    """Return all books, ordered by physical shelf position.

    Each element is a dict of all book_current columns plus a 'tags' key
    (comma-separated tag names in alphabetical order, or None when the book
    has no tags). Books with no location set sort last (NULLs sort after
    non-NULLs in SQLite's default ascending collation).

    This is the snapshot entry point -- it returns the full catalogue
    that write_snapshot() in snapshot_core.py maps to FIELD_MAP headers and writes
    as an xlsx. No WHERE clause is intentional: all_books() is a deliberate
    full-table scan.
    """
    rows = conn.execute(
        f"""
        SELECT b.*,
               {_TAGS_SUBQUERY}
        FROM book_current AS b
        ORDER BY b.room, b.space_label, b.bin_label, b.position
        """,
    ).fetchall()

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Tag statistics
# ---------------------------------------------------------------------------

def tag_stats(
    conn: sqlite3.Connection,
    order_by_count: bool = True,
) -> list[tuple[str, int]]:
    """Return all tags with their book counts, including orphans (count = 0).

    order_by_count=True  (default): ordered by use_count descending, then tag
                                    name ascending as a tiebreaker. Useful for
                                    curation -- most-used tags first.
    order_by_count=False:           ordered alphabetically by tag name. Useful
                                    as a combobox / constraint source where
                                    predictable position matters more than rank.

    Orphans (tags with no book_tag rows) appear with count 0 in both orderings --
    useful for spotting what a prune_tags run would remove, and for keeping
    reminder tags that haven't been applied yet.

    Returns an empty list when the tag table is empty.
    """
    order_clause = "use_count DESC, t.name ASC" if order_by_count else "t.name ASC"
    rows = conn.execute(
        f"""
        SELECT t.name, COUNT(bt.book_id) AS use_count
        FROM tag AS t
        LEFT JOIN book_tag AS bt ON bt.tag_id = t.tag_id
        GROUP BY t.tag_id, t.name
        ORDER BY {order_clause}
        """
    ).fetchall()
    return [(row["name"], row["use_count"]) for row in rows]


# ---------------------------------------------------------------------------
# Public dispatcher (scalar queries only -- list-returning functions are called
# directly from pyxll_bridge.py, not via this dispatcher)
# ---------------------------------------------------------------------------

# Maps query name -> (function, required_param_count, accepts_room_filter)
# required_param_count excludes the optional room parameter.
_DISPATCH: dict[str, tuple] = {
    "rooms":                    (rooms,                    0, False),
    "spaces":                   (spaces,                   1, False),
    "bins":                     (bins,                     2, False),
    "space_count":              (space_count,              1, False),
    "location_combo_count":     (location_combo_count,     0, False),
    "book_count":               (book_count,               0, True),
    "book_count_with_bib":      (book_count_with_bib,      0, True),
    "book_count_photo_only":    (book_count_photo_only,    0, True),
    "count_by_status":          (count_by_status,          1, True),
    "count_by_revision_source": (count_by_revision_source, 1, True),
    "count_by_cover_source":    (count_by_cover_source,    1, True),
    "count_by_cover_status":    (count_by_cover_status,    1, True),
    # Vocabulary queries
    "distinct_statuses":         (distinct_statuses,         0, False),
    "distinct_revision_sources": (distinct_revision_sources, 0, False),
    "distinct_cover_sources":    (distinct_cover_sources,    0, False),
    "distinct_cover_statuses":   (distinct_cover_statuses,   0, False),
}


def query(conn: sqlite3.Connection, name: str, *params: str) -> str | int:
    """Dispatch a named query and return its result.

    params are positional strings from the Excel cell formula, e.g.:
        query(conn, "spaces", "Magazin")
        query(conn, "book_count", "Magazin")
        query(conn, "count_by_status", "ready", "Magazin")
        query(conn, "rooms")

    For queries that accept a room filter (see _DISPATCH), the room is
    always the LAST parameter and is optional -- omit it (or pass "") for
    the all-rooms total.

    Raises ValueError for unknown query names or wrong parameter counts.
    """
    if name not in _DISPATCH:
        known = ", ".join(sorted(_DISPATCH))
        raise ValueError(f"unknown query {name!r}. Known queries: {known}")

    fn, required, accepts_room = _DISPATCH[name]
    params = list(params)

    if accepts_room:
        # The room is the last param and is optional.
        if len(params) == required:
            room = ""
        elif len(params) == required + 1:
            room = params.pop()
        else:
            raise ValueError(
                f"query {name!r} takes {required} required param(s) plus an "
                f"optional room, got {len(params)} param(s)"
            )
        return fn(conn, *params, room=room)
    else:
        if len(params) != required:
            raise ValueError(
                f"query {name!r} takes exactly {required} param(s), "
                f"got {len(params)}"
            )
        return fn(conn, *params)
