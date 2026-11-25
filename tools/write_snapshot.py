#!/usr/bin/env python3
"""
write_snapshot.py — Write the full catalogue to a re-importable xlsx snapshot.

Writes data/import/YYYYMMDD_HHMMSS_snapshot.xlsx containing every row from
book_current (plus tags), with headers matching FIELD_MAP exactly so the
file can be fed straight back into haddo_import after edits.

Usage:
    make snapshot      # macOS (or Windows Git Bash / MSYS2)
    python tools/write_snapshot.py

See snapshot_core.py and GOALS.md for the round-trip caveats (non-preferred
covers, revision history, and orphan tags are not preserved).
"""

import sys
from datetime import datetime
from pathlib import Path

from haddolib.database import DEFAULT_DB, connect
from haddolib.snapshot_core import write_snapshot

IMPORT_DIR = Path("data/import")


def main() -> None:
    db_path = Path(DEFAULT_DB)

    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}", file=sys.stderr)
        print("[ERROR] Run 'make bootstrap' first.", file=sys.stderr)
        sys.exit(1)

    if not IMPORT_DIR.exists():
        print(f"[ERROR] Output directory not found: {IMPORT_DIR}", file=sys.stderr)
        print(f"[ERROR] Create it manually: mkdir -p {IMPORT_DIR}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    filename = f"{now.strftime('%Y%m%d_%H%M%S')}_snapshot.xlsx"
    dest = IMPORT_DIR / filename

    print(f"[INFO] Source database : {db_path}")
    print(f"[INFO] Output file     : {dest}")

    try:
        conn = connect(str(db_path))
        count = write_snapshot(conn, dest, now)
        conn.close()
    except Exception as e:
        print(f"[ERROR] Snapshot failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Done. {count} book(s) written.")


if __name__ == "__main__":
    main()
