#!/usr/bin/env python3
"""
isbndb_synopsis.py -- Fetch synopses for pdf-annotations PDFs via ISBNdb.

Reads the query CSV produced by pdf_lst_to_queries.py (pdf_id;query;year).
For each row, fetches all editions via ISBNdb's free-text search, picks the
one whose date_published matches year (falling back to the best overall
match if none does -- see select_best_matching_year() in isbndb_utils.py),
and writes <pdf_id>.txt into --synopses-dir: the synopsis text if found and
non-empty, otherwise a zero-length file. A zero-length file marks the pdf_id
as resolved either way, so a plain rerun skips it -- pass --force to
re-query and overwrite regardless.

Synopsis files are written UTF-8 with a byte-order mark (utf-8-sig), so
Windows text viewers that lack a BOM to detect (e.g. Total Commander's F3
lister) don't fall back to guessing the system codepage on non-ASCII
characters -- same reasoning as the UTF-8 BOM already used for CSV output
elsewhere in this project.

Also writes a semicolon-delimited CSV (UTF-8 BOM, German Excel compatible)
with one row per pdf_id actually resolved this run (skipped pdf_ids get no
row): the standard record columns, plus query, pdf_id, year_searched,
year_matched, and has_synopsis. The synopsis text itself lives only in the
.txt file, not in this CSV. If every pdf_id was already resolved (nothing
to do this run), the output CSV is left untouched rather than overwritten
with an empty file.

Rate limit: 1 request/second (ISBNdb Basic plan) -- applied only between
rows that actually need an API call.

API key is read from the environment variable ISBNDB_API_KEY,
or from a .env file in the current working directory.

Usage:
    python scripts/isbndb_synopsis.py -i data/output/pdfs_query.csv \\
        -o data/output/pdfs_query_result.csv --synopses-dir ~/Obsidian/Papers/Collection/Synopses
    python scripts/isbndb_synopsis.py -i data/output/pdfs_query.csv \\
        -o data/output/pdfs_query_result.csv --synopses-dir ~/Obsidian/Papers/Collection/Synopses --force
"""

import argparse
import csv
import os
import sys
import time

from dotenv import load_dotenv

from haddolib.common import write_csv
from haddolib.isbndb_utils import (
    RECORD_CSV_FIELDS,
    extract_record,
    fetch_editions,
    select_best_matching_year,
)

# --- Constants ---

REQUEST_DELAY_S = 1.0

CSV_FIELDS = RECORD_CSV_FIELDS + ["query", "pdf_id", "year_searched", "year_matched", "has_synopsis"]


# --- I/O helpers ---

def read_query_rows(source) -> list[dict]:
    """
    Read query rows from the semicolon-delimited CSV produced by
    pdf_lst_to_queries.py. Each row has keys pdf_id, query, year.
    """
    reader = csv.DictReader(source, delimiter=";")
    return list(reader)


def _not_found_row(pdf_id: str, query: str, year: str) -> dict:
    row = {field: "" for field in RECORD_CSV_FIELDS}
    row["isbn13"] = "NA"
    row["found"] = 0
    row["query"] = query
    row["pdf_id"] = pdf_id
    row["year_searched"] = year
    row["year_matched"] = ""
    row["has_synopsis"] = 0
    return row


# --- Resolution ---

def resolve_row(pdf_id: str, query: str, year: str, api_key: str) -> tuple[dict, str]:
    """
    Resolve one query row: fetch all editions, pick the best year-matching
    one via select_best_matching_year(), and return (csv_row, synopsis_text).

    csv_row always carries pdf_id, year_searched, year_matched, has_synopsis
    plus the standard record columns. synopsis_text is "" when no edition
    was found at all, or the matched edition's synopsis is empty -- both
    cases still produce a (zero-length) .txt file, by design.
    """
    records = fetch_editions(query, api_key)
    record, year_matched = select_best_matching_year(records, year)

    if record is None:
        return _not_found_row(pdf_id, query, year), ""

    row = extract_record(record, include_synopsis=True)
    synopsis_text = row.pop("synopsis", "")  # goes to the .txt file, not the CSV
    row["query"] = query
    row["pdf_id"] = pdf_id
    row["year_searched"] = year
    row["year_matched"] = year_matched
    row["has_synopsis"] = 1 if synopsis_text else 0
    return row, synopsis_text


