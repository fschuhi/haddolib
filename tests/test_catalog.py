"""
tests/test_catalog.py — Tests for the pure handle catalog (catalog.py).

These tests ARE the spec for HandleCatalog. The catalog is pure (stdlib only,
no PyXLL / Excel / DB), so everything here runs on macOS. A controllable clock
is injected so TTL and last-accessed behaviour is tested deterministically —
no sleep().

Each test builds its own HandleCatalog instance: the catalog owns its state
per-instance, so nothing bleeds between tests.
"""

import threading
from datetime import datetime, timedelta

import pytest

from haddolib.catalog import HandleCatalog


# ---------------------------------------------------------------------------
# Controllable clock
# ---------------------------------------------------------------------------

class FakeClock:
    """A settable clock. now() returns the current value; advance() moves it."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 6, 20, 12, 0, 0)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def catalog(clock) -> HandleCatalog:
    """A catalog with a fixed session id and the fake clock injected."""
    return HandleCatalog(session_id="testsess", now_fn=clock.now)


# ---------------------------------------------------------------------------
# Handle format & uniqueness
# ---------------------------------------------------------------------------

def test_handle_has_expected_format(catalog) -> None:
    handle = catalog.put("books_by_bin", [{"title": "A"}])
    # haddo:{session_id}:{kind}:{token}
    assert handle.startswith("haddo:testsess:books_by_bin:")
    parts = handle.split(":")
    assert len(parts) == 4
    assert parts[0] == "haddo"
    assert len(parts[3]) == 32          # token_hex(16) → 32 hex chars


def test_handles_are_unique(catalog) -> None:
    handles = {catalog.put("books_by_bin", []) for _ in range(100)}
    assert len(handles) == 100


def test_default_session_id_is_generated() -> None:
    # No session_id given → a non-empty 4-byte hex prefix is minted.
    cat = HandleCatalog()
    handle = cat.put("books_by_bin", [])
    prefix = handle.split(":")[1]
    assert len(prefix) == 8             # token_hex(4) → 8 hex chars


# ---------------------------------------------------------------------------
# put / get round-trip
# ---------------------------------------------------------------------------

def test_put_then_get_returns_same_object(catalog) -> None:
    data = [{"title": "A"}, {"title": "B"}]
    handle = catalog.put("books_by_bin", data)
    assert catalog.get(handle) is data


def test_get_unknown_handle_raises_keyerror(catalog) -> None:
    with pytest.raises(KeyError, match="Unknown or released"):
        catalog.get("haddo:testsess:books_by_bin:deadbeef")


def test_get_wrong_kind_raises_typeerror(catalog) -> None:
    handle = catalog.put("books_by_bin", [])
    with pytest.raises(TypeError, match="expected 'cover_list'"):
        catalog.get(handle, expected_kind="cover_list")


def test_get_matching_kind_succeeds(catalog) -> None:
    handle = catalog.put("books_by_bin", [{"x": 1}])
    assert catalog.get(handle, expected_kind="books_by_bin") == [{"x": 1}]


# ---------------------------------------------------------------------------
# last_accessed bookkeeping (deterministic via the fake clock)
# ---------------------------------------------------------------------------

def test_get_refreshes_last_accessed(catalog, clock) -> None:
    handle = catalog.put("books_by_bin", [])
    [entry] = catalog.snapshot()
    created = entry["last_accessed_at"]
    clock.advance(120)
    catalog.get(handle)
    [entry2] = catalog.snapshot()
    assert entry2["last_accessed_at"] == created + timedelta(seconds=120)


# ---------------------------------------------------------------------------
# replace
# ---------------------------------------------------------------------------

def test_replace_updates_stored_data(catalog) -> None:
    old_data = [{"title": "A"}]
    new_data = [{"title": "B"}, {"title": "C"}]
    handle = catalog.put("books_by_bin", old_data)
    catalog.replace(handle, new_data)
    assert catalog.get(handle) is new_data


def test_replace_refreshes_last_accessed(catalog, clock) -> None:
    handle = catalog.put("books_by_bin", [])
    clock.advance(120)
    catalog.replace(handle, [{"title": "fresh"}])
    [entry] = catalog.snapshot()
    assert entry["last_accessed_at"] == clock.now()


def test_replace_unknown_handle_raises_keyerror(catalog) -> None:
    with pytest.raises(KeyError, match="Unknown or released"):
        catalog.replace("haddo:testsess:books_by_bin:deadbeef", [])


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------

def test_release_existing_returns_true(catalog) -> None:
    handle = catalog.put("books_by_bin", [])
    assert catalog.release(handle) is True


def test_release_is_idempotent(catalog) -> None:
    handle = catalog.put("books_by_bin", [])
    assert catalog.release(handle) is True
    assert catalog.release(handle) is False   # already gone


def test_get_after_release_raises(catalog) -> None:
    handle = catalog.put("books_by_bin", [])
    catalog.release(handle)
    with pytest.raises(KeyError):
        catalog.get(handle)


# ---------------------------------------------------------------------------
# sweep (deterministic via the fake clock)
# ---------------------------------------------------------------------------

def test_sweep_evicts_stale_entries(catalog, clock) -> None:
    old = catalog.put("books_by_bin", [])
    clock.advance(700)                       # 'old' last accessed 700s ago
    fresh = catalog.put("books_by_bin", [])  # 'fresh' accessed now
    evicted = catalog.sweep(600)
    assert evicted == 1
    assert catalog.release(fresh) is True    # fresh survived
    with pytest.raises(KeyError):
        catalog.get(old)                     # old is gone


def test_sweep_keeps_recently_accessed(catalog, clock) -> None:
    handle = catalog.put("books_by_bin", [])
    clock.advance(700)
    catalog.get(handle)                      # refresh: last_accessed = now
    assert catalog.sweep(600) == 0           # back inside the window
    assert catalog.release(handle) is True


def test_sweep_empty_catalog_returns_zero(catalog) -> None:
    assert catalog.sweep(600) == 0


def test_sweep_uses_default_ttl_when_none(clock) -> None:
    cat = HandleCatalog(session_id="t", now_fn=clock.now, default_ttl_seconds=300)
    cat.put("books_by_bin", [])
    clock.advance(301)
    assert cat.sweep() == 1                   # 300s default window, 301s old → evicted


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

def test_snapshot_empty_when_no_entries(catalog) -> None:
    assert catalog.snapshot() == []


def test_snapshot_reports_kind_and_size(catalog) -> None:
    catalog.put("books_by_bin", [{"a": 1}, {"b": 2}, {"c": 3}])
    [entry] = catalog.snapshot()
    assert entry["kind"] == "books_by_bin"
    assert entry["size"] == 3
    assert isinstance(entry["created_at"], datetime)
    assert isinstance(entry["last_accessed_at"], datetime)


def test_snapshot_size_none_for_unsized_data(catalog) -> None:
    catalog.put("scalar", 42)                # int has no len()
    [entry] = catalog.snapshot()
    assert entry["size"] is None


# ---------------------------------------------------------------------------
# instances are independent (the anti-bleed property)
# ---------------------------------------------------------------------------

def test_instances_do_not_share_state(clock) -> None:
    a = HandleCatalog(session_id="a", now_fn=clock.now)
    b = HandleCatalog(session_id="b", now_fn=clock.now)
    handle = a.put("books_by_bin", [{"x": 1}])
    assert len(a) == 1
    assert len(b) == 0
    with pytest.raises(KeyError):
        b.get(handle)                        # b never saw a's handle


# ---------------------------------------------------------------------------
# concurrency smoke (the lock must not deadlock or corrupt under contention)
# ---------------------------------------------------------------------------

def test_concurrent_put_get_release_is_safe(catalog) -> None:
    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(50):
                h = catalog.put("books_by_bin", [1, 2, 3])
                assert catalog.get(h) == [1, 2, 3]
                catalog.release(h)
        except Exception as exc:  # pragma: no cover - only on failure
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(catalog) == 0                  # every put was released
