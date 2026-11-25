#!/usr/bin/env python3
"""
catalog.py — the pure handle catalog for haddolib's read-path crossings.

A small, stateful store mapping opaque handle strings to Python objects, with
TTL-based eviction. It is the haddolib-owned alternative to PyXLL's transient
object cache (whose TTL semantics proved unsuitable for stateful VBA loops):
plain-string handles are first-class Excel/VBA values — storable in variables,
cells, or dictionaries — with no PyXLL-specific lifetime rules.

This module is PURE: stdlib only, no PyXLL, no Excel, no database. It is fully
unit-testable on macOS. The thin @xl_func wrappers in pyxll_bridge.py hold one
module-level HandleCatalog instance and do the Excel/VBA marshalling around it.

Handle format:  haddo:{session_id}:{kind}:{16-byte hex token}
  The session_id (generated once per catalog instance — i.e. once per Python
  session in production) makes stale handles from a previous PyXLL reload carry
  a different prefix, so they are immediately recognisable.

Concurrency:
  Every public method takes a per-instance RLock, so the catalog is safe to use
  from whatever threads PyXLL/Excel may call it on.

Testability (the reason this is a class, not module globals):
  - now_fn is injectable, so sweep() and last-accessed bookkeeping are tested
    deterministically by advancing a fake clock — no sleep().
  - Each HandleCatalog instance owns its own state, so tests never bleed into
    one another through a module global.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from secrets import token_hex
from threading import RLock
from typing import Any, Callable


@dataclass
class _Entry:
    """One stored catalog entry. Internal — callers read data via get()/snapshot()."""

    kind: str
    created_at: datetime
    last_accessed_at: datetime
    data: Any


class HandleCatalog:
    """Opaque-handle store with TTL eviction. Pure; stdlib only.

    Parameters
    ----------
    session_id:
        Prefix component embedded in every handle. Defaults to a fresh 4-byte
        hex token, so each instance (each Python session) is distinguishable and
        handles minted before a PyXLL reload are obviously stale afterwards.
    now_fn:
        Clock used for created_at / last_accessed_at / sweep cutoffs. Defaults to
        datetime.now; tests inject a controllable clock for determinism.
    default_ttl_seconds:
        The fallback max-age used by sweep() when no explicit age is given.
    """

    def __init__(
        self,
        *,
        session_id: str | None = None,
        now_fn: Callable[[], datetime] = datetime.now,
        default_ttl_seconds: int = 600,
    ) -> None:
        self.session_id: str = session_id if session_id is not None else token_hex(4)
        self.default_ttl_seconds: int = default_ttl_seconds
        self._now_fn: Callable[[], datetime] = now_fn
        self._entries: dict[str, _Entry] = {}
        self._lock: RLock = RLock()

    # -- handle minting -----------------------------------------------------

    def _new_handle(self, kind: str) -> str:
        return f"haddo:{self.session_id}:{kind}:{token_hex(16)}"

    # -- core operations ----------------------------------------------------

    def put(self, kind: str, data: Any) -> str:
        """Store data under a fresh handle and return the handle string."""
        handle = self._new_handle(kind)
        now = self._now_fn()
        with self._lock:
            self._entries[handle] = _Entry(
                kind=kind,
                created_at=now,
                last_accessed_at=now,
                data=data,
            )
        return handle

    def get(self, handle: str, expected_kind: str | None = None) -> Any:
        """Return stored data, refreshing last_accessed_at.

        Raises KeyError if the handle is unknown or already released, and
        TypeError if expected_kind is given and does not match the stored kind.
        """
        with self._lock:
            entry = self._entries.get(handle)
            if entry is None:
                raise KeyError(f"Unknown or released haddo handle: {handle!r}")
            if expected_kind is not None and entry.kind != expected_kind:
                raise TypeError(
                    f"Handle {handle!r} is kind {entry.kind!r}, "
                    f"expected {expected_kind!r}"
                )
            entry.last_accessed_at = self._now_fn()
            return entry.data

    def release(self, handle: str) -> bool:
        """Remove a handle. Returns True if it existed, False otherwise."""
        with self._lock:
            return self._entries.pop(handle, None) is not None

    def replace(self, handle: str, data: Any) -> None:
        """Replace the data stored under an existing handle in place.

        Updates last_accessed_at to now. The handle string is unchanged —
        callers (VBA) hold the same string and see fresh data on the next
        get() call.

        Raises KeyError if the handle is unknown or already released.
        """
        with self._lock:
            entry = self._entries.get(handle)
            if entry is None:
                raise KeyError(f"Unknown or released haddo handle: {handle!r}")
            entry.data = data
            entry.last_accessed_at = self._now_fn()

    def sweep(self, max_age_seconds: int | None = None) -> int:
        """Evict entries not accessed within max_age_seconds. Returns the count.

        When max_age_seconds is None, default_ttl_seconds is used — so the
        wrapper can simply call sweep() and let the catalog own the default.
        """
        if max_age_seconds is None:
            max_age_seconds = self.default_ttl_seconds
        cutoff = self._now_fn() - timedelta(seconds=max_age_seconds)
        with self._lock:
            stale = [
                h for h, e in self._entries.items()
                if e.last_accessed_at < cutoff
            ]
            for h in stale:
                del self._entries[h]
        return len(stale)

    # -- diagnostics --------------------------------------------------------

    def snapshot(self) -> list[dict]:
        """Return a consistent point-in-time view of all entries.

        Each element is a dict with keys: handle, kind, created_at,
        last_accessed_at, size. created_at / last_accessed_at are raw datetimes
        and size is len(data) (or None when data has no length) — the PyXLL
        wrapper formats these for the worksheet (isoformat, blank for None).
        Built under the lock, so it is a coherent snapshot.
        """
        with self._lock:
            out: list[dict] = []
            for handle, entry in self._entries.items():
                try:
                    size: int | None = len(entry.data)
                except TypeError:
                    size = None
                out.append(
                    {
                        "handle": handle,
                        "kind": entry.kind,
                        "created_at": entry.created_at,
                        "last_accessed_at": entry.last_accessed_at,
                        "size": size,
                    }
                )
            return out

    def __len__(self) -> int:
        """Number of live entries (handy for tests and quick introspection)."""
        with self._lock:
            return len(self._entries)
