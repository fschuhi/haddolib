"""
tests/test_pdf_lst_to_queries.py — Tests for pdf_lst_to_queries.py's filename
parser (parse_filename) and *.lst reader (read_filenames).

Real-world cases below are drawn from an actual pdfs.lst run (5/5 parsed,
0 skipped) rather than invented from scratch -- the Umlaut and multi-word-
author cases in particular are genuine specimens, not synthetic ones.
"""

import io

import pytest

from scripts.pdf_lst_to_queries import parse_filename, read_filenames


# ---------------------------------------------------------------------------
# parse_filename() -- well-formed filenames
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename, expected",
    [
        (
            "(Köhler 1992) Gestalt Psychology.pdf",
            {"pdf_id": "(Köhler 1992)", "query": "Köhler: Gestalt Psychology", "year": "1992"},
        ),
        (
            "(Amrita Baba 2022) Awake.pdf",
            {"pdf_id": "(Amrita Baba 2022)", "query": "Amrita Baba: Awake", "year": "2022"},
        ),
        (
            "(Mipham 2016) A Garland of Views - A Guide to View, Meditation, and Result in the Nine Vehicles.pdf",
            {
                "pdf_id": "(Mipham 2016)",
                "query": "Mipham: A Garland of Views - A Guide to View, Meditation, and Result in the Nine Vehicles",
                "year": "2016",
            },
        ),
        (
            "(Dalai Lama+Thupten Jinpa 2009) The Union of Bliss and Emptiness.pdf",
            {
                "pdf_id": "(Dalai Lama+Thupten Jinpa 2009)",
                "query": "Dalai Lama+Thupten Jinpa: The Union of Bliss and Emptiness",
                "year": "2009",
            },
        ),
    ],
)
def test_parse_filename_well_formed(filename, expected) -> None:
    assert parse_filename(filename) == expected


def test_parse_filename_disambiguation_letter_stripped_from_year() -> None:
    # pdf_id keeps the disambiguation letter verbatim (it's the bibnote
    # filename stem); year drops it, since it's a uniqueness device only.
    row = parse_filename("(Longchenpa 2001a) The Precious Treasury of the Basic Space of Phenomena.pdf")
    assert row["pdf_id"] == "(Longchenpa 2001a)"
    assert row["year"] == "2001"


# ---------------------------------------------------------------------------
# parse_filename() -- malformed filenames
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename",
    [
        "Longchenpa 2001a The Precious Treasury.pdf",   # no parens at all
        "(Longchenpa) The Precious Treasury.pdf",        # no year in the parens
        "(Longchenpa 2001a) The Precious Treasury",      # missing .pdf extension
        "(Longchenpa 01a) The Precious Treasury.pdf",    # year not 4 digits
    ],
)
def test_parse_filename_malformed_returns_none(filename) -> None:
    assert parse_filename(filename) is None


# ---------------------------------------------------------------------------
# read_filenames()
# ---------------------------------------------------------------------------

def test_read_filenames_skips_blank_lines_and_comments() -> None:
    source = io.StringIO(
        "(Köhler 1992) Gestalt Psychology.pdf\n"
        "\n"
        "# a comment line\n"
        "(Amrita Baba 2022) Awake.pdf\n"
    )
    result = read_filenames(source)
    assert result == [
        (1, "(Köhler 1992) Gestalt Psychology.pdf"),
        (4, "(Amrita Baba 2022) Awake.pdf"),
    ]
