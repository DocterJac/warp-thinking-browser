#!/usr/bin/env python3
"""
warp_thinking_read.py
──────────────────────
Extract and display the full thinking chain and AI response text for a
specific Warp agent task, identified by task_id.

For each step in the task, prints the thinking block first (if present)
followed by the response text (if present), so you can read the full
reasoning → response flow in sequence.

Sections:
    Protobuf (shared)   — wire-format parser, keep in sync across scripts
    DB shared           — default_db_path, _extract_query_text
    DB read-specific    — fetch_task, list_recent_tasks
    Extraction          — extract_steps (thinking + response)
    Formatting          — output rendering
    Entry point         — main()

Usage:
    python3 warp_thinking_read.py <task_id>
    python3 warp_thinking_read.py <task_id> --db /path/to/warp.sqlite
    python3 warp_thinking_read.py --list              # show 20 most recent tasks
    python3 warp_thinking_read.py <task_id> --save    # save output to a .txt file

Requirements: Python 3.7+, no third-party packages.
"""

import argparse
import json
import os
import platform
import sqlite3
import sys
import textwrap


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

# ── Extraction (read-specific) ───────────────────────────────────────────────

def extract_steps(blob):
    """
    Parse the task blob and return a list of step dicts:
        {
            step_id:   str | None,
            thinking:  str | None,   # field 15 → field 1
            response:  str | None,   # field 3  → field 1
        }
    Steps are returned in blob order (which matches execution order).
    """
    steps = []

    for fn, wt, val in parse_fields(bytes(blob)):
        if fn != 5 or wt != 2:
            continue  # only step messages (field 5)

        step = {"step_id": None, "thinking": None, "response": None}
        thinking_chunks = []
        response_chunks = []

        for sfn, swt, sval in parse_fields(val):

            # Field 1 — step UUID
            if sfn == 1 and swt == 2:
                step["step_id"] = decode_string(sval)

            # Field 3 — AI response block (nested message → field 1 = text)
            elif sfn == 3 and swt == 2:
                for ifn, iwt, ival in parse_fields(sval):
                    if ifn == 1 and iwt == 2:
                        text = decode_string(ival)
                        if text and len(text.strip()) > 0:
                            response_chunks.append(text)

            # Field 15 — thinking block (nested message → field 1 = text)
            elif sfn == 15 and swt == 2:
                for ifn, iwt, ival in parse_fields(sval):
                    if iwt == 2:
                        text = decode_string(ival)
                        if text and len(text) > 10:
                            thinking_chunks.append(text)

        if thinking_chunks:
            step["thinking"] = "\n".join(thinking_chunks)
        if response_chunks:
            step["response"] = "\n".join(response_chunks)

        # Only keep steps that have at least one of thinking or response
        if step["thinking"] or step["response"]:
            steps.append(step)

    return steps


# ── DB helpers (read-specific) ───────────────────────────────────────────────

