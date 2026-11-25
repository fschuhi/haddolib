"""
tests/test_common_coercion.py -- The value-coercion helpers in common.py.

These cover the contract the roster mapping leans on but doesn't exercise
directly: the int(float(...)) string path, and the "raise loudly on a
German-comma string" promise (locale parsing is the CSV layer's job, not these).

If you prefer one-file-per-module, these fold cleanly into test_common.py.
"""

import pytest

from haddolib.common import as_int, as_real, as_text


def test_as_text_trims_and_nulls_blank() -> None:
    assert as_text("  hi  ") == "hi"
    assert as_text("") is None
    assert as_text("   ") is None
    assert as_text(None) is None
    assert as_text(123) == "123"          # non-string coerced via str()


def test_as_int_native_float_path() -> None:
    # The real PyXLL path: whole numbers arrive as floats.
    assert as_int(946.0) == 946
    assert isinstance(as_int(946.0), int)
    assert as_int(0) == 0


def test_as_int_string_and_blank() -> None:
    assert as_int("946") == 946
    assert as_int("946.0") == 946         # stray decimal string still works
    assert as_int("") is None
    assert as_int(None) is None


def test_as_int_german_comma_raises_loudly() -> None:
    with pytest.raises(ValueError):
        as_int("1,2927")                  # locale parsing is NOT this layer's job


def test_as_real_native_and_string() -> None:
    assert as_real(19.5) == 19.5
    assert as_real(3) == 3.0 and isinstance(as_real(3), float)
    assert as_real("0.4") == 0.4
    assert as_real("") is None
    assert as_real(None) is None


def test_as_real_german_comma_raises_loudly() -> None:
    with pytest.raises(ValueError):
        as_real("1,5")
