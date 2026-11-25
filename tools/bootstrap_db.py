#!/usr/bin/env python3
"""
bootstrap_db.py -- Initializes or resets the live SQLite database with the schema (DEFAULT_SCHEMA in database.py).
"""

import sys
from pathlib import Path

from haddolib.database import DEFAULT_DB, DEFAULT_SCHEMA, apply_schema, connect


def main() -> None:
    db_path = Path(DEFAULT_DB)
    
    print(f"[INFO] Target database: {db_path}")
    
    if db_path.exists():
        print(f"[WARN] Database file already exists: {db_path}")
        ans = input("       Are you sure you want to drop and completely re-create it? (y/N): ")
        if ans.strip().lower() not in ("y", "yes"):
            print("[INFO] Aborted by user.")
            sys.exit(0)
            
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