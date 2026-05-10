#!/usr/bin/env python3
"""
warp_thinking_browse.py
───────────────────────
Browse Warp agent conversations and extract the model's internal reasoning
("thinking") text — the first-person chain-of-thought the AI produces during
a task, normally shown as a collapsed block in the Warp UI.

Requirements: Python 3.7+, no third-party packages.

Sections:
    Config              — ANSI colour support and terminal helpers
    Protobuf (shared)   — wire-format parser, keep in sync across scripts
    DB shared           — default_db_path, _extract_query_text
    DB browse-specific  — conversation and task loading
    Screens             — interactive TUI
    Entry point         — main()

Usage:
    python3 warp_thinking_browse.py           # auto-detect DB location
    python3 warp_thinking_browse.py --db /path/to/warp.sqlite
    python3 warp_thinking_browse.py --help

Default database locations:
    macOS:   ~/Library/Group Containers/2BBY89MBSN.dev.warp/Library/
             Application Support/dev.warp.Warp-Stable/warp.sqlite
    Linux:   ~/.local/state/warp-terminal/warp.sqlite
    Windows: %LOCALAPPDATA%\\warp\\Warp\\data\\warp.sqlite
"""

import argparse
import json
import os
import platform
import sqlite3
import sys
import textwrap

# ── Config ────────────────────────────────────────────────────────────────────

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
    else:
        return None


