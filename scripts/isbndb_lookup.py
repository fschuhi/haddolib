#!/usr/bin/env python3
"""
isbndb_lookup.py — Bulk ISBN lookup via ISBNdb API v2.

Reads ISBNs (one per line) from a file (-i) or stdin.
Writes a semicolon-delimited CSV (UTF-8 BOM, German Excel compatible)
to a file (-o) or stdout.

Progress and batch info are written to stderr.

ISBN-10s are skipped (ISBNdb bulk POST does not match them reliably).
Collect skipped ISBN-10s and resolve them via isbndb_search.py instead.

API key is read from the environment variable ISBNDB_API_KEY,
or from a .env file in the current working directory.

Usage:
    python tools/isbndb_lookup.py -i data/input/isbns.txt -o data/output/isbndb_results.csv
    cat data/input/isbns.txt | python tools/isbndb_lookup.py -o data/output/isbndb_results.csv
"""

import argparse
import os
import sys
import time

import requests
from dotenv import load_dotenv

from haddolib.common import is_valid_isbn, is_valid_isbn13, write_csv
from haddolib.isbndb_utils import extract_record

# --- Constants ---

API_URL = "https://api2.isbndb.com/books"
BATCH_SIZE = 100       # Basic plan maximum
BATCH_DELAY_S = 1.1    # Basic plan: 1 call per second; slight margin

CSV_SEP = ";"

CSV_FIELDS = [
    "isbn13",
    "found",
    "title",
    "title_long",
    "authors",
    "publisher",
    "date_published",
    "edition",
    "pages",
    "binding",
    "language",
    "dimensions",
    "height_cm",
    "length_cm",
    "width_cm",
    "weight_kg",
    "subjects",
    "cover_url",
    "dewey_decimal",
    "isbn10",
]


def _not_found(isbn: str) -> dict:
    return {
        "isbn13": f"{isbn}",
        "found": 0,
        **{f: "" for f in CSV_FIELDS if f not in ("isbn13", "found")},
    }


# --- API call ---

def lookup_batch(isbns: list[str], api_key: str) -> dict[str, dict]:
    """Query ISBNdb for a batch of ISBNs. Returns {isbn: row_dict}."""
    headers = {
        "accept": "application/json",
        "Authorization": api_key,
        "Content-Type": "application/json",
    }
    payload = {"isbns": isbns}

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 429:
            print("[WARN] Rate limit hit — waiting 5s before retry", file=sys.stderr)
            time.sleep(5)
            response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"[ERROR] API request failed: {e}", file=sys.stderr)
        return {isbn: _not_found(isbn) for isbn in isbns}

    found_map = {}
    for record in data.get("data", []):
        key = record.get("isbn13") or record.get("isbn")
        if key:
            found_map[key] = extract_record(record)

    results = {}
    for isbn in isbns:
        results[isbn] = found_map.get(isbn, _not_found(isbn))

    requested = data.get("requested", len(isbns))
    if requested != len(isbns):
        print(
            f"[WARN] API reported requested={requested}, we sent {len(isbns)}",
            file=sys.stderr,
        )

    return results


# --- I/O helpers ---

def read_isbns(source) -> tuple[list[str], list[str], list[tuple[int, str]]]:
    """
    Read ISBNs from a file-like object.
    Returns:
        isbn13s  — valid ISBN-13s, ready for bulk POST
        isbn10s  — valid ISBN-10s, skipped by this script (use isbndb_search.py)
        skipped  — (lineno, value) pairs that don't look like ISBNs at all
    """
    isbn13s = []
    isbn10s = []
    skipped = []

    for lineno, raw in enumerate(source, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if is_valid_isbn13(line):
            isbn13s.append(line)
        elif is_valid_isbn(line):
            isbn10s.append(line)
        else:
            skipped.append((lineno, line))

    return isbn13s, isbn10s, skipped


# --- Main ---

def main() -> None:
    load_dotenv()

    api_key = os.environ.get("ISBNDB_API_KEY")
    if not api_key:
        print("[ERROR] ISBNDB_API_KEY not set. Add it to .env or the environment.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Bulk ISBN-13 lookup via ISBNdb API v2. Writes semicolon-delimited CSV."
    )
    parser.add_argument("-i", "--input", metavar="FILE",
                        help="Input file with one ISBN per line (default: stdin)")
    parser.add_argument("-o", "--output", metavar="FILE",
                        help="Output CSV file (default: stdout)")
    args = parser.parse_args()

    # --- Read ---
    if args.input:
        with open(args.input, encoding="utf-8-sig") as f:
            isbn13s, isbn10s, skipped = read_isbns(f)
    else:
        isbn13s, isbn10s, skipped = read_isbns(sys.stdin)

    if skipped:
        print(f"[WARN] Skipped {len(skipped)} non-ISBN line(s):", file=sys.stderr)
        for lineno, val in skipped:
            print(f"       line {lineno}: {val!r}", file=sys.stderr)

    if isbn10s:
        print(
            f"[INFO] {len(isbn10s)} ISBN-10(s) discarded — not supported by bulk POST endpoint.",
            file=sys.stderr,
        )
        print(
            f"       Resolve these via isbndb_search.py instead.",
            file=sys.stderr,
        )

    total = len(isbn13s)
    print(f"[INFO] {total} ISBN-13(s) to look up", file=sys.stderr)
    if total == 0:
        print("[WARN] Nothing to do.", file=sys.stderr)
        sys.exit(0)

    # --- Batch lookup ---
    rows = []
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(num_batches):
        batch = isbn13s[batch_idx * BATCH_SIZE : (batch_idx + 1) * BATCH_SIZE]
        batch_num = batch_idx + 1
        print(f"[INFO] Batch {batch_num}/{num_batches} — {len(batch)} ISBN(s) ...", file=sys.stderr)

        results = lookup_batch(batch, api_key)
        rows.extend(results[isbn] for isbn in batch)

        found_in_batch = sum(1 for isbn in batch if results[isbn]["found"])
        print(f"       → {found_in_batch}/{len(batch)} found", file=sys.stderr)

        if batch_num < num_batches:
            time.sleep(BATCH_DELAY_S)

    found_total = sum(1 for r in rows if r["found"])
    print(f"[INFO] Done. {found_total}/{total} ISBN-13(s) found.", file=sys.stderr)

    # --- Write ---
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            write_csv(rows, f, CSV_FIELDS)
        print(f"[INFO] Output written to {args.output}", file=sys.stderr)
    else:
        write_csv(rows, sys.stdout, CSV_FIELDS)


if __name__ == "__main__":
    main()
