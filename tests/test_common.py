"""
tests/test_common.py -- Tests for shared ISBN validation utilities in common.py.

These tests serve as a living specification for what constitutes a valid ISBN.
Real ISBNs from the Magazin collection are used as positive cases where possible.

ISBN-13 checksum: weights 1,3,1,3,... over first 12 digits;
  check digit = (10 - sum % 10) % 10

ISBN-10 checksum: sum of (position * digit) for positions 1-9;
  check digit = sum % 11  (digit or X for 10)
"""

import pytest
from haddolib.common import is_valid_isbn, is_valid_isbn10, is_valid_isbn13, isbn10_to_isbn13


# ---------------------------------------------------------------------------
# ISBN-13 -- valid
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("isbn", [
    # Real books from the Magazin -- confirmed valid by checksum
    "9783589238446",
    "9783821816838",
    "9783821816814",
    "9783442164998",
    "9783442167395",
    "9781785040481",
    "9780141040011",
    # Valid ISBNs not found in ISBNdb -- checksum still correct
    "9783800619672",
    "9783596509096",
    # Hyphens and spaces must be stripped before validation
    "978-3-442-16499-8",
    "978 3 442 16499 8",
    # 979 prefix is also valid for ISBN-13
    "9791032305690",
])
def test_isbn13_valid(isbn: str) -> None:
    assert is_valid_isbn13(isbn), f"Expected {isbn!r} to be a valid ISBN-13"


# ---------------------------------------------------------------------------
# ISBN-13 -- invalid
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("isbn, reason", [
    # Wrong check digit (last digit flipped)
    ("9783589238447", "wrong check digit"),
    ("9780141040012", "wrong check digit"),
    # Invalid prefix
    ("9773589238440", "prefix 977 is not valid"),
    ("9763589238449", "prefix 976 is not valid"),
    # Too short / too long
    ("978358923844",  "only 12 digits"),
    ("97835892384460", "14 digits"),
    # Non-numeric characters
    ("978358923844X", "X not valid in ISBN-13"),
    ("97835892A8446", "letter in body"),
    # Empty and whitespace-only
    ("",              "empty string"),
    ("   ",           "whitespace only"),
    # Looks like ISBN-10
    ("3930799324",    "ISBN-10 is not ISBN-13"),
])
def test_isbn13_invalid(isbn: str, reason: str) -> None:
    assert not is_valid_isbn13(isbn), f"Expected {isbn!r} to be invalid ({reason})"


# ---------------------------------------------------------------------------
# ISBN-10 -- valid
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("isbn", [
    # Real books from the Magazin
    "3930799324",
    "3897490005",
    "389749003X",   # X as check digit (= 10)
    "042513699X",   # X as check digit, different publisher prefix
    # Hyphens must be stripped
    "3-897490-00-5",
    # Lowercase x should also be accepted (stripped and uppercased)
    "389749003x",
])
def test_isbn10_valid(isbn: str) -> None:
    assert is_valid_isbn10(isbn), f"Expected {isbn!r} to be a valid ISBN-10"


# ---------------------------------------------------------------------------
# ISBN-10 -- invalid
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("isbn, reason", [
    # Wrong check digit
    ("3930799325",   "wrong check digit"),
    ("3897490006",   "wrong check digit"),
    # X in wrong position
    ("39307X9324",   "X in position 6, not allowed there"),
    # Too short / too long
    ("393079932",    "only 9 digits"),
    ("39307993240",  "11 digits"),
    # Non-numeric in first 9
    ("39A079932B",   "letters in body"),
    # Empty
    ("",             "empty string"),
    # Looks like ISBN-13
    ("9783589238446", "ISBN-13 is not ISBN-10"),
])
def test_isbn10_invalid(isbn: str, reason: str) -> None:
    assert not is_valid_isbn10(isbn), f"Expected {isbn!r} to be invalid ({reason})"


# ---------------------------------------------------------------------------
# is_valid_isbn -- combined wrapper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("isbn", [
    "9783589238446",   # valid ISBN-13
    "9780141040011",   # valid ISBN-13
    "3930799324",      # valid ISBN-10
    "389749003X",      # valid ISBN-10 with X
    "978-3-442-16499-8",  # hyphens stripped
])
def test_is_valid_isbn_accepts_both(isbn: str) -> None:
    assert is_valid_isbn(isbn), f"Expected {isbn!r} to be accepted by is_valid_isbn"


@pytest.mark.parametrize("isbn, reason", [
    ("9783589238447", "invalid ISBN-13"),
    ("3930799325",    "invalid ISBN-10"),
    ("1234567890123", "13 digits but wrong prefix and check"),
    ("",              "empty string"),
])
def test_is_valid_isbn_rejects_invalid(isbn: str, reason: str) -> None:
    assert not is_valid_isbn(isbn), f"Expected {isbn!r} to be rejected ({reason})"


# ---------------------------------------------------------------------------
# isbn10_to_isbn13 -- conversion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("isbn10, expected_isbn13", [
    # Real Magazin books -- verified pairs
    ("3892282358", "9783892282358"),
    ("3100432088", "9783100432087"),
    ("3891365276", "9783891365274"),
    # Existing Magazin ISBN-10s from the validation tests above
    ("3930799324", "9783930799329"),
    ("3897490005", "9783897490000"),
    ("389749003X", "9783897490031"),
])
def test_isbn10_to_isbn13(isbn10: str, expected_isbn13: str) -> None:
    result = isbn10_to_isbn13(isbn10)
    assert result == expected_isbn13, f"isbn10_to_isbn13({isbn10!r}) = {result!r}, expected {expected_isbn13!r}"
    # Converted result must also pass ISBN-13 validation
    assert is_valid_isbn13(result), f"Converted {result!r} does not pass ISBN-13 validation"
