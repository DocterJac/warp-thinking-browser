#!/usr/bin/env python3
"""
capture_fixture.py
──────────────────
Capture a sample task blob from the Warp database and save it as a test
fixture. Run this once to create the fixture that the parity tests use.

Usage:
    python3 tests/capture_fixture.py
    python3 tests/capture_fixture.py --db /path/to/warp.sqlite
    python3 tests/capture_fixture.py --with-thinking   # prefer a task that has thinking

Output:
    tests/fixtures/sample_task.bin
"""

import argparse
import os
import platform
import sqlite3
import sys

FIXTURE_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
FIXTURE_PATH = os.path.join(FIXTURE_DIR, "sample_task.bin")


def default_db_path():
    system = platform.system()
    if system == "Darwin":
        return os.path.expanduser(
            "~/Library/Group Containers/2BBY89MBSN.dev.warp"
            "/Library/Application Support/dev.warp.Warp-Stable/warp.sqlite"
        )
    elif system == "Linux":
        xdg = os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state"))
        return os.path.join(xdg, "warp-terminal", "warp.sqlite")
    elif system == "Windows":
        local = os.environ.get("LOCALAPPDATA", "")
        return os.path.join(local, "warp", "Warp", "data", "warp.sqlite")
    return None


def main():
    parser = argparse.ArgumentParser(description="Capture a Warp task blob as a test fixture.")
    parser.add_argument("--db", metavar="PATH", help="Path to warp.sqlite")
    parser.add_argument("--with-thinking", action="store_true",
                        help="Prefer a task with large blob (likely to contain thinking)")
    args = parser.parse_args()

    db_path = os.path.expanduser(args.db) if args.db else default_db_path()
    if not db_path or not os.path.exists(db_path):
        print(f"  Database not found: {db_path or '(could not detect)'}")
        sys.exit(1)

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    if args.with_thinking:
        # Pick the largest recent blob — more likely to contain thinking
        row = con.execute(
            "SELECT task_id, length(task), task FROM agent_tasks "
            "ORDER BY length(task) DESC LIMIT 1"
        ).fetchone()
    else:
        # Pick the most recent task
        row = con.execute(
            "SELECT task_id, length(task), task FROM agent_tasks "
            "ORDER BY last_modified_at DESC LIMIT 1"
        ).fetchone()

    con.close()

    if not row:
        print("  No tasks found in the database.")
        sys.exit(1)

    tid, size, blob = row
    os.makedirs(FIXTURE_DIR, exist_ok=True)

    with open(FIXTURE_PATH, "wb") as f:
        f.write(bytes(blob))

    print(f"  Captured task {tid} ({size / 1024:.1f} KB)")
    print(f"  Saved → {FIXTURE_PATH}")


if __name__ == "__main__":
    main()
