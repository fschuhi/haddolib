#!/usr/bin/env python3
"""
isbndb_utils.py — Shared ISBNdb networking, selection, and field extraction.

Used by isbndb_lookup.py (bulk POST), isbndb_search.py (single GET queries),
and isbndb_synopsis.py (year-aware synopsis lookup). Handles the shared GET
request, best-match selection, dimension conversion, and record-to-CSV-row
mapping for ISBNdb API responses.
"""

import sys
import time

import requests

from haddolib.common import fmt_decimal

# --- Unit conversion constants ---

_INCHES_TO_CM = 2.54
_POUNDS_TO_KG = 0.453592
_MM_TO_CM = 0.1
_G_TO_KG = 0.001


def extract_dimensions(structured: dict) -> tuple[str, str, str, str]:
    """
    Extract height_cm, length_cm, width_cm, weight_kg from a dimensions_structured dict.

    Supports inches, cm, mm for lengths; pounds, kg, g/gram/grams for weight.
    All numeric output uses German decimal comma (via fmt_decimal).
    Returns empty strings for absent or unrecognised units (warns to stderr).
    """

    def convert_length(entry: dict) -> str:
        if not entry:
            return ""
        value = entry.get("value")
        unit = entry.get("unit", "").lower().strip()
        if value is None:
            return ""
        if unit == "inches":
            return fmt_decimal(value * _INCHES_TO_CM)
        if unit in ("cm", "centimeters", "centimetres"):
            return fmt_decimal(float(value))
        if unit == "mm":
            return fmt_decimal(value * _MM_TO_CM)
        print(f"[WARN] Unrecognised length unit: {unit!r} — leaving blank", file=sys.stderr)
        return ""

    def convert_weight(entry: dict) -> str:
        if not entry:
            return ""
        value = entry.get("value")
        unit = entry.get("unit", "").lower().strip()
        if value is None:
            return ""
        if unit == "pounds":
            return fmt_decimal(value * _POUNDS_TO_KG, decimals=4)
        if unit in ("kg", "kilograms", "kilogram"):
            return fmt_decimal(float(value), decimals=4)
        if unit in ("g", "gram", "grams"):
            return fmt_decimal(value * _G_TO_KG, decimals=4)
        print(f"[WARN] Unrecognised weight unit: {unit!r} — leaving blank", file=sys.stderr)
        return ""

    return (
        convert_length(structured.get("height", {})),
        convert_length(structured.get("length", {})),
        convert_length(structured.get("width", {})),
        convert_weight(structured.get("weight", {})),
    )


# --- Networking ---

_API_URL = "https://api2.isbndb.com/books"


def fetch_editions(query: str, api_key: str) -> list[dict]:
    """
    Fetch all editions for a free-text query via GET /books/{query}.

    Handles the ISBNdb Basic-plan 429 rate limit with a single sleep-and-retry.
    Returns the raw 'books' list from the API response -- unselected, unextracted,
    every edition the API returned. Returns an empty list if the request fails
    or no editions are found.

    Shared by isbndb_search.py's search_one() and isbndb_synopsis.py, which
    each apply their own selection logic (select_best() / select_best_matching_year())
    on top of this raw list.
    """
    headers = {
        "accept": "application/json",
        "Authorization": api_key,
    }
    url = f"{_API_URL}/{requests.utils.quote(query, safe='')}"

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 429:
            print("[WARN] Rate limit hit — waiting 5s before retry", file=sys.stderr)
            time.sleep(5)
            response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"[ERROR] API request failed for {query!r}: {e}", file=sys.stderr)
        return []

    return data.get("books", [])


# --- Result selection ---

COVER_PLACEHOLDER = "1668753483534.jpg"


def is_placeholder(cover_url: str) -> bool:
    """Return True if cover_url is the ISBNdb 'no cover' placeholder image."""
    return cover_url.endswith(COVER_PLACEHOLDER)


def select_best(records: list[dict]) -> dict | None:
    """
    Pick the best record from an API response.

    Walks records in the order returned by the API and returns the first
    one whose cover image is not the placeholder. Falls back to the first
    record if all have placeholder covers. Returns None if the list is empty.
    """
    if not records:
        return None
    for record in records:
        cover = record.get("image", "")
        if not is_placeholder(cover):
            return record
    return records[0]


def extract_year(date_published: str) -> str:
    """
    Extract the leading 4-digit year from a date_published string.

    ISBNdb returns date_published in several formats: "", "1991", "2007-05",
    "2006-05-02". Returns the first 4 characters if they form a plausible
    year, otherwise "".
    """
    prefix = (date_published or "")[:4]
    return prefix if len(prefix) == 4 and prefix.isdigit() else ""


def select_best_matching_year(records: list[dict], year: str) -> tuple[dict | None, str]:
    """
    Pick the best record from an API response, preferring a matching year.

    If year is truthy, filters records to those whose date_published starts
    with that year (via extract_year()) and runs select_best() over just
    that subset. Falls back to select_best() over the full list -- either
    because year was falsy, or none of the records matched it.

    Returns (record, year_matched): year_matched is year if a matching
    record was selected, otherwise "". Returns (None, "") if records is
    empty.
    """
    if year:
        matching = [r for r in records if extract_year(r.get("date_published", "")) == year]
        if matching:
            return select_best(matching), year
    return select_best(records), ""


# --- Extraction ---

RECORD_CSV_FIELDS = [
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


def extract_record(record: dict, include_synopsis: bool = False) -> dict:
    """
    Extract CSV fields from a single ISBNdb API record.

    Works for both bulk POST responses (isbndb_lookup.py) and
    single GET responses (isbndb_search.py) — the record schema is the same.

    Returns a dict with keys RECORD_CSV_FIELDS. If include_synopsis is True, a
    'synopsis' key is appended containing the raw HTML synopsis field. Only
    present in GET responses; bulk POST responses do not carry this field.
    """

    def join(lst: list) -> str:
        return ",".join(str(x) for x in lst) if lst else ""

    isbn13 = record.get("isbn13") or record.get("isbn", "")
    isbn13_text = f"{isbn13}" if isbn13 else ""

    isbn10 = record.get("isbn10")
    isbn10_text = f"{isbn10}" if isbn10 else ""

    cover = record.get("image", "").strip()
    if not cover:
        cover = record.get("image_original", "").strip()

    structured = record.get("dimensions_structured") or {}
    height_cm, length_cm, width_cm, weight_kg = extract_dimensions(structured)

    row = {
        "isbn13":         isbn13_text,
        "found":          1,
        "title":          record.get("title", ""),
        "title_long":     record.get("title_long", ""),
        "authors":        join(record.get("authors", [])),
        "publisher":      record.get("publisher", ""),
        "date_published": record.get("date_published", ""),
        "edition":        record.get("edition", ""),
        "pages":          record.get("pages", ""),
        "binding":        record.get("binding", ""),
        "language":       record.get("language", ""),
        "dimensions":     record.get("dimensions", ""),
        "height_cm":      height_cm,
        "length_cm":      length_cm,
        "width_cm":       width_cm,
        "weight_kg":      weight_kg,
        "subjects":       join(record.get("subjects", [])),
        "cover_url":      cover,
        "dewey_decimal":  record.get("dewey_decimal", ""),
        "isbn10":         isbn10_text,
    }

    if include_synopsis:
        row["synopsis"] = record.get("synopsis", "")

    return row
