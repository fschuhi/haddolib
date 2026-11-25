#!/usr/bin/env python3
"""
backup_db.py — Safely backs up the live SQLite database and its directory.

Uses sqlite3's native backup API to ensure consistency even if the DB is active.
Creates a timestamped subfolder in each provided destination root.
"""

import argparse
import datetime
import shutil
import sqlite3
import sys
from pathlib import Path

from haddolib.database import DEFAULT_DB


def backup_to_destination(src_db: Path, dest_root: Path, timestamp: str) -> bool:
    if not dest_root.exists():
        print(f"[WARN] Destination root does not exist (unmounted?): {dest_root}", file=sys.stderr)
        return False

    target_dir = dest_root / timestamp
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[ERROR] Could not create timestamp directory {target_dir}: {e}", file=sys.stderr)
        return False

    print(f"[INFO] Backing up to {target_dir} ...")

    # 1. Safely backup the SQLite database using the native API
    target_db = target_dir / src_db.name
    try:
        with sqlite3.connect(src_db) as src, sqlite3.connect(target_db) as dst:
            src.backup(dst)
        print(f"       -> Database copied safely.")
    except sqlite3.Error as e:
        print(f"[ERROR] SQLite backup failed: {e}", file=sys.stderr)
        return False

    # 2. Copy any other files in the source directory (e.g., config, logs)
    src_dir = src_db.parent
    for item in src_dir.iterdir():
        if item.is_file() and item.name != src_db.name:
            try:
                shutil.copy2(item, target_dir / item.name)
                print(f"       -> Copied {item.name}")
            except OSError as e:
                print(f"[WARN] Failed to copy {item.name}: {e}", file=sys.stderr)

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely backup the live SQLite database.")
    parser.add_argument(
        "--dest",
        action="append",
        required=True,
        help="Destination root folder (can be specified multiple times)"
    )
    args = parser.parse_args()

    src_db = Path(DEFAULT_DB)
    if not src_db.exists():
        print(f"[ERROR] Source database not found: {src_db}", file=sys.stderr)
        sys.exit(1)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"[INFO] Starting backup run for timestamp: {timestamp}")

    success_count = 0
    for d in args.dest:
        if backup_to_destination(src_db, Path(d), timestamp):
            success_count += 1

    if success_count == 0:
        print("[ERROR] All backup attempts failed.", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"[INFO] Backup complete. Successful destinations: {success_count}/{len(args.dest)}")


if __name__ == "__main__":
    main()