def _supports_colour():
    if platform.system() == "Windows":
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.SetConsoleMode(kernel.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

_COLOUR = _supports_colour()
RESET  = "\033[0m"  if _COLOUR else ""
BOLD   = "\033[1m"  if _COLOUR else ""
DIM    = "\033[2m"  if _COLOUR else ""
CYAN   = "\033[36m" if _COLOUR else ""
GREEN  = "\033[32m" if _COLOUR else ""
YELLOW = "\033[33m" if _COLOUR else ""
RED    = "\033[31m" if _COLOUR else ""

def c(text, *codes):
    return "".join(codes) + str(text) + RESET

def clear():
    os.system("cls" if platform.system() == "Windows" else "clear")

def hr(char="─", width=72, colour=DIM):
    print(c(char * width, colour))

def header(title):
    clear()
    hr("═")
    print(c(f"  WARP THINKING BROWSER  ·  {title}", BOLD, CYAN))
    hr("═")
    print()

def prompt(msg, options=""):
    if options:
        msg = f"{msg}  {c(options, DIM)}"
    try:
        return input(f"\n{c('›', BOLD, CYAN)} {msg}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return "q"

# ── Protobuf parser (shared — keep in sync across all three scripts) ──────────
#
# Warp stores agent task data as Protocol Buffers binary blobs.
# We parse without a schema using wire-format rules:
#   wire type 0 = varint, 1 = 64-bit, 2 = length-delimited, 5 = 32-bit
#
# Observed field layout:
#   Task message  — field 1: task_id  field 2: title  field 5 (rep): steps
#   Step message  — field 1: step_id  field 15: thinking block (nested msg)
#   Thinking msg  — field 1 (or 2): thinking text string

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
    Definitive check: returns True if the blob contains at least one
    thinking block (field 15 in a step message with extractable text).

    This replaces the size heuristic. It stops at the first confirmed
    thinking field found, so it is fast enough to run on every blob
    at list time.
    """
    for fn, wt, val in parse_fields(bytes(blob)):
        if fn != 5 or wt != 2:          # must be a step (field 5)
            continue
        for sfn, swt, sval in parse_fields(val):
            if sfn != 15 or swt != 2:   # must be a thinking block (field 15)
                continue
            for _, twt, tval in parse_fields(sval):
                if twt == 2 and len(tval) > 10 and decode_string(tval) is not None:
                    return True         # confirmed: readable thinking text exists
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

# (default_db_path is in Config section above — shared across all scripts)

# ── DB helpers (browse-specific) ─────────────────────────────────────────────

_DB_PATH = None

def get_db():
    return sqlite3.connect(_DB_PATH)

def load_conversations(limit=500):
    con = get_db()
    rows = con.execute("""
        SELECT
            ac.conversation_id,
            ac.last_modified_at,
            (
                SELECT aq.input
                FROM ai_queries aq
                WHERE aq.conversation_id = ac.conversation_id
                ORDER BY aq.start_ts ASC
                LIMIT 1
            ) AS first_query
        FROM agent_conversations ac
        ORDER BY ac.last_modified_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    con.close()
    result = []
    for cid, ts, fq in rows:
        title = _extract_query_text(fq)
        result.append({"id": cid, "ts": ts, "title": title})
    return result

def search_thinking_in_conversation(conversation_id, term):
    """Return True if any task in this conversation contains term in its thinking."""
    con = get_db()
    rows = con.execute(
        "SELECT task FROM agent_tasks WHERE conversation_id = ?",
        (conversation_id,)
    ).fetchall()
    con.close()
    term_lower = term.lower()
    for (blob,) in rows:
        for block in extract_thinking(blob):
            if term_lower in block["thinking"].lower():
                return True
    return False

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

def load_tasks(conversation_id):
    con = get_db()
    rows = con.execute("""
        SELECT task_id, last_modified_at, length(task), task
        FROM agent_tasks
        WHERE conversation_id = ?
        ORDER BY last_modified_at ASC
    """, (conversation_id,)).fetchall()
    con.close()
    result = []
    for tid, ts, size, blob in rows:
        result.append({
            "id": tid, "ts": ts, "size": size,
            "title": task_title_from_blob(blob), "blob": blob
        })
    return result

# ── Screens (browse-specific) ────────────────────────────────────────────────

def _term_width():
    try:
        return os.get_terminal_size().columns
    except Exception:
        return 120

def screen_conversations():
    title_filter   = ""
    thinking_filter = ""

    while True:
        header("Conversations")

        print(c("  FILTERS", BOLD))
        tf_display = c(f'"{title_filter}"', CYAN) if title_filter else c("none", DIM)
        sk_display = c(f'"{thinking_filter}"', CYAN) if thinking_filter else c("none", DIM)
        print(f"  [F] Title filter    : {tf_display}")
        print(f"  [T] Thinking search : {sk_display}")
        if title_filter or thinking_filter:
            print(f"  [C] Clear all filters")
        print()
        hr()
        print()

        all_convos = load_conversations()

        if title_filter:
            term = title_filter.lower()
            all_convos = [cv for cv in all_convos if term in cv["title"].lower()]

        if thinking_filter:
            print(c("  Searching thinking text…", DIM), end="\r", flush=True)
            matched = []
            for cv in all_convos:
                if search_thinking_in_conversation(cv["id"], thinking_filter):
                    matched.append(cv)
            all_convos = matched
            print(" " * 40, end="\r")

        convos = all_convos

        if not convos:
            print(c("  No conversations matched your filters.", YELLOW))
        else:
            prefix_width = 26
            title_width  = max(40, _term_width() - prefix_width)
            indent       = " " * prefix_width

            for i, cv in enumerate(convos):
                ts_short    = (cv["ts"] or "")[:16]
                idx_str     = c(f"[{i:>2}]", BOLD, CYAN)
                ts_str      = c(ts_short, DIM)
                title_lines = textwrap.wrap(cv["title"], width=title_width) or ["(no queries)"]
                print(f"  {idx_str}  {ts_str}  {title_lines[0]}")
                for line in title_lines[1:]:
                    print(f"{indent}{line}")

        total = len(convos)
        print()
        hr()
        if title_filter or thinking_filter:
            print(c(f"  {total} conversation(s) matched", DIM))

        choice = prompt(
            "Number to open,  F = title filter,  T = thinking search,"
            + ("  C = clear," if title_filter or thinking_filter else "")
            + "  Q = quit",
            "[0-N / F / T / C / Q]"
        )
        cl = choice.lower()

        if cl == "q":
            return
        elif cl == "f":
            val = prompt("Title filter (Enter to clear)").strip()
            title_filter = val
        elif cl == "t":
            val = prompt("Search thinking text (Enter to clear)").strip()
            thinking_filter = val
        elif cl == "c":
            title_filter = ""
            thinking_filter = ""
        else:
            try:
                idx = int(choice)
                if 0 <= idx < len(convos):
                    screen_tasks(convos[idx])
            except ValueError:
                pass

def screen_tasks(convo):
    while True:
        header(f"Tasks  ·  {convo['title'][:55]}")
        tasks = load_tasks(convo["id"])

        if not tasks:
            print(c("  No tasks found for this conversation.", YELLOW))
            prompt("Press Enter to go back")
            return

        for i, t in enumerate(tasks):
            ts_short = (t["ts"] or "")[:16]
            size_kb  = t["size"] / 1024

            # ── Definitive thinking check — no heuristics ──────────────────
            has_think = blob_has_thinking(t["blob"])
            if has_think:
                flag = c("  ✦ thinking confirmed", GREEN, BOLD)
            else:
                flag = c("  · no thinking", DIM)

            print(
                f"  {c(f'[{i:>2}]', BOLD, CYAN)}"
                f"  {c(ts_short, DIM)}"
                f"  {c(f'{size_kb:>7.1f} KB', DIM)}"
                f"  {t['title'][:40]}"
                f"{flag}"
            )

        print()
        hr()
        choice = prompt("Select task number,  B to go back", "[0-N / B]")
        if choice.lower() == "b":
            return
        try:
            idx = int(choice)
            if 0 <= idx < len(tasks):
                screen_thinking(tasks[idx])
        except ValueError:
            pass

def screen_thinking(task):
    header(f"Thinking  ·  {task['title'][:55]}")
    print(c("  Extracting…", DIM), end="\r")
    blocks = extract_thinking(task["blob"])
    clear()
    header(f"Thinking  ·  {task['title'][:55]}")

    if not blocks:
        print(c("  No thinking blocks found in this task.", YELLOW))
        print(c("  The model did not use extended reasoning here.", DIM))
        prompt("Press Enter to go back")
        return

    print(c(f"  {len(blocks)} thinking block(s) found\n", GREEN))

    for i, blk in enumerate(blocks, 1):
        hr("─")
        print(c(f"  Block {i}  ·  step {blk['step_id']}", BOLD))
        hr("─")
        for para in blk["thinking"].split("\n"):
            if para.strip():
                for line in textwrap.wrap(para, width=72):
                    print(f"  {line}")
            else:
                print()
        print()

    hr("═")
    choice = prompt("S = save to file,  B = back,  Q = quit", "[S / B / Q]")
    if choice.lower() == "s":
        save_thinking(task, blocks)
        prompt("Press Enter to continue")
    elif choice.lower() == "q":
        sys.exit(0)

def save_thinking(task, blocks):
    safe = "".join(ch if ch.isalnum() or ch in " _-" else "_" for ch in task["title"])
    safe = safe.strip().replace(" ", "_")[:50]
    ts   = (task["ts"] or "")[:10].replace("-", "")
    default_name = f"thinking_{ts}_{safe}.txt"
    default_path = os.path.join(os.getcwd(), default_name)

    print(f"\n  Default save path: {c(default_path, CYAN)}")
    dest = prompt("Press Enter to accept, or type a different path").strip()
    if not dest:
        dest = default_path
    dest = os.path.expanduser(dest)
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)

    with open(dest, "w", encoding="utf-8") as f:
        f.write(f"Task:   {task['title']}\n")
        f.write(f"TaskID: {task['id']}\n")
        f.write(f"Date:   {task['ts']}\n")
        f.write(f"Blocks: {len(blocks)}\n")
        f.write("=" * 72 + "\n\n")
        for i, blk in enumerate(blocks, 1):
            f.write(f"--- Block {i}  (step {blk['step_id']}) ---\n\n")
            f.write(blk["thinking"])
            f.write("\n\n")

    print(c(f"\n  Saved → {dest}", GREEN))

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global _DB_PATH

    parser = argparse.ArgumentParser(
        prog="warp_thinking_browse.py",
        description="Browse Warp agent conversations and extract thinking text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help="Path to warp.sqlite (auto-detected if omitted)"
    )
    args = parser.parse_args()

    if args.db:
        _DB_PATH = os.path.expanduser(args.db)
    else:
        _DB_PATH = default_db_path()

    if not _DB_PATH or not os.path.exists(_DB_PATH):
        detected = _DB_PATH or "(could not detect for this OS)"
        print(c(f"\n  Warp database not found at: {detected}", RED))
        print(c( "  Use --db /path/to/warp.sqlite to specify it manually.", YELLOW))
        print(c( "\n  Common locations:", DIM))
        print("    macOS:   ~/Library/Group Containers/2BBY89MBSN.dev.warp/"
              "Library/Application Support/dev.warp.Warp-Stable/warp.sqlite")
        print("    Linux:   ~/.local/state/warp-terminal/warp.sqlite")
        print("    Windows: %LOCALAPPDATA%\\warp\\Warp\\data\\warp.sqlite\n")
        sys.exit(1)

    screen_conversations()
    clear()
    print(c("  Bye.\n", DIM))

if __name__ == "__main__":
    main()
