#!/usr/bin/env python3
"""
warp_thinking_watch.py
──────────────────────
Background daemon that watches the Warp SQLite database for new or updated
agent tasks and automatically exports any thinking blocks to timestamped log
files — one file per task, written as soon as the task is detected.

No guesswork. Uses the same definitive field-15 protobuf probe as the browser
tool. Only tasks that actually contain thinking text produce a log file.

Sections:
    Protobuf (shared)   — wire-format parser, keep in sync across scripts
    DB shared           — default_db_path, _extract_query_text
    DB watch-specific   — get_recent_tasks
    File output         — log file writing
    Watch loop          — polling daemon
    Entry point         — main()

Usage:
    python3 warp_thinking_watch.py                         # log to ./warp_thinking_logs/
    python3 warp_thinking_watch.py --out ~/research/logs   # custom output directory
    python3 warp_thinking_watch.py --db /path/to/warp.sqlite --out ~/logs
    python3 warp_thinking_watch.py --help

Run as a background process:
    nohup python3 warp_thinking_watch.py --out ~/warp_thinking_logs &

Or install as a launchd service on macOS — see README for plist.

Output files:
    One .txt file per task that contains thinking, named:
        YYYYMMDD_HHMMSS_<task_title_slug>.txt

    Each file contains:
        - Conversation title and ID
        - Task title and ID
        - Timestamp
        - All thinking blocks, numbered and separated

Requirements: Python 3.7+, no third-party packages.
"""

import argparse
import json
import os
import platform
import sqlite3
import sys
import textwrap
import time
from datetime import datetime

# ── Protobuf parser (shared — keep in sync across all three scripts) ──────────

def read_varint(data, pos):
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos

def parse_fields(data):
    pos, fields = 0, []
    while pos < len(data):
        try:
            tag, pos = read_varint(data, pos)
            fn, wt = tag >> 3, tag & 0x7
            if wt == 0:
                v, pos = read_varint(data, pos)
                fields.append((fn, 0, v))
            elif wt == 2:
                ln, pos = read_varint(data, pos)
                if pos + ln > len(data):
                    break
                fields.append((fn, 2, data[pos:pos + ln]))
                pos += ln
            elif wt == 1:
                fields.append((fn, 1, data[pos:pos + 8])); pos += 8
            elif wt == 5:
                fields.append((fn, 5, data[pos:pos + 4])); pos += 4
            else:
                break
        except Exception:
            break
    return fields

def decode_string(data):
    """Return decoded UTF-8 string or None."""
    try:
        return data.decode("utf-8")
    except Exception:
        return None

def task_title_from_blob(blob):
    for fn, wt, val in parse_fields(bytes(blob)):
        if fn == 2 and wt == 2:
            text = decode_string(val)
            if text:
                return text
    return "(untitled)"

def blob_has_thinking(blob):
    """
    Definitive check: returns True only if field-15 content with readable
    UTF-8 text of >10 bytes exists in at least one step of the task blob.
    Stops at the first confirmation — fast enough for polling.
    """
    for fn, wt, val in parse_fields(bytes(blob)):
        if fn != 5 or wt != 2:
            continue
        for sfn, swt, sval in parse_fields(val):
            if sfn != 15 or swt != 2:
                continue
            for _, twt, tval in parse_fields(sval):
                if twt == 2 and len(tval) > 10 and decode_string(tval) is not None:
                    return True
    return False

def extract_thinking(blob):
    """Return [{step_id, thinking}] for all thinking blocks in a task blob."""
    blocks = []
    for fn, wt, val in parse_fields(bytes(blob)):
        if fn != 5 or wt != 2:
            continue
        step_id, chunks = None, []
        for sfn, swt, sval in parse_fields(val):
            if sfn == 1 and swt == 2:
                step_id = decode_string(sval)
            elif sfn == 15 and swt == 2:
                for _, twt, tval in parse_fields(sval):
                    if twt == 2:
                        text = decode_string(tval)
                        if text and len(text) > 10:
                            chunks.append(text)
        if chunks:
            blocks.append({"step_id": step_id, "thinking": "\n".join(chunks)})
    return blocks

# ── DB helpers (shared — keep in sync across all three scripts) ──────────────

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

# ── DB helpers (watch-specific) ───────────────────────────────────────────────

