#!/usr/bin/env python3
"""
src/haddolib/pyxll_bridge.py -- PyXLL integration layer for haddolib.

The @xl_func / @xl_macro entry points that expose the Python backend to Excel
(the macros via VBA's Application.Run). These are THIN: marshalling and DB-
connection housekeeping only. All real work -- parse, import, rejected file,
summary packing, queries, handle state -- lives in bridge_core / query_core /
catalog, which are unit-tested on macOS WITHOUT PyXLL. This module can
therefore only be exercised in the Windows VM where PyXLL is installed.

Signature note (verified -- see signature research): @xl_macro takes an
ARGUMENT-ONLY signature string, "var[][] data". The xl_func-style ": <returntype>"
is invalid for a macro. The function still RETURNS its value; VBA receives it
through Application.Run (the scalar-string path of BRIDGE_CONTRACT.md section 4). That
return path -- not the worksheet-cell path -- is what carries the summary back.

Handle catalog:
  The module-level _CATALOG instance (HandleCatalog) manages opaque handle
  strings for VBA loops over list results. All state, locking, eviction, and
  diagnostics live in catalog.py (pure, tested on macOS). This module holds
  only the single instance and the thin @xl_func wrappers that marshal between
  Excel/VBA conventions and the catalog's Python API.

  Handle format:  haddo:{session_id}:{kind}:{16-byte hex token}
  The session_id (generated once per catalog instance) makes stale handles
  from a previous PyXLL reload immediately obvious.

  VBA contract:
    1. Call one of the haddo_books_by_* functions -> receive a handle string.
    2. Use haddo_len / haddo_get_field to read data.
    3. Always call haddo_release in an On Error GoTo Cleanup block.
    4. Call haddo_sweep_handles from Workbook_Open or a maintenance macro to
       evict any handles that leaked through a crash (default TTL: 600 s).

  Kind strings (embedded in handle, visible in haddo_handles diagnostic):
    "books_by_bin"    -- books_by_bin()    result
    "books_by_title"  -- books_by_title()  result
    "books_by_author" -- books_by_author() result
    "books_by_tags"   -- books_by_tags()   result

  haddo_len / haddo_get_field / haddo_release are kind-agnostic: any handle
  from any haddo_books_by_* function works. The kind is diagnostic only.
"""

from datetime import datetime
from pathlib import Path

from pyxll import xl_func, xl_macro

from haddolib.bridge_core import run_import
from haddolib.catalog import HandleCatalog
from haddolib.database import connect
from haddolib.query_core import (
    query,
    books_by_bin,
    books_by_title,
    books_by_author,
    books_by_tags,
    books_by_ids,
    tag_stats,
)
from haddolib.tag_core import set_tags

# data/import/ lives at the repo root. This file is src/haddolib/pyxll_bridge.py,
# so parents[2] is the root (haddolib -> src -> root). The directory is created
# and owned OUTSIDE the engine (git-ignored); run_import assumes it exists.
_IMPORT_DIR = Path(__file__).resolve().parents[2] / "data" / "import"

# One catalog instance per Python session. session_id regenerates on PyXLL
# reload, so stale handles are immediately recognisable (different prefix).
_CATALOG: HandleCatalog = HandleCatalog()


# ---------------------------------------------------------------------------
# Smoke UDF, might include version number etc. later
# ---------------------------------------------------------------------------

@xl_func
def haddo_hello() -> str:
    """Smoke UDF: confirms PyXLL is loading haddolib and running Python."""
    return "Haddolib is connected and ready!"


# ---------------------------------------------------------------------------
# Import crossing 1
# ---------------------------------------------------------------------------

