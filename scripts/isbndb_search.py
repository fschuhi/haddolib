#!/usr/bin/env python3
"""
isbndb_search.py -- Free-text and ISBN search via ISBNdb API v2.

Reads one query string per line from a file (-i).
Writes a semicolon-delimited CSV (UTF-8 BOM, German Excel compatible) to -o.

Query lines may be:
  - Tab-separated VLM output:  title<TAB>author<TAB>publisher
  - Free-text composed in Excel: "Daniel Goleman: EQ, Emotionale Intelligenz"
  - ISBN-13 strings: routed to the bulk POST lookup endpoint (GET search broken for ISBNs)
  - ISBN-10 strings: converted to ISBN-13 via isbn10_to_isbn13(), then routed as above

Blank lines and # comments are skipped.

One result row is written per query. If the API returns no results, a not-found
row is written with isbn13="NA" and found=0.

Rate limit: 1 request/second (ISBNdb Basic plan).

API key is read from the environment variable ISBNDB_API_KEY,
or from a .env file in the current working directory.

Usage:
    python scripts/isbndb_search.py -i data/input/queries.txt -o data/output/search_results.csv
    python scripts/isbndb_search.py -i data/input/queries.txt -o data/output/search_results.csv --synopsis
"""

import argparse
import os
import sys
import time

from dotenv import load_dotenv

from haddolib.common import is_valid_isbn13, is_valid_isbn10, isbn10_to_isbn13, write_csv
from haddolib.isbndb_utils import RECORD_CSV_FIELDS, extract_record, fetch_editions, select_best

# --- Constants ---

API_URL = "https://api2.isbndb.com/books"
REQUEST_DELAY_S = 1.0

CSV_FIELDS = RECORD_CSV_FIELDS + ["query"]


# --- API calls ---

def lookup_one(isbn13: str, api_key: str, include_synopsis: bool = False) -> dict | None:
    """
    Look up a single ISBN-13 via the ISBNdb bulk POST endpoint.

    Uses POST /books with a single-element list, which is the same endpoint
    used by isbndb_lookup.py. This is necessary because ISBNdb removed ISBN
    matching from their free-text GET search endpoint.

    Returns an extracted record dict (via extract_record), or None if the
    ISBN was not found or the request failed.
    """
    import requests

    headers = {
        "accept": "application/json",
        "Authorization": api_key,
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(API_URL, headers=headers, json={"isbns": [isbn13]}, timeout=30)
        if response.status_code == 429:
            print("[WARN] Rate limit hit -- waiting 5s before retry", file=sys.stderr)
            time.sleep(5)
            response = requests.post(API_URL, headers=headers, json={"isbns": [isbn13]}, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"[ERROR] API request failed for ISBN {isbn13!r}: {e}", file=sys.stderr)
        return None

    records = data.get("data", [])
    if not records:
        return None
    return extract_record(records[0], include_synopsis=include_synopsis)


def search_one(query: str, api_key: str, include_synopsis: bool = False) -> dict:
    """
    Search ISBNdb for a single free-text query string.

    Fetches all editions via fetch_editions(), selects the best one via
    select_best(), and returns a fully populated CSV row dict. Appends the
    original query string as the final field so Excel can identify
    search-resolved rows. If no editions are found or the request fails,
    returns a not-found row.
    """
    records = fetch_editions(query, api_key)
    best = select_best(records)

    if best is None:
        return _not_found(query)

    row = extract_record(best, include_synopsis=include_synopsis)
    row["query"] = query
    return row


# --- I/O helpers ---

def read_queries(source) -> list[str]:
    """
    Read query strings from a file-like object.
    Skips blank lines and lines starting with #.
    Returns query strings exactly as written -- no parsing or reformatting.
    """
    queries = []
    for raw in source:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        queries.append(line)
    return queries


def _not_found(query: str) -> dict:
    return {
        "isbn13": "NA",
        "found": 0,
        **{f: "" for f in CSV_FIELDS if f not in ("isbn13", "found", "query")},
        "query": query,
    }


# --- Routing ---

def resolve_query(query: str, api_key: str, include_synopsis: bool) -> dict:
    """
    Route a single query to the appropriate API call and return a CSV row dict.

    ISBN-13  -> lookup_one() via POST /books
    ISBN-10  -> convert to ISBN-13, then lookup_one() via POST /books
    anything else -> search_one() via GET /books/{query}

    In all cases the original query string is stamped into row["query"].
    """
    if is_valid_isbn13(query):
        record = lookup_one(query, api_key, include_synopsis)
        if record is None:
            return _not_found(query)
        record["query"] = query
        return record

    if is_valid_isbn10(query):
        isbn13 = isbn10_to_isbn13(query)
        print(f"       (ISBN-10 -> ISBN-13: {isbn13})", file=sys.stderr)
        record = lookup_one(isbn13, api_key, include_synopsis)
        if record is None:
            return _not_found(query)
        record["query"] = query
        return record

    return search_one(query, api_key, include_synopsis)


# --- Main ---

def main() -> None:
    load_dotenv()

    api_key = os.environ.get("ISBNDB_API_KEY")
    if not api_key:
        print("[ERROR] ISBNDB_API_KEY not set. Add it to .env or the environment.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Free-text and ISBN search via ISBNdb API v2. Writes semicolon-delimited CSV."
    )
    parser.add_argument("-i", "--input", metavar="FILE", required=True,
                        help="Input file with one query string per line")
    parser.add_argument("-o", "--output", metavar="FILE", required=True,
                        help="Output CSV file")
    parser.add_argument("--synopsis", action="store_true",
                        help="Include the synopsis field as the final CSV column")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8-sig") as f:
        queries = read_queries(f)

    total = len(queries)
    print(f"[INFO] {total} query/queries to resolve", file=sys.stderr)
    if total == 0:
        print("[WARN] Nothing to do.", file=sys.stderr)
        sys.exit(0)

    rows = []
    for idx, query in enumerate(queries, start=1):
        print(f"[INFO] {idx}/{total} {query!r} ...", file=sys.stderr)
        row = resolve_query(query, api_key, args.synopsis)
        rows.append(row)
        status = "found" if row["found"] else "not found"
        print(f"       -> {status}", file=sys.stderr)
        if idx < total:
            time.sleep(REQUEST_DELAY_S)

    found_total = sum(1 for r in rows if r["found"])
    print(f"[INFO] Done. {found_total}/{total} resolved.", file=sys.stderr)

    fieldnames = CSV_FIELDS + ["synopsis"] if args.synopsis else CSV_FIELDS
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        write_csv(rows, f, fieldnames)
    print(f"[INFO] Output written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
