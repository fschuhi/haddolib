#!/usr/bin/env python3
"""
openlibrary_lookup.py -- Bulk ISBN lookup via Open Library Books API.

Reads ISBNs (one per line) from a file (-i) or stdin.
Writes a semicolon-delimited CSV (UTF-8 BOM, German Excel compatible)
to a file (-o) or stdout.

Progress and batch info are written to stderr.

Usage:
    python scripts/openlibrary_lookup.py -i data/input/isbns.txt -o data/output/isbn_results.csv
    cat data/input/isbns.txt | python scripts/openlibrary_lookup.py -o data/output/isbn_results.csv
    python scripts/openlibrary_lookup.py -i data/input/isbns.txt   # stdout
"""

import argparse
import sys
import time

import requests

from haddolib.common import write_csv

# --- Constants ---

API_URL = "https://openlibrary.org/api/books"
BATCH_SIZE = 20
BATCH_DELAY_S = 1.0  # seconds between batches, to be polite

CSV_FIELDS = [
    "isbn",
    "found",
    "title",
    "subtitle",
    "authors",
    "publisher",
    "publish_date",
    "pages",
    "subjects",
    "cover_url_medium",
    "cover_url_large",
    "ol_url",
]


# --- ISBN validation ---

def _is_plausible_isbn(raw: str) -> bool:
    """
    Quick sanity check: accept ISBN-13 (starts with 978/979, 13 digits)
    or ISBN-10 (10 chars, first 9 digits, last digit or X).
    Does NOT compute the check digit -- that's already been done in Excel.
    """
    s = raw.replace("-", "").replace(" ", "").upper()
    if len(s) == 13:
        return s.isdigit() and (s.startswith("978") or s.startswith("979"))
    if len(s) == 10:
        return s[:9].isdigit() and (s[9].isdigit() or s[9] == "X")
    return False


# --- Open Library extraction ---

def _extract(isbn: str, data: dict) -> dict:
    """Extract the fields we care about from a single OL record."""

    def names(lst):
        return "; ".join(item.get("name", "") for item in lst) if lst else ""

    title = data.get("title", "")
    subtitle = data.get("subtitle", "")
    authors = names(data.get("authors", []))
    publishers = names(data.get("publishers", []))
    publish_date = data.get("publish_date", "")
    pages = data.get("number_of_pages", "")
    subjects = names(data.get("subjects", []))
    covers = data.get("cover", {})
    cover_medium = covers.get("medium", "")
    cover_large = covers.get("large", "")
    ol_url = data.get("url", "")

    return {
        "isbn": isbn,
        "found": 1,
        "title": title,
        "subtitle": subtitle,
        "authors": authors,
        "publisher": publishers,
        "publish_date": publish_date,
        "pages": pages,
        "subjects": subjects,
        "cover_url_medium": cover_medium,
        "cover_url_large": cover_large,
        "ol_url": ol_url,
    }


def _not_found(isbn: str) -> dict:
    return {"isbn": isbn, "found": 0, **{f: "" for f in CSV_FIELDS if f not in ("isbn", "found")}}


# --- Core lookup ---

def lookup_batch(isbns: list[str]) -> dict[str, dict]:
    """Query Open Library for a batch of ISBNs. Returns {isbn: row_dict}."""
    bibkeys = ",".join(f"ISBN:{isbn}" for isbn in isbns)
    params = {"bibkeys": bibkeys, "format": "json", "jscmd": "data"}

    try:
        response = requests.get(API_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"[ERROR] API request failed: {e}", file=sys.stderr)
        return {isbn: _not_found(isbn) for isbn in isbns}

    results = {}
    for isbn in isbns:
        key = f"ISBN:{isbn}"
        if key in data:
            results[isbn] = _extract(isbn, data[key])
        else:
            results[isbn] = _not_found(isbn)
    return results


# --- I/O helpers ---

def read_isbns(source) -> list[str]:
    """
    Read ISBNs from a file-like object.
    - Strips CRLF and whitespace
    - Skips blank lines and comment lines (starting with #)
    - Warns about lines that don't look like ISBNs
    """
    isbns = []
    skipped = []
    for lineno, raw in enumerate(source, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _is_plausible_isbn(line):
            isbns.append(line)
        else:
            skipped.append((lineno, line))

    if skipped:
        print(f"[WARN] Skipped {len(skipped)} non-ISBN line(s):", file=sys.stderr)
        for lineno, val in skipped:
            print(f"       line {lineno}: {val!r}", file=sys.stderr)

    return isbns


# --- Main ---

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk ISBN lookup via Open Library. Writes semicolon-delimited CSV."
    )
    parser.add_argument(
        "-i", "--input",
        metavar="FILE",
        help="Input file with one ISBN per line (default: stdin)",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="Output CSV file (default: stdout)",
    )
    args = parser.parse_args()

    # --- Read ISBNs ---
    if args.input:
        with open(args.input, encoding="utf-8-sig") as f:  # utf-8-sig strips BOM if present
            isbns = read_isbns(f)
    else:
        isbns = read_isbns(sys.stdin)

    total = len(isbns)
    print(f"[INFO] {total} valid ISBN(s) to look up", file=sys.stderr)

    if total == 0:
        print("[WARN] Nothing to do.", file=sys.stderr)
        sys.exit(0)

    # --- Batch lookup ---
    rows = []
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(num_batches):
        batch = isbns[batch_idx * BATCH_SIZE : (batch_idx + 1) * BATCH_SIZE]
        batch_num = batch_idx + 1
        print(
            f"[INFO] Batch {batch_num}/{num_batches} -- {len(batch)} ISBN(s) ...",
            file=sys.stderr,
        )
        results = lookup_batch(batch)
        rows.extend(results[isbn] for isbn in batch)  # preserve input order

        found_in_batch = sum(1 for isbn in batch if results[isbn]["found"])
        print(
            f"       -> {found_in_batch}/{len(batch)} found",
            file=sys.stderr,
        )

        if batch_num < num_batches:
            time.sleep(BATCH_DELAY_S)

    found_total = sum(1 for r in rows if r["found"])
    print(f"[INFO] Done. {found_total}/{total} ISBN(s) found.", file=sys.stderr)

    # --- Write CSV ---
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            write_csv(rows, f, CSV_FIELDS)
        print(f"[INFO] Output written to {args.output}", file=sys.stderr)
    else:
        write_csv(rows, sys.stdout, CSV_FIELDS)


if __name__ == "__main__":
    main()