def fetch_task(db_path, task_id):
    """Return (task_row_dict, conv_title) or raise if not found."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    row = con.execute(
        "SELECT task_id, conversation_id, last_modified_at, length(task), task "
        "FROM agent_tasks WHERE task_id = ?",
        (task_id,)
    ).fetchone()

    if not row:
        con.close()
        return None, None

    tid, cid, ts, size, blob = row

    # Get conversation title from ai_queries
    fq_row = con.execute(
        "SELECT input FROM ai_queries WHERE conversation_id = ? "
        "ORDER BY start_ts ASC LIMIT 1",
        (cid,)
    ).fetchone()
    con.close()

    conv_title = _extract_query_text(fq_row[0] if fq_row else None)

    return {
        "task_id":   tid,
        "task_title": task_title_from_blob(blob),
        "conv_title": conv_title,
        "ts":        ts,
        "size_kb":   size / 1024,
        "blob":      blob,
    }, conv_title


def list_recent_tasks(db_path, n=20):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT at.task_id, at.conversation_id, at.last_modified_at, length(at.task), at.task, "
        "(SELECT aq.input FROM ai_queries aq WHERE aq.conversation_id = at.conversation_id "
        " ORDER BY aq.start_ts ASC LIMIT 1) "
        "FROM agent_tasks at ORDER BY at.last_modified_at DESC LIMIT ?",
        (n,)
    ).fetchall()
    con.close()

    result = []
    for tid, cid, ts, size, blob, fq in rows:
        result.append({
            "task_id":    tid,
            "task_title": task_title_from_blob(blob),
            "conv_title": _extract_query_text(fq),
            "ts":         ts,
            "size_kb":    size / 1024,
        })
    return result


# ── Formatting (read-specific) ────────────────────────────────────────────────

WRAP_WIDTH = 80

def wrap_text(text):
    lines = []
    for para in text.split("\n"):
        if para.strip():
            lines.extend(textwrap.wrap(para, width=WRAP_WIDTH))
            lines.append("")
        else:
            lines.append("")
    # Remove trailing blank lines
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def format_output(task, steps):
    """Return the full formatted output as a string."""
    out = []

    divider     = "═" * WRAP_WIDTH
    thin_div    = "─" * WRAP_WIDTH

    out.append(divider)
    out.append(f"TASK:         {task['task_title']}")
    out.append(f"CONVERSATION: {task['conv_title'][:WRAP_WIDTH - 14]}")
    out.append(f"TASK ID:      {task['task_id']}")
    out.append(f"DATE:         {task['ts']}")
    out.append(f"SIZE:         {task['size_kb']:.1f} KB")
    out.append(divider)

    thinking_count = sum(1 for s in steps if s["thinking"])
    response_count = sum(1 for s in steps if s["response"])
    out.append(
        f"\n{len(steps)} step(s) with content  "
        f"·  {thinking_count} thinking block(s)  "
        f"·  {response_count} response block(s)\n"
    )

    for i, step in enumerate(steps, 1):
        out.append(f"{'━' * WRAP_WIDTH}")
        out.append(f"STEP {i}  ·  {step['step_id']}")
        out.append(f"{'━' * WRAP_WIDTH}")

        if step["thinking"]:
            out.append(f"\n  ▸ THINKING\n{thin_div}")
            out.append(wrap_text(step["thinking"]))

        if step["response"]:
            out.append(f"\n  ▸ RESPONSE\n{thin_div}")
            out.append(wrap_text(step["response"]))

        out.append("")

    out.append(divider)
    return "\n".join(out)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="warp_thinking_read.py",
        description="Print thinking chain and response text for a Warp agent task.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("task_id", nargs="?", help="Task UUID to read")
    parser.add_argument("--db", metavar="PATH",
                        help="Path to warp.sqlite (auto-detected if omitted)")
    parser.add_argument("--list", action="store_true",
                        help="List 20 most recent tasks and exit")
    parser.add_argument("--save", action="store_true",
                        help="Save output to a .txt file in the current directory")
    args = parser.parse_args()

    db_path = os.path.expanduser(args.db) if args.db else default_db_path()

    if not db_path or not os.path.exists(db_path):
        print(f"\n  Database not found: {db_path or '(could not detect)'}")
        print("  Use --db /path/to/warp.sqlite\n")
        sys.exit(1)

    # ── --list mode ───────────────────────────────────────────────────────────
    if args.list:
        tasks = list_recent_tasks(db_path)
        print(f"\n{'─' * 100}")
        print(f"{'TIMESTAMP':<18}  {'SIZE':>8}  {'TASK TITLE':<35}  CONVERSATION")
        print(f"{'─' * 100}")
        for t in tasks:
            print(
                f"{(t['ts'] or '')[:16]:<18}  "
                f"{t['size_kb']:>7.1f}K  "
                f"{t['task_title'][:35]:<35}  "
                f"{t['conv_title'][:50]}"
            )
            print(f"  task_id: {t['task_id']}")
            print()
        print(f"{'─' * 100}\n")
        return

    # ── Read task ─────────────────────────────────────────────────────────────
    if not args.task_id:
        parser.print_help()
        sys.exit(1)

    task, _ = fetch_task(db_path, args.task_id)
    if not task:
        print(f"\n  Task not found: {args.task_id}\n")
        print("  Use --list to see recent task IDs.\n")
        sys.exit(1)

    steps = extract_steps(task["blob"])

    if not steps:
        print(f"\n  No thinking or response content found in task {args.task_id}.\n")
        sys.exit(0)

    output = format_output(task, steps)
    print(output)

    # ── --save ────────────────────────────────────────────────────────────────
    if args.save:
        safe = "".join(
            ch if ch.isalnum() or ch in " _-" else "_"
            for ch in task["task_title"]
        ).strip().replace(" ", "_")[:50]
        ts = (task["ts"] or "")[:10].replace("-", "")
        filename = f"task_{ts}_{safe}.txt"
        filepath = os.path.join(os.getcwd(), filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n  Saved → {filepath}\n")


if __name__ == "__main__":
    main()
