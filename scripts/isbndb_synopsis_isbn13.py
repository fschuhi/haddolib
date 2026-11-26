#!/usr/bin/env python3
"""
isbndb_synopsis_isbn13.py -- Fetch synopses for the catalogue's books via ISBNdb.

Reads a snapshot xlsx (default: the newest YYYYMMDD_HHMMSS_snapshot.xlsx in data/import/)
and takes every row whose revision_source is 'isbndb' and that has an isbn13:
the books known to be on ISBNdb. Fetches them in bulk (up to 100 ISBNs per
call, see fetch_by_isbn13() in isbndb_utils.py) and writes <isbn13>.txt into
--synopses-dir: the synopsis text if there is one, otherwise a zero-length
file. A zero-length file marks the book as looked up either way, so a plain
rerun skips it -- pass --force to fetch again and overwrite regardless.

Synopsis files are written UTF-8 with a byte-order mark (utf-8-sig), the same
contract as isbndb_synopsis.py (the pdf-annotations flow). The text is
written exactly as ISBNdb returns it.

A failed request (network, VPN, quota) stops the run with exit code 1. Files
of earlier batches stay; the failed batch gets no files, so a rerun carries on
where this run stopped.

Rate limit: one bulk call per BATCH_DELAY_S (ISBNdb Basic plan: 1 call/s).

API key is read from the environment variable ISBNDB_API_KEY,
or from a .env file in the current working directory.

Usage:
    python scripts/isbndb_synopsis_isbn13.py
    python scripts/isbndb_synopsis_isbn13.py -i data/import/20261126_191354_snapshot.xlsx
    python scripts/isbndb_synopsis_isbn13.py --force
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from zipfile import BadZipFile

import requests
from dotenv import load_dotenv
from openpyxl import load_workbook

from haddolib.common import as_text
from haddolib.isbndb_utils import BATCH_SIZE, fetch_by_isbn13

# --- Constants ---

IMPORT_DIR = Path("data/import")
DEFAULT_SYNOPSES_DIR = Path("data/synopses")
SNAPSHOT_NAME = re.compile(r"\d{8}_\d{6}_snapshot\.xlsx")    # as written by make snapshot
SOURCE_ISBNDB = "isbndb"
BATCH_DELAY_S = 1.1    # Basic plan: 1 call per second; slight margin


# --- Input helpers ---

def newest_snapshot(import_dir: Path) -> Path:
    """
    Return the newest YYYYMMDD_HHMMSS_snapshot.xlsx in import_dir, so the name
    order is the time order. Only names of exactly that form count: an Excel
    lock file (~$20261126_191354_snapshot.xlsx) or a macOS ._ file is no snapshot.
    Raises FileNotFoundError if there is none.
    """
    snapshots = sorted(p for p in import_dir.iterdir() if SNAPSHOT_NAME.fullmatch(p.name))
    if not snapshots:
        raise FileNotFoundError(f"No YYYYMMDD_HHMMSS_snapshot.xlsx in {import_dir}")
    return snapshots[-1]


def read_isbn13s(xlsx_path: Path) -> list[str]:
    """
    Read a snapshot xlsx and return the isbn13 of every row whose
    revision_source is 'isbndb' and whose isbn13 is not empty, in sheet order,
    without duplicates. Columns are found by header name.
    Raises ValueError if the sheet lacks the isbn13 or revision_source column.
    """
    wb = load_workbook(xlsx_path, read_only=True)
    try:
        rows = wb.active.iter_rows(values_only=True)
        header = [as_text(h) for h in next(rows, ())]
        for name in ("isbn13", "revision_source"):
            if name not in header:
                raise ValueError(f"{xlsx_path}: column {name!r} not found in the header row")
        i_isbn, i_source = header.index("isbn13"), header.index("revision_source")

        isbn13s: dict[str, None] = {}   # a dict keeps the order, drops duplicates
        for row in rows:
            isbn13 = as_text(row[i_isbn]) if i_isbn < len(row) else None
            source = as_text(row[i_source]) if i_source < len(row) else None
            if isbn13 and source == SOURCE_ISBNDB:
                isbn13s[isbn13] = None
        return list(isbn13s)
    finally:
        wb.close()


def chunks(items: list[str], size: int) -> list[list[str]]:
    """Split items into consecutive lists of at most size items."""
    return [items[i:i + size] for i in range(0, len(items), size)]


# --- Output helper ---

def write_synopsis(path: Path, text: str) -> None:
    """Write text as utf-8-sig, or a zero-length file if text is empty."""
    if text:
        path.write_text(text, encoding="utf-8-sig")
    else:
        path.write_bytes(b"")


# --- Main ---

def main() -> None:
    load_dotenv()

    api_key = os.environ.get("ISBNDB_API_KEY")
    if not api_key:
        print("[ERROR] ISBNDB_API_KEY not set. Add it to .env or the environment.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Fetch synopses for the catalogue's ISBNdb books, one <isbn13>.txt file per book."
    )
    parser.add_argument("-i", "--input", metavar="FILE", type=Path,
                        help=f"Snapshot xlsx (default: the newest snapshot in {IMPORT_DIR})")
    parser.add_argument("--synopses-dir", metavar="DIR", type=Path, default=DEFAULT_SYNOPSES_DIR,
                        help=f"Directory for the <isbn13>.txt files (default: {DEFAULT_SYNOPSES_DIR})")
    parser.add_argument("--force", action="store_true",
                        help="Fetch again and overwrite even if <isbn13>.txt already exists")
    args = parser.parse_args()

    try:
        snapshot = args.input or newest_snapshot(IMPORT_DIR)
        print(f"[INFO] Reading {snapshot}", file=sys.stderr)
        isbn13s = read_isbn13s(snapshot)
    except (FileNotFoundError, ValueError, BadZipFile) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] {len(isbn13s)} book(s) with revision_source {SOURCE_ISBNDB!r}", file=sys.stderr)

    synopses_dir = args.synopses_dir
    synopses_dir.mkdir(parents=True, exist_ok=True)

    todo = [i for i in isbn13s if args.force or not (synopses_dir / f"{i}.txt").exists()]
    print(f"[INFO] {len(todo)} to fetch, {len(isbn13s) - len(todo)} already have a file (skipped)",
          file=sys.stderr)
    if not todo:
        print("[INFO] Nothing to fetch.", file=sys.stderr)
        return

    batches = chunks(todo, BATCH_SIZE)
    with_text = 0
    without_synopsis = 0    # ISBNdb returned the book, but with no synopsis
    not_returned = 0        # ISBNdb did not return the book at all
    for n, batch in enumerate(batches, start=1):
        print(f"[INFO] Batch {n}/{len(batches)} ({len(batch)} ISBNs) ...", file=sys.stderr)
        try:
            records = fetch_by_isbn13(batch, api_key)
        except requests.RequestException as e:
            print(f"[ERROR] Batch {n} failed: {e}", file=sys.stderr)
            print("[ERROR] Stopped. Files of earlier batches are kept; rerun to continue.", file=sys.stderr)
            sys.exit(1)

        for isbn13 in batch:
            record = records.get(isbn13)
            text = (record or {}).get("synopsis") or ""
            write_synopsis(synopses_dir / f"{isbn13}.txt", text)
            if text:
                with_text += 1
            elif record is None:
                not_returned += 1
            else:
                without_synopsis += 1

        if n < len(batches):
            time.sleep(BATCH_DELAY_S)

    print(f"[INFO] Done. {len(todo)} fetched: {with_text} with a synopsis, "
          f"{without_synopsis} returned without one, {not_returned} not returned by ISBNdb "
          f"(the last two are zero-length files).", file=sys.stderr)


if __name__ == "__main__":
    main()