# --- Main ---

def main() -> None:
    load_dotenv()

    api_key = os.environ.get("ISBNDB_API_KEY")
    if not api_key:
        print("[ERROR] ISBNDB_API_KEY not set. Add it to .env or the environment.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Fetch synopses for pdf-annotations PDFs via ISBNdb, one .txt file per pdf_id."
    )
    parser.add_argument("-i", "--input", metavar="FILE", required=True,
                        help="Input query CSV from pdf_lst_to_queries.py: pdf_id;query;year")
    parser.add_argument("-o", "--output", metavar="FILE", required=True,
                        help="Output CSV file")
    parser.add_argument("--synopses-dir", metavar="DIR", required=True,
                        help="Directory to write <pdf_id>.txt synopsis files into")
    parser.add_argument("--force", action="store_true",
                        help="Re-query and overwrite even if <pdf_id>.txt already exists")
    args = parser.parse_args()

    synopses_dir = os.path.expanduser(args.synopses_dir)
    os.makedirs(synopses_dir, exist_ok=True)

    with open(args.input, encoding="utf-8-sig") as f:
        query_rows = read_query_rows(f)

    total = len(query_rows)
    print(f"[INFO] {total} query row(s) read", file=sys.stderr)
    if total == 0:
        print("[WARN] Nothing to do.", file=sys.stderr)
        sys.exit(0)

    # --- Decide which rows need an API call: no need to ask the API for
    # synopses we already have, unless --force. ---
    work_items = []  # (pdf_id, query, year, txt_path)
    skipped_existing = 0
    for row in query_rows:
        pdf_id, query, year = row["pdf_id"], row["query"], row["year"]
        txt_path = os.path.join(synopses_dir, f"{pdf_id}.txt")
        if not args.force and os.path.exists(txt_path):
            skipped_existing += 1
            continue
        work_items.append((pdf_id, query, year, txt_path))

    print(
        f"[INFO] {len(work_items)} to resolve, {skipped_existing} already have a synopsis file (skipped)",
        file=sys.stderr,
    )

    if not work_items:
        print("[INFO] Nothing to resolve -- leaving existing output CSV untouched.", file=sys.stderr)
        sys.exit(0)

    # --- Resolve, write .txt files, collect CSV rows ---
    csv_rows = []
    for idx, (pdf_id, query, year, txt_path) in enumerate(work_items, start=1):
        print(f"[INFO] {idx}/{len(work_items)} {pdf_id} {query!r} ...", file=sys.stderr)
        csv_row, synopsis_text = resolve_row(pdf_id, query, year, api_key)
        csv_rows.append(csv_row)

        if synopsis_text:
            with open(txt_path, "w", encoding="utf-8-sig") as f:
                f.write(synopsis_text)
        else:
            open(txt_path, "w", encoding="utf-8").close()  # zero-length, by design

        status = "found" if csv_row["found"] else "not found"
        year_note = f", year matched {csv_row['year_matched']}" if csv_row["year_matched"] else ""
        print(f"       -> {status}{year_note}", file=sys.stderr)

        if idx < len(work_items):
            time.sleep(REQUEST_DELAY_S)

    found_total = sum(1 for r in csv_rows if r["found"])
    print(f"[INFO] Done. {found_total}/{len(work_items)} resolved.", file=sys.stderr)

    with open(args.output, "w", encoding="utf-8", newline="") as f:
        write_csv(csv_rows, f, CSV_FIELDS)
    print(f"[INFO] Output written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
