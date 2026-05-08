# warp-thinking-browser

Extract and browse Warp agent thinking/reasoning text from the local SQLite
database.

Workaround for [warpdotdev/warp#9702](https://github.com/warpdotdev/warp/issues/9702)
— *Feature request: Persist agent thinking/reasoning output for review after
response completes.*

---

## Why this exists

When a Warp agent processes a request using an extended thinking model, the
model produces two distinct outputs: the visible response, and a reasoning
trace — a first-person chain-of-thought showing how it arrived at that
response.

Warp displays this reasoning trace as a streaming preview while the model
thinks. Once the response completes, the trace collapses into a small,
fixed-height viewport. For any non-trivial reasoning chain the only way to
read the full output is to scroll through a tiny window or take screenshots.

This is a significant friction point for anyone who relies on the thinking
output to understand agent decision-making, debug unexpected behaviour, refine
prompts, or study how the model interpreted a request. The thinking output is
paid-for content — in many cases the most valuable part of a session — but
its transient presentation makes it nearly impossible to work with.

**Warp already stores the complete thinking text in its local SQLite
database.** The display problem is a UI constraint, not a data constraint.
These tools bypass the UI entirely, read the database directly, parse the
binary task blobs, and surface the full thinking output as readable, searchable,
saveable plain text.

---

## The two tools

### `warp_thinking_browser.py`

An interactive terminal browser for your Warp conversation history. Navigate
conversations, select tasks, and read or save the full thinking text for any
session. Use it when you want to go back and examine the reasoning from a
specific past session.

### `warp_thinking_logger.py`

A background daemon that watches the Warp database and automatically exports
thinking blocks to timestamped log files as sessions complete. Run it once and
leave it — every session that produces thinking output gets a log file without
any manual intervention. Use it when you want a persistent, searchable archive
of all thinking output across all sessions going forward.

---

## How thinking detection works

Both tools use a **definitive protobuf field probe** rather than a size
heuristic. The Warp database stores task data as Protocol Buffers binary blobs.
Within each blob, thinking text lives at field 15 of each step message. The
tools walk the protobuf structure and confirm that field 15 content with
readable UTF-8 text actually exists before reporting a task as containing
thinking. A task either has thinking or it does not — there is no "thinking
likely" guess.

The browser displays `✦ thinking confirmed` or `· no thinking` next to each
task. The logger silently skips tasks with no thinking and writes a log file
for tasks that do.

---

## Requirements

- Python 3.7 or later
- No third-party packages — standard library only
- Warp terminal installed (the database is created automatically by Warp)

---

## Installation

No installation required. Download both script files and place them anywhere:

```bash
git clone https://github.com/DocterJac/warp-thinking-browser.git
cd warp-thinking-browser
```

Or download the scripts individually.

---

## Database location

The tools auto-detect the Warp database. If auto-detection fails, use `--db`
to specify the path manually.

| Platform | Default path |
|----------|-------------|
| macOS    | `~/Library/Group Containers/2BBY89MBSN.dev.warp/Library/Application Support/dev.warp.Warp-Stable/warp.sqlite` |
| Linux    | `~/.local/state/warp-terminal/warp.sqlite` |
| Windows  | `%LOCALAPPDATA%\warp\Warp\data\warp.sqlite` |

---

## warp_thinking_browser.py — Usage

```bash
python3 warp_thinking_browser.py                       # auto-detect database
python3 warp_thinking_browser.py --db /path/to/warp.sqlite
```

### Conversations screen

Lists your 500 most recent conversations by timestamp and opening question.

```
════════════════════════════════════════════════════════════════════════
  WARP THINKING BROWSER  ·  Conversations
════════════════════════════════════════════════════════════════════════

  FILTERS
  [F] Title filter    : none
  [T] Thinking search : none

────────────────────────────────────────────────────────────────────────

  [ 0]  2026-05-08 09:41  refactor the authentication middleware to use JWT
  [ 1]  2026-05-08 08:17  why are my Jest tests failing after the webpack config change?
  [ 2]  2026-05-07 22:53  write a migration script to backfill the users table
  [ 3]  2026-05-07 19:30  help me debug the memory leak in the worker pool

› Number to open,  F = title filter,  T = thinking search,  Q = quit
```

Type the number of the conversation you want and press Enter.

### Filters

**F — Title filter** narrows the list by any word or phrase from the opening
question. Runs instantly against stored text — no blob parsing.

**T — Thinking search** scans the full thinking text inside every task blob
across the (filtered) conversation list. Use this when you remember something
the model reasoned about but not necessarily what you asked it. Shows a
progress indicator while scanning.

The filters stack: title filter runs first (fast), then thinking search
operates only on the results. **C** clears both filters.

### Tasks screen

Each conversation can contain multiple tasks — one per agent run. Each task
shows a definitive `✦ thinking confirmed` or `· no thinking` flag.

```
  [ 0]  2026-05-08 09:41    287.4 KB  Refactor Auth Middleware     ✦ thinking confirmed
  [ 1]  2026-05-08 09:53     61.2 KB  Add Unit Tests               ✦ thinking confirmed
  [ 2]  2026-05-08 10:04      1.8 KB  (untitled)                   · no thinking
```

### Thinking view

Displays the full thinking output split into numbered blocks — one per
reasoning step — word-wrapped to 72 characters. Press **S** to save the full
output to a `.txt` file.

---

## warp_thinking_logger.py — Usage

```bash
python3 warp_thinking_logger.py                         # log to ./warp_thinking_logs/
python3 warp_thinking_logger.py --out ~/research/logs   # custom output directory
python3 warp_thinking_logger.py --db /path/to/warp.sqlite --out ~/logs
python3 warp_thinking_logger.py --interval 30           # poll every 30 seconds (default: 10)
python3 warp_thinking_logger.py --quiet                 # suppress console output
```

Run in the background:

```bash
nohup python3 warp_thinking_logger.py --out ~/warp_thinking_logs &
```

### What it does

On startup, the logger records all existing task IDs so it only captures new
sessions going forward — it does not retroactively process your entire history.

Every `--interval` seconds it checks for new task rows in the database. For
each new task it runs the definitive field-15 probe. Tasks with no thinking
are silently skipped. Tasks with thinking get a log file written immediately.

Console output (unless `--quiet`):

```
[09:41:03]  Warp Thinking Logger started
[09:41:03]  Database  : ~/Library/.../warp.sqlite
[09:41:03]  Output    : ~/warp_thinking_logs
[09:41:03]  Polling every 10s — Ctrl+C to stop

[09:43:17]  wait   Add Unit Tests  (appeared, no thinking yet)
[09:47:52]  wrote  3 block(s)  →  20260508_094752_Refactor_Auth_Middleware.txt
[09:51:04]  wait   quick fix for typo  (appeared, no thinking yet)
[09:52:18]  wrote  1 block(s)  →  20260508_095218_quick_fix_for_typo.txt
```

### Output files

One `.txt` file per task that contains thinking, named:

```
YYYYMMDD_HHMMSS_<task_title_slug>.txt
```

Each file contains the conversation title, task title, task ID, timestamp,
and all thinking blocks numbered and separated.

### Running as a launchd service (macOS)

To have the logger start automatically at login, create
`~/Library/LaunchAgents/com.github.warp-thinking-logger.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.github.warp-thinking-logger</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/path/to/warp_thinking_logger.py</string>
    <string>--out</string>
    <string>/Users/YOUR_USERNAME/warp_thinking_logs</string>
    <string>--quiet</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardErrorPath</key>
  <string>/tmp/warp-thinking-logger.err</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.github.warp-thinking-logger.plist
```

Stop it:

```bash
launchctl unload ~/Library/LaunchAgents/com.github.warp-thinking-logger.plist
```

### Running as a systemd service (Linux)

Create `~/.config/systemd/user/warp-thinking-logger.service`:

```ini
[Unit]
Description=Warp Thinking Logger
After=default.target

[Service]
ExecStart=/usr/bin/python3 /path/to/warp_thinking_logger.py \
  --out /home/YOUR_USERNAME/warp_thinking_logs \
  --quiet
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

Enable and start:

```bash
systemctl --user enable warp-thinking-logger
systemctl --user start warp-thinking-logger
```

---

## Technical notes

### How the protobuf parser works

Warp stores agent task data as Protocol Buffers binary blobs in the
`agent_tasks.task` column. The tools parse these without a schema using the
protobuf wire-format rules directly.

Observed field layout:

```
Task message
  Field 1   →  task_id (string)
  Field 2   →  task title (string)
  Field 5   →  repeated step messages
    Step message
      Field 1   →  step_id (string)
      Field 15  →  thinking block (nested message)
                     contains the thinking text as a string field
      Field 3   →  text response block
      Field 4   →  tool use block
      Field 5   →  tool result block
```

Field 15 of each step message is where the thinking text lives. The parser
walks every step, extracts any field-15 content, and returns it as a list
of thinking blocks — one per reasoning step. The parser is approximately
50 lines of Python with no external dependencies.

### Why not network interception?

Warp's AI endpoints use Protocol Buffers binary encoding
(`application/x-protobuf`) rather than JSON for requests. Intercepting the
response layer via a proxy would require maintaining SSL certificates and
keeping a proxy process running permanently — significant ongoing friction.

The Warp database approach is simpler and more reliable: Warp writes the
complete thinking text to `warp.sqlite` automatically. The tools read from
the same data Warp already stores, with no impact on the running application.
The logger opens the database read-only (`file:...?mode=ro`) and cannot
corrupt Warp's data.

### Schema dependency

The protobuf field numbers used by these tools were determined by inspection
of the binary blobs. They are not documented by Warp. A future Warp update
could change the binary layout, which would require updating the field numbers
in `parse_fields()`. Both tools will report `· no thinking` / silently skip
rather than crash if the schema changes, but results would be empty. Check
after any significant Warp version update if output stops appearing.

---

## Limitations

- **Retroactive coverage.** The logger only captures sessions going forward
  from when it was started. For sessions before that, use the browser tool.
  The browser tool can search all stored history.

- **Local database only.** Tasks that ran on a different machine are not in
  your local database unless you have accessed those conversations in Warp
  (which triggers a sync).

- **No thinking = no output.** Simple or short agent responses may not trigger
  extended reasoning. Both tools report this clearly rather than silently
  returning nothing.

- **Undocumented schema.** See Technical notes above.

---

## Author

**Lester Wilson**

Built as a workaround for
[warpdotdev/warp#9702](https://github.com/warpdotdev/warp/issues/9702).

---

## Licence

MIT — do whatever you like with it.