@xl_macro("var[][] data")
def haddo_import(data):
    """Import crossing 1, called from VBA via Application.Run("haddo_import", rng.Value2).

    Thin shell: stamp one 'now' for the whole run, open the live DB with the
    connection contract applied, delegate everything to run_import, and ALWAYS
    close the connection. Returns the delimited summary string that VBA Splits
    into a Scripting.Dictionary (BRIDGE_CONTRACT.md section 4).

    Per-call open/close keeps the engine stateless -- no module-level connection.
    """
    now = datetime.now()
    conn = connect()                  # DEFAULT_DB is the live Windows DB; contract applied
    try:
        return run_import(conn, data, now, str(_IMPORT_DIR))
    finally:
        conn.close()                  # closed even if run_import raises


# ---------------------------------------------------------------------------
# Scalar query UDF
# ---------------------------------------------------------------------------

@xl_func("str name, str *params: var")
def haddo_query(name: str, *params):
    """Read crossing: call a named query and return its result as a cell value.

    Called directly from a worksheet cell formula:
        =haddo_query("rooms")
        =haddo_query("spaces", "Magazin")
        =haddo_query("book_count", "Magazin")
        =haddo_query("count_by_status", "ready", "Magazin")

    The PyXLL signature "str *params" collects any extra arguments into a list,
    giving the UDF its variadic character without needing Python *args in the
    type string. The return type "var" lets the function return either a string
    or an integer depending on which query is called.

    A bad query name or wrong parameter count surfaces as #VALUE! in the cell --
    the formula is wrong, fix it. No special wrapping is needed.

    Per-call open/close keeps the engine stateless -- no module-level connection.
    """
    conn = connect()
    try:
        return query(conn, name, *params)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Handle-based list queries
# ---------------------------------------------------------------------------

@xl_func("str room, str space_label, str bin_label: str")
def haddo_books_by_bin(room: str, space_label: str, bin_label: str) -> str:
    """Load all books in one bin and return a private haddolib handle string.

    Called from a worksheet cell or from VBA via Application.Run:
        handle = Application.Run("haddo_books_by_bin", "Magazin", "rack 01", "box 01")

    Opens the DB, calls books_by_bin(), closes the DB, stores the list[dict]
    in the private catalog, and returns an opaque handle string. The handle is
    a plain Excel string value -- no PyXLL object cache involved.

    Use haddo_get_field / haddo_len to read data, and haddo_release when done.
    Handles expire after 600 s of inactivity; call haddo_sweep_handles from a
    maintenance macro to evict any that leaked through a crash.

    Per-call open/close keeps the engine stateless -- no module-level connection.
    """
    conn = connect()
    try:
        rows = books_by_bin(conn, room, space_label, bin_label)
        return _CATALOG.put("books_by_bin", rows)
    finally:
        conn.close()


@xl_func("str search: str")
def haddo_books_by_title(search: str) -> str:
    """Load all books whose title contains search and return a handle string.

    Called from VBA via Application.Run:
        handle = Application.Run("haddo_books_by_title", "Krieg")

    The match is case-insensitive substring: "krieg" matches "Der Krieg der Welten".
    Returns a handle usable with haddo_len / haddo_get_field / haddo_release,
    identical contract to haddo_books_by_bin.

    Raises #VALUE! if search is blank.

    Per-call open/close keeps the engine stateless -- no module-level connection.
    """
    conn = connect()
    try:
        rows = books_by_title(conn, search)
        return _CATALOG.put("books_by_title", rows)
    finally:
        conn.close()


@xl_func("str search: str")
def haddo_books_by_author(search: str) -> str:
    """Load all books whose authors field contains search and return a handle string.

    Called from VBA via Application.Run:
        handle = Application.Run("haddo_books_by_author", "Rowling")

    The match is case-insensitive substring against the full authors string
    (comma-delimited as stored from the API). Returns a handle usable with
    haddo_len / haddo_get_field / haddo_release.

    Raises #VALUE! if search is blank.

    Per-call open/close keeps the engine stateless -- no module-level connection.
    """
    conn = connect()
    try:
        rows = books_by_author(conn, search)
        return _CATALOG.put("books_by_author", rows)
    finally:
        conn.close()


