"""
tests/test_isbndb_utils.py — Tests for the ISBNdb selection helpers
(extract_year, select_best_matching_year) in isbndb_utils.py.

extract_dimensions() and extract_record() are not yet covered here — this
file targets only the new year-aware selection logic added this session.

The two-edition fixture below is a trimmed real API response (query: "Dalai
Lama+Thupten Jinpa: The Union of Bliss and Emptiness", no year param), kept
as a genuine specimen rather than a synthetic one: two real editions of the
same book, 21 years apart, neither with a placeholder cover.
"""

import pytest

from haddolib.isbndb_utils import extract_year, select_best_matching_year

# ---------------------------------------------------------------------------
# Fixture: real two-edition API response (year param omitted), trimmed to
# the fields select_best_matching_year() and select_best() actually read.
# ---------------------------------------------------------------------------

_SHAMBHALA_2009 = {
    "title": "The Union of Bliss and Emptiness Teachings on the Practice of Guru Yoga",
    "isbn13": "9781559393218",
    "date_published": "2009-04-16",
    "image": "https://images.isbndb.com/covers/5410213482743.jpg",
}

_SNOW_LION_1988 = {
    "title": "The Union of Bliss and Emptiness: A Commentary on Guru Yoga Practice",
    "isbn13": "9780937938690",
    "date_published": "1988-01-01",
    "image": "https://images.isbndb.com/covers/25910313482521.jpg",
}

_TWO_EDITIONS = [_SHAMBHALA_2009, _SNOW_LION_1988]


# ---------------------------------------------------------------------------
# extract_year()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "date_published, expected_year",
    [
        ("", ""),
        ("1991", "1991"),
        ("2007-05", "2007"),
        ("2006-05-02", "2006"),
    ],
)
def test_extract_year(date_published, expected_year) -> None:
    assert extract_year(date_published) == expected_year


# ---------------------------------------------------------------------------
# select_best_matching_year()
# ---------------------------------------------------------------------------

def test_select_best_matching_year_finds_match() -> None:
    # Only the Shambhala 2009 edition matches -- it's selected, and
    # year_matched confirms the match rather than a coincidental first-pick.
    record, year_matched = select_best_matching_year(_TWO_EDITIONS, "2009")
    assert record["isbn13"] == "9781559393218"
    assert year_matched == "2009"


def test_select_best_matching_year_falls_back_when_year_absent() -> None:
    # Neither edition is from 1975 -- falls back to select_best() over the
    # full list, which returns the first record (neither cover is a
    # placeholder). year_matched is empty: the pick is not year-backed.
    record, year_matched = select_best_matching_year(_TWO_EDITIONS, "1975")
    assert record["isbn13"] == "9781559393218"
    assert year_matched == ""


def test_select_best_matching_year_empty_records() -> None:
    assert select_best_matching_year([], "2009") == (None, "")


def test_select_best_matching_year_no_year_requested() -> None:
    # A falsy year skips filtering entirely -- same fallback path as the
    # year-absent case above, exercised via the empty-string input that
    # isbn_synopsis.py would pass when year_searched is unknown.
    record, year_matched = select_best_matching_year(_TWO_EDITIONS, "")
    assert record["isbn13"] == "9781559393218"
    assert year_matched == ""
