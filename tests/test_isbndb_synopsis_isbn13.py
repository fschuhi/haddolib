"""
tests/test_isbndb_synopsis_isbn13.py -- Tests for the pure helpers of
scripts/isbndb_synopsis_isbn13.py (newest_snapshot, read_isbn13s, chunks,
write_synopsis). The script lives outside the package, so it is loaded by path.
main() calls the network and is tested manually.
"""

import importlib.util
from pathlib import Path

import pytest
from openpyxl import Workbook

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "isbndb_synopsis_isbn13.py"
_spec = importlib.util.spec_from_file_location("isbndb_synopsis_isbn13", _SCRIPT)
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def _make_snapshot(path: Path, rows: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# newest_snapshot()
# ---------------------------------------------------------------------------

def test_newest_snapshot_picks_latest_timestamp(tmp_path) -> None:
    for name in ("20261104_101500_snapshot.xlsx", "20261126_191354_snapshot.xlsx",
                 "20260704_080000_snapshot.xlsx", "notes.xlsx", "books.lst"):
        (tmp_path / name).touch()
    assert script.newest_snapshot(tmp_path).name == "20261126_191354_snapshot.xlsx"


def test_newest_snapshot_ignores_lock_and_hidden_files(tmp_path) -> None:
    # Excel leaves ~$<name> while a snapshot is open; it sorts after the digits.
    for name in ("20261126_191354_snapshot.xlsx", "~$20261126_191354_snapshot.xlsx",
                 "._20261126_191354_snapshot.xlsx", "20261127_snapshot.xlsx"):
        (tmp_path / name).touch()
    assert script.newest_snapshot(tmp_path).name == "20261126_191354_snapshot.xlsx"


def test_newest_snapshot_none_found(tmp_path) -> None:
    (tmp_path / "books.lst").touch()
    with pytest.raises(FileNotFoundError):
        script.newest_snapshot(tmp_path)


# ---------------------------------------------------------------------------
# read_isbn13s()
# ---------------------------------------------------------------------------

def test_read_isbn13s_filters_by_source_and_isbn(tmp_path) -> None:
    path = _make_snapshot(tmp_path / "s.xlsx", [
        ["title", "revision_source", "isbn13"],              # columns in any order
        ["A", "isbndb", "9781538123898"],
        ["B", "not_in_isbndb", "9783451395840"],             # other source: dropped
        ["C", "isbndb", None],                               # no isbn13: dropped
        ["D", "isbndb", "  "],                               # blank isbn13: dropped
        ["E", "isbndb", "9780937938690"],
        ["F", "isbndb", "9781538123898"],                    # duplicate: dropped
    ])
    assert script.read_isbn13s(path) == ["9781538123898", "9780937938690"]


def test_read_isbn13s_accepts_text_and_number_cells(tmp_path) -> None:
    # Snapshots store isbn13 as text; a number cell (hand-edited sheet) still works.
    path = _make_snapshot(tmp_path / "s.xlsx", [
        ["isbn13", "revision_source"],
        ["9781538123898", "isbndb"],
        [9780937938690, "isbndb"],
    ])
    assert script.read_isbn13s(path) == ["9781538123898", "9780937938690"]


def test_read_isbn13s_keeps_leading_zero_text(tmp_path) -> None:
    path = _make_snapshot(tmp_path / "s.xlsx", [["isbn13", "revision_source"], ["0123456789012", "isbndb"]])
    assert script.read_isbn13s(path) == ["0123456789012"]


def test_read_isbn13s_missing_column(tmp_path) -> None:
    path = _make_snapshot(tmp_path / "s.xlsx", [["title", "isbn13"], ["A", "9781538123898"]])
    with pytest.raises(ValueError, match="revision_source"):
        script.read_isbn13s(path)


# ---------------------------------------------------------------------------
# chunks()
# ---------------------------------------------------------------------------

def test_chunks_splits_in_order() -> None:
    assert script.chunks(["a", "b", "c", "d", "e"], 2) == [["a", "b"], ["c", "d"], ["e"]]


def test_chunks_empty_and_exact() -> None:
    assert script.chunks([], 100) == []
    assert script.chunks(["a", "b"], 2) == [["a", "b"]]


# ---------------------------------------------------------------------------
# write_synopsis()
# ---------------------------------------------------------------------------

def test_write_synopsis_text_is_utf8_with_bom(tmp_path) -> None:
    path = tmp_path / "9781538123898.txt"
    script.write_synopsis(path, "Grüße aus Köln")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert path.read_text(encoding="utf-8-sig") == "Grüße aus Köln"


def test_write_synopsis_empty_is_zero_length(tmp_path) -> None:
    path = tmp_path / "9781538123898.txt"
    script.write_synopsis(path, "")
    assert path.exists() and path.stat().st_size == 0
