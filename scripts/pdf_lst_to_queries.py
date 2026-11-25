#!/usr/bin/env python3
"""
pdf_lst_to_queries.py — Convert a *.lst of PDF filenames into an ISBNdb query CSV.

Reads PDF filenames (one per line) from a file (-i), each expected to follow
the pdf-annotations naming convention:

    (Author[+Author...] YYYY[a-z]) Title.pdf

Writes a semicolon-delimited CSV (UTF-8 BOM, German Excel compatible) with one
row per parseable filename: pdf_id, query, year. Intended to be inspected (in
Excel) before isbn_synopsis.py spends API calls resolving it.

pdf_id is the parenthesized "(Author[+Author...] YYYY[a-z])" prefix, verbatim
-- matches the bibnote filename stem used by pdf-annotations. The single
optional trailing disambiguation letter (e.g. "2001a") is a uniqueness device
only; it is stripped for the output "year" column.

Filenames that don't match the convention are skipped and reported to stderr
with their line number -- never a hard stop, since the *.lst may carry a few
stragglers from the Windows-to-macOS migration (e.g. Umlaut handling).

Blank lines and # comments in the input are skipped silently.

Usage:
    python scripts/pdf_lst_to_queries.py -i data/input/pdfs.lst -o data/output/queries.csv
"""

import argparse
import re
import sys

from haddolib.common import write_csv

# --- Constants ---

CSV_FIELDS = ["pdf_id", "query", "year"]

_FILENAME_RE = re.compile(
    r"^\((?P<authors>.+?) (?P<year>\d{4}[a-z]?)\) (?P<title>.+)\.pdf$"
)


# --- Parsing ---

def parse_filename(filename: str) -> dict | None:
    """
    Parse one PDF filename into a query CSV row.

    Returns a dict with keys pdf_id, query, year -- or None if filename does
    not match the "(Author[+Author...] YYYY[a-z]) Title.pdf" convention.
    """
    match = _FILENAME_RE.match(filename)
    if match is None:
        return None

    authors = match.group("authors")
    year = match.group("year")
    title = match.group("title")

    return {
        "pdf_id": f"({authors} {year})",
        "query": f"{authors}: {title}",
        "year": year[:4],
    }


# --- I/O helpers ---

def read_filenames(source) -> list[tuple[int, str]]:
    """
    Read PDF filenames from a file-like object, paired with their line number.
    Skips blank lines and lines starting with #.
    """
    lines = []
    for lineno, raw in enumerate(source, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append((lineno, line))
    return lines


# --- Main ---

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a *.lst of PDF filenames into an ISBNdb query CSV."
    )
    parser.add_argument("-i", "--input", metavar="FILE", required=True,
                        help="Input *.lst file, one PDF filename per line")
    parser.add_argument("-o", "--output", metavar="FILE", required=True,
                        help="Output CSV file")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8-sig") as f:
        filenames = read_filenames(f)

    total = len(filenames)
    print(f"[INFO] {total} filename(s) to parse", file=sys.stderr)
    if total == 0:
        print("[WARN] Nothing to do.", file=sys.stderr)
        sys.exit(0)

    rows = []
    skipped = 0
    for lineno, filename in filenames:
        row = parse_filename(filename)
        if row is None:
            skipped += 1
            print(f"[WARN] line {lineno}: does not match naming convention, skipped: {filename!r}",
                  file=sys.stderr)
            continue
        rows.append(row)

    print(f"[INFO] Done. {len(rows)}/{total} parsed, {skipped} skipped.", file=sys.stderr)

    with open(args.output, "w", encoding="utf-8", newline="") as f:
        write_csv(rows, f, CSV_FIELDS)
    print(f"[INFO] Output written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
