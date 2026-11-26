#!/usr/bin/env python3
"""
bootstrap_db.py -- Initializes or resets the live SQLite database with the schema (DEFAULT_SCHEMA in database.py).

Before an existing database is deleted, its whole catalogue is written to a
snapshot in data/import/. Changes that exist only in the database (e.g. tags
added in Excel since the last snapshot) would otherwise be lost when the
database is rebuilt from the sheets. If the snapshot cannot be written,
nothing is deleted.
"""

import sys
from datetime import datetime
from pathlib import Path

from haddolib.database import DEFAULT_DB, DEFAULT_SCHEMA, apply_schema, connect
from haddolib.snapshot_core import write_snapshot

IMPORT_DIR = Path("data/import")


def main() -> None:
    db_path = Path(DEFAULT_DB)
    
    print(f"[INFO] Target database: {db_path}")
    
    if db_path.exists():
        print(f"[WARN] Database file already exists: {db_path}")
        ans = input("       Are you sure you want to drop and completely re-create it? (y/N): ")
        if ans.strip().lower() not in ("y", "yes"):
            print("[INFO] Aborted by user.")
            sys.exit(0)
            
        # Safety net: the +/- cycle rebuilds the database from the sheets, so
        # whatever exists only in the database has to be saved first.
        if not IMPORT_DIR.exists():
            print(f"[ERROR] Output directory not found: {IMPORT_DIR}", file=sys.stderr)
            print(f"[ERROR] Create it manually: mkdir -p {IMPORT_DIR}", file=sys.stderr)
            print("[ERROR] Database NOT deleted.", file=sys.stderr)
            sys.exit(1)

        now = datetime.now()
        snapshot_path = IMPORT_DIR / f"{now.strftime('%Y%m%d_%H%M%S')}_snapshot.xlsx"
        try:
            old_conn = connect(str(db_path))
            count = write_snapshot(old_conn, snapshot_path, now)
            old_conn.close()
        except Exception as e:
            print(f"[ERROR] Snapshot failed: {e}", file=sys.stderr)
            print("[ERROR] Database NOT deleted.", file=sys.stderr)
            sys.exit(1)
        print(f"[INFO] Snapshot written: {snapshot_path} ({count} book(s))")

        try:
            db_path.unlink()
            print(f"[INFO] Existing database deleted.")
        except OSError as e:
            print(f"[ERROR] Could not delete existing database: {e}", file=sys.stderr)
            sys.exit(1)

    if not DEFAULT_SCHEMA.exists():
        print(f"[ERROR] Schema file not found: {DEFAULT_SCHEMA}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Ensuring directory structure exists...")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Connecting and applying schema from {DEFAULT_SCHEMA}...")
    try:
        conn = connect(str(db_path))
        apply_schema(conn)
        conn.close()
    except Exception as e:
        print(f"[ERROR] Failed to apply schema: {e}", file=sys.stderr)
        sys.exit(1)

    print("[INFO] Bootstrap complete. Database is ready.")


if __name__ == "__main__":
    main()