@xl_func("str tags, bool match_all: str")
def haddo_books_by_tags(tags: str, match_all: bool) -> str:
    """Load books matching the given tags and return a handle string.

    Called from VBA via Application.Run:
        handle = Application.Run("haddo_books_by_tags", "Afrika, Tiere", True)
        handle = Application.Run("haddo_books_by_tags", "Afrika, Tiere", False)

    tags      -- comma-separated tag names; whitespace around commas is ignored.
    match_all -- True:  only books carrying ALL listed tags (AND logic).
                 False: books carrying ANY of the listed tags (OR logic).

    Returns a handle usable with haddo_len / haddo_get_field / haddo_release.
    Raises #VALUE! if tags is blank or contains only whitespace.

    Per-call open/close keeps the engine stateless -- no module-level connection.
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    conn = connect()
    try:
        rows = books_by_tags(conn, tag_list, match_all)
        return _CATALOG.put("books_by_tags", rows)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tag write crossing
# ---------------------------------------------------------------------------

@xl_func("int book_id, str tags_text: str")
def haddo_set_tags(book_id: int, tags_text: str) -> str:
    """Replace all tags for a book.

    Called from VBA via Application.Run:
        Application.Run "haddo_set_tags", book_id, "Klassiker, SciFi"

    book_id   -- the integer book.book_id (retrieve via haddo_get_field on an
                 existing handle, e.g. GetHaddoBooksFieldInRow(handle, row, "book_id")).
    tags_text -- comma-delimited tag names; whitespace around names is trimmed.
                 An empty or blank string clears all tags for the book.

    Returns "ok" on success. Raises #VALUE! if book_id is not a positive integer.

    Per-call open/close keeps the engine stateless -- no module-level connection.
    """
    conn = connect()
    try:
        set_tags(conn, book_id, tags_text)
        conn.commit()
        return "ok"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tag statistics
# ---------------------------------------------------------------------------

@xl_func("bool order_by_count: var[][]")
def haddo_tag_stats(order_by_count: bool = True):
    """Return a 2D table of all tags with their book counts.

    Use from a worksheet cell:
        =haddo_tag_stats()        -- count order (most-used first)
        =haddo_tag_stats(FALSE)   -- alphabetical order (for combobox sources)

    order_by_count (default True): True = count descending, name ascending as
        tiebreaker; False = alphabetical by name only.

    Returns a header row ["tag", "count"] followed by one data row per tag.
    Tags with no linked books (orphans) appear with count 0 -- useful for
    spotting what a prune_tags run would remove.

    Returns a header-only table when no tags exist.

    Per-call open/close keeps the engine stateless -- no module-level connection.
    """
    conn = connect()
    try:
        rows = tag_stats(conn, order_by_count)
    finally:
        conn.close()
    return [["tag", "count"]] + [[name, count] for name, count in rows]


# ---------------------------------------------------------------------------
# Handle refresh crossing
# ---------------------------------------------------------------------------

@xl_func("str handle: str")
def haddo_refresh_handle(handle: str) -> str:
    """Refresh a handle's snapshot from the database.

    After a write operation (e.g. haddo_set_tags), the existing snapshot held
    under a handle is stale. Call this to pull fresh rows for all book_ids in
    the snapshot, replacing the old data in place. The handle string is
    unchanged -- VBA holds the same variable and sees updated data on the next
    haddo_get_field call.

    Called from VBA via Application.Run:
        Application.Run "haddo_refresh_handle", m_sHaddoHandle

    Returns "ok" on success. Raises #VALUE! if the handle is unknown or stale.

    Per-call open/close keeps the engine stateless -- no module-level connection.
    """
    current_rows = _CATALOG.get(handle)
    book_ids = [row["book_id"] for row in current_rows]
    conn = connect()
    try:
        fresh_rows = books_by_ids(conn, book_ids)
        _CATALOG.replace(handle, fresh_rows)
        return "ok"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Shared handle accessors -- kind-agnostic, work with any haddo_books_by_* handle
# ---------------------------------------------------------------------------

@xl_func("str handle, int row, str field: var")
def haddo_get_field(handle: str, row: int, field: str):
    """Return one field value from a cached haddo_books_by_* result.

    Called from a VBA macro via Application.Run:
        value = Application.Run("haddo_get_field", handle, 1, "title")

    row is 1-based (VBA convention): row=1 is the first book in the result.
    field is any key present in the book_current dict (e.g. "title", "isbn13",
    "cover_ref", "tags").

    Works with handles from any haddo_books_by_* function -- kind-agnostic.
    Raises #VALUE! if the handle is stale, the row is out of range, or the
    field name is unknown.
    """
    data = _CATALOG.get(handle)           # no expected_kind -- all book handles share this accessor
    row_dict = data[row - 1]
    if field not in row_dict:
        available = ", ".join(sorted(row_dict.keys()))
        raise KeyError(f"Unknown field {field!r}. Available fields: {available}")
    return row_dict[field]


@xl_func("str handle: int")
def haddo_len(handle: str) -> int:
    """Return the number of books in a cached haddo_books_by_* result.

    Called from a VBA macro via Application.Run:
        n = Application.Run("haddo_len", handle)

    Works with handles from any haddo_books_by_* function -- kind-agnostic.
    Useful for driving a For loop over the result:
        Dim i As Long
        For i = 1 To Application.Run("haddo_len", handle)
            ...
        Next i
    """
    data = _CATALOG.get(handle)           # no expected_kind -- kind-agnostic
    return len(data)


@xl_func("str handle: str")
def haddo_release(handle: str) -> str:
    """Remove a handle from the private catalog.

    Called from a VBA macro via Application.Run:
        Application.Run "haddo_release", handle

    Always call this when finished -- ideally in an On Error GoTo Cleanup block
    so the entry is freed even if the macro fails mid-way.

    Works with handles from any haddo_books_by_* function -- kind-agnostic.
    Returns "released" if the handle existed, "not found" if it was already
    gone (e.g. expired by a sweep) -- both are safe outcomes for VBA.
    """
    released = _CATALOG.release(handle)
    return "released" if released else "not found"


@xl_func("int max_age_seconds: int")
def haddo_sweep_handles(max_age_seconds: int = _CATALOG.default_ttl_seconds) -> int:
    """Evict catalog entries not accessed within max_age_seconds.

    Call this from Workbook_Open or a maintenance macro to clean up any handles
    that leaked through a crash or an abandoned macro run:
        Application.Run "haddo_sweep_handles", 600

    Returns the number of entries evicted. Safe to call at any time.
    When called with no argument, uses the catalog's default TTL (600 s).
    """
    return _CATALOG.sweep(max_age_seconds)


@xl_func(": var[][]", volatile=True)
def haddo_handles():
    """Diagnostic UDF: return a table of all active catalog entries.

    Use from a worksheet cell during development:
        =haddo_handles()

    IMPORTANT: This function is intentionally volatile, see signature.
    Do not remove the `volatile=True`.

    Returns a 2D table with columns:
        handle | kind | created_at | last_accessed_at | size
    The header row is always present; the table is empty (header only) when the
    catalog holds no entries. Datetimes are formatted as ISO 8601 strings;
    size is blank when the stored object has no length.
    """
    header = [["handle", "kind", "created_at", "last_accessed_at", "size"]]
    rows = [
        [
            e["handle"],
            e["kind"],
            e["created_at"].isoformat(timespec="seconds"),
            e["last_accessed_at"].isoformat(timespec="seconds"),
            e["size"] if e["size"] is not None else "",
        ]
        for e in _CATALOG.snapshot()
    ]
    return header + rows