def get_recent_tasks(db_path, limit=2000):
    """
    Return the most recently modified tasks from the database.
    Caller is responsible for filtering by seen state.
    Opens the database read-only so it cannot affect Warp.
    """
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        rows = con.execute("""
            SELECT
                at.task_id,
                at.conversation_id,
                at.last_modified_at,
                at.task,
                (
                    SELECT aq.input
                    FROM ai_queries aq
                    WHERE aq.conversation_id = at.conversation_id
                    ORDER BY aq.start_ts ASC
                    LIMIT 1
                ) AS first_query
            FROM agent_tasks at
            ORDER BY at.last_modified_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        con.close()
    except Exception as e:
        return [], str(e)

    tasks = []
    for tid, cid, ts, blob, fq in rows:
        conv_title = _extract_query_text(fq)
        task_title = task_title_from_blob(blob)
        tasks.append({
            "task_id": tid,
            "conversation_id": cid,
            "ts": ts,
            "blob": blob,
            "conv_title": conv_title,
            "task_title": task_title,
        })
    return tasks, None

def _extract_query_text(raw):
    if not raw:
        return "(no queries)"
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "Query" in item:
                    text = item["Query"].get("text", "")
                    if text:
                        return text.strip().replace("\n", " ")
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    return raw.strip().replace("\n", " ") or "(no queries)"

# ── File output (watch-specific) ───────────────────────────────────────────────

def slugify(text, max_len=50):
    safe = "".join(ch if ch.isalnum() or ch in " _-" else "_" for ch in text)
    return safe.strip().replace(" ", "_")[:max_len]

def write_thinking_log(task, blocks, out_dir):
    """Write a thinking log file for a task. Returns the path written."""
    ts_raw = task["ts"] or ""
    # Normalise timestamp — WARP stores various formats
    try:
        dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        ts_file = dt.strftime("%Y%m%d_%H%M%S")
        ts_display = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        ts_file = ts_raw[:16].replace(":", "").replace("-", "").replace(" ", "_")
        ts_display = ts_raw

    slug = slugify(task["task_title"])
    filename = f"{ts_file}_{slug}.txt"
    filepath = os.path.join(out_dir, filename)

    # Avoid overwriting if a file with this name already exists
    if os.path.exists(filepath):
        base, ext = os.path.splitext(filepath)
        filepath = f"{base}_{task['task_id'][:8]}{ext}"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("=" * 72 + "\n")
        f.write("WARP AGENT THINKING LOG\n")
        f.write("=" * 72 + "\n\n")
        f.write(f"Conversation : {task['conv_title']}\n")
        f.write(f"Task         : {task['task_title']}\n")
        f.write(f"Task ID      : {task['task_id']}\n")
        f.write(f"Timestamp    : {ts_display}\n")
        f.write(f"Blocks       : {len(blocks)}\n\n")

        for i, blk in enumerate(blocks, 1):
            f.write(f"{'─' * 72}\n")
            f.write(f"Block {i}  ·  step {blk['step_id']}\n")
            f.write(f"{'─' * 72}\n\n")
            for para in blk["thinking"].split("\n"):
                if para.strip():
                    for line in textwrap.wrap(para, width=72):
                        f.write(f"  {line}\n")
                else:
                    f.write("\n")
            f.write("\n")

    return filepath

# ── Watch loop (watch-specific) ────────────────────────────────────────────────

def run_logger(db_path, out_dir, poll_interval=10, verbose=True):
    os.makedirs(out_dir, exist_ok=True)

    def log(msg):
        if verbose:
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}]  {msg}", flush=True)

    log("Warp Thinking Logger started")
    log(f"Database  : {db_path}")
    log(f"Output    : {out_dir}")
    log(f"Polling every {poll_interval}s — Ctrl+C to stop\n")

    # seen_ts:    task_id -> last_modified_at we last probed at.
    #             A task is re-probed whenever its ts changes.
    # written_ids: task_ids whose log file has been written.
    #             Once written, the task is never touched again.
    #
    # This design fixes the race condition where Warp writes a task row
    # before thinking is fully populated. A task seen mid-flight (no
    # thinking yet) is re-probed on the next poll where its ts has
    # changed, until thinking appears or the ts stabilises permanently.
    seen_ts = {}       # task_id -> last_modified_at
    written_ids = set()  # task_ids with log files already written

    existing, err = get_recent_tasks(db_path)
    if err:
        log(f"WARNING: could not read database on startup: {err}")
    else:
        for t in existing:
            seen_ts[t["task_id"]] = t["ts"]
        log(f"Found {len(seen_ts)} existing task(s) — will only log new tasks from now on")

    while True:
        try:
            time.sleep(poll_interval)
        except KeyboardInterrupt:
            log("Stopped by user.")
            break

        tasks, err = get_recent_tasks(db_path)
        if err:
            log(f"WARNING: database read error: {err}")
            continue

        for task in tasks:
            tid        = task["task_id"]
            current_ts = task["ts"]

            if tid in written_ids:
                continue  # log already written — never re-process

            if seen_ts.get(tid) == current_ts:
                continue  # task unchanged since last probe — skip

            # New task, or a task that has been updated since we last saw it.
            is_new = tid not in seen_ts
            seen_ts[tid] = current_ts

            if not blob_has_thinking(task["blob"]):
                # No thinking found yet. If brand-new, note it; otherwise
                # stay silent and re-probe next time the ts changes.
                if is_new:
                    log(f"  wait   {task['task_title'][:55]}  (appeared, no thinking yet)")
                continue

            blocks = extract_thinking(task["blob"])
            if not blocks:
                if is_new:
                    log(f"  wait   {task['task_title'][:55]}  (appeared, extraction empty)")
                continue

            try:
                path = write_thinking_log(task, blocks, out_dir)
                written_ids.add(tid)
                log(f"  wrote  {len(blocks)} block(s)  →  {os.path.basename(path)}")
            except Exception as e:
                log(f"  ERROR writing log for task {tid}: {e}")

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="warp_thinking_watch.py",
        description="Auto-export Warp agent thinking blocks to log files as sessions complete.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help="Path to warp.sqlite (auto-detected if omitted)"
    )
    parser.add_argument(
        "--out",
        metavar="DIR",
        default=os.path.join(os.getcwd(), "warp_thinking_logs"),
        help="Output directory for log files (default: ./warp_thinking_logs/)"
    )
    parser.add_argument(
        "--interval",
        metavar="SECONDS",
        type=int,
        default=10,
        help="Polling interval in seconds (default: 10)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output"
    )
    args = parser.parse_args()

    db_path = os.path.expanduser(args.db) if args.db else default_db_path()

    if not db_path or not os.path.exists(db_path):
        detected = db_path or "(could not detect for this OS)"
        print(f"\n  Warp database not found at: {detected}")
        print( "  Use --db /path/to/warp.sqlite to specify it manually.\n")
        sys.exit(1)

    out_dir = os.path.expanduser(args.out)

    run_logger(
        db_path=db_path,
        out_dir=out_dir,
        poll_interval=args.interval,
        verbose=not args.quiet,
    )

if __name__ == "__main__":
    main()
