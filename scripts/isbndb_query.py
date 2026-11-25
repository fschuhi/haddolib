#!/usr/bin/env python3
"""
isbndb_query.py -- Single-query debug tool for the ISBNdb API.

For free-text queries, fires one request against GET /books/{query} and writes
all returned results as semicolon-delimited CSV to stdout (UTF-8 BOM, German
Excel compatible). No result selection or filtering -- all records are written
for human inspection.

For ISBN inputs (ISBN-13 or ISBN-10), routes to the POST /books endpoint
instead, since ISBNdb removed ISBN matching from the free-text search endpoint.
ISBN-10s are automatically converted to ISBN-13 before lookup.

Use this to debug why a query returns unexpected results, or to decide how
to phrase a query before adding it to a bulk input file for isbndb_search.py.

By default the synopsis field is omitted (synopses can be very long and make
the output hard to read). Use --synopsis to include it as the final column.

API key is read from the environment variable ISBNDB_API_KEY,
or from a .env file in the current working directory.

Usage:
    python scripts/isbndb_query.py "Wolf Haas Müll"
    python scripts/isbndb_query.py "Daniel Goleman    EQ Emotionale Intelligenz"
    python scripts/isbndb_query.py --synopsis "Wolf Haas Müll"
    python scripts/isbndb_query.py 9783442164998
    python scripts/isbndb_query.py 3892282358
"""

import argparse
import os
import sys
import time

import requests
from dotenv import load_dotenv

from haddolib.common import is_valid_isbn13, is_valid_isbn10, isbn10_to_isbn13, write_csv
from haddolib.isbndb_utils import extract_record

# --- Constants ---

API_URL = "https://api2.isbndb.com/books"

BASE_FIELDS = [
    "isbn13",
    "isbn10",
    "title",
    "authors",
    "publisher",
    "date_published",
    "binding",
    "pages",
    "cover_url",
]


# --- API calls ---

def lookup_one(isbn13: str, api_key: str, include_synopsis: bool) -> dict | None:
    """
    Look up a single ISBN-13 via the ISBNdb bulk POST endpoint.

    Returns an extracted record dict, or None if not found or request failed.
    """
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
        print(f"[ERROR] API request failed: {e}", file=sys.stderr)
        return None

    records = data.get("data", [])
    if not records:
        return None
    return extract_record(records[0], include_synopsis=include_synopsis)


def query_all(query: str, api_key: str, include_synopsis: bool) -> list[dict]:
    """
    Query ISBNdb for a single free-text search string.

    Returns all records from the API response as a list of row dicts.
    Each record is extracted via extract_record(); no filtering or selection.
    Returns an empty list if the request fails or no results are found.
    """
    headers = {
        "accept": "application/json",
        "Authorization": api_key,
    }
    url = f"{API_URL}/{requests.utils.quote(query, safe='')}"

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"[ERROR] API request failed: {e}", file=sys.stderr)
        return []

    records = data.get("books", [])
    return [extract_record(r, include_synopsis=include_synopsis) for r in records]


# --- Main ---

def main() -> None:
    load_dotenv()

    api_key = os.environ.get("ISBNDB_API_KEY")
    if not api_key:
        print("[ERROR] ISBNDB_API_KEY not set. Add it to .env or the environment.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Single-query ISBNdb debug tool. Writes all results as CSV to stdout."
    )
    parser.add_argument("query", help="Query string: free text, ISBN-13, or ISBN-10")
    parser.add_argument("--synopsis", action="store_true",
                        help="Include synopsis as final column (raw HTML, may be very long)")
    args = parser.parse_args()

    fields = BASE_FIELDS + ["synopsis"] if args.synopsis else BASE_FIELDS
    query = args.query.strip()

    if is_valid_isbn13(query):
        print(f"[INFO] Detected ISBN-13 -- using lookup endpoint", file=sys.stderr)
        record = lookup_one(query, api_key, include_synopsis=args.synopsis)
        rows = [record] if record else []
    elif is_valid_isbn10(query):
        isbn13 = isbn10_to_isbn13(query)
        print(f"[INFO] Detected ISBN-10 -- converted to {isbn13}, using lookup endpoint", file=sys.stderr)
        record = lookup_one(isbn13, api_key, include_synopsis=args.synopsis)
        rows = [record] if record else []
    else:
        rows = query_all(query, api_key, include_synopsis=args.synopsis)

    if not rows:
        print("[INFO] No results.", file=sys.stderr)
        sys.exit(0)

    print(f"[INFO] {len(rows)} result(s) for {query!r}", file=sys.stderr)
    write_csv(rows, sys.stdout, fields)


if __name__ == "__main__":
    main()
