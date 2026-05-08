# Warp Thinking Browser

A lightweight, zero-dependency terminal tool that lets you browse your Warp agent
conversations and extract the full reasoning ("thinking") text the AI produced
during each task — the complete, untruncated chain-of-thought that is otherwise
trapped in a tiny, non-scrollable viewport in the Warp UI.

---

## Background — the problem this solves

Warp issue [#9702](https://github.com/warpdotdev/warp/issues/9702) describes the
core problem:

> *"The thinking output is paid-for content that provides genuine value, but its
> transient nature makes it nearly impossible to digest in real time, especially
> for longer reasoning chains."*

With **Always show** enabled in Settings › AI › Other, Warp does preserve the
thinking text after a response completes — but the preserved section is a small,
fixed-height, non-resizable viewport. For any non-trivial reasoning chain the only
way to read the full output is to scroll through a tiny window, take dozens of
screenshots, or try to OCR your way through it.

This tool bypasses the UI entirely. Warp already stores the complete thinking text
in its local SQLite database. This script reads that database directly, parses the
binary task blobs, and presents the full thinking output as readable, scrollable,
copyable, saveable plain text.

---

## What it does

- Lists up to 500 recent Warp agent **conversations** by timestamp and first message
- **Filter by title** — instantly narrow the list by any word or phrase from your question
- **Search inside thinking** — scan the full reasoning text across all conversations
  to find one where the AI discussed a specific topic
- Drills into a conversation to show the individual **tasks** (each agent run)
  with a size indicator flagging which ones are likely to contain thinking
- Extracts and displays the full **thinking blocks** for any selected task,
  word-wrapped for comfortable reading in the terminal
- Optionally **saves** the thinking text to a plain `.txt` file you can open,
  search, share, or archive

---

## Requirements

- Python 3.7 or later
- No third-party packages — uses only the Python standard library
- Warp terminal app installed (the database is created by Warp automatically)

---

## Installation

No installation required. Just download the single script file:

```
warp_thinking_browser.py
```

Place it anywhere you like — your home directory, a scripts folder, wherever.

---

## Usage

### Run it

```bash
python3 warp_thinking_browser.py
```

The database is detected automatically. On first launch you will see a list of
your 500 most recent conversations.

### Override the database path

If Warp is installed in a non-standard location, or you want to point at a
different database:

```bash
python3 warp_thinking_browser.py --db /path/to/warp.sqlite
```

### Get help

```bash
python3 warp_thinking_browser.py --help
```

---

## Walkthrough

### Step 1 — Conversations screen

The conversations screen shows your history with a filter panel at the top.

```
════════════════════════════════════════════════════════════════════════
  WARP THINKING BROWSER  ·  Conversations
════════════════════════════════════════════════════════════════════════

  FILTERS
  [F] Title filter    : none
  [T] Thinking search : none

────────────────────────────────────────────────────────────────────────

  [ 0]  2026-05-08 09:41  refactor the authentication middleware to use JWT
                          bearer tokens and move validation into a dedicated
                          service class
  [ 1]  2026-05-08 08:17  why are my Jest tests failing after the webpack
                          config change?
  [ 2]  2026-05-07 22:53  write a migration script to backfill the users
                          table with default preferences
  [ 3]  2026-05-07 19:30  help me debug the memory leak in the worker pool
  ...

› Number to open,  F = title filter,  T = thinking search,  Q = quit
  [0-N / F / T / C / Q]:
```

Type the number next to the conversation you want and press Enter.

### Filtering conversations

With hundreds of conversations in history, the two filters help you zero in
on the right one quickly.

#### F — Title filter (fast)

Filters the conversation list by any word or phrase from your original
question. Runs instantly — no blob parsing.

```
› Title filter (Enter to clear): JWT middleware
```

The list immediately narrows to only conversations whose opening question
contains that text.

#### T — Thinking search (slower)

Searches the full thinking text inside every task blob across the filtered
conversations. Use this when you remember something the AI *reasoned about*
but not necessarily what you asked.

```
› Search thinking text (Enter to clear): TokenService
```

A progress message shows while blobs are being scanned. Only conversations
where at least one task contains that term in its thinking text are returned.

#### Using both together

The filters stack — title filter runs first (cheap), then thinking search
operates only on those results. This keeps the thinking search fast even
against a large history.

#### C — Clear all filters

`C` appears in the prompt once any filter is active. Press it to reset both
filters and return to the full list.

```
  FILTERS
  [F] Title filter    : "JWT middleware"
  [T] Thinking search : "TokenService"
  [C] Clear all filters

  [ 0]  2026-05-08 09:41  refactor the authentication middleware...

  1 conversation(s) matched
```

### Step 2 — Tasks screen

Each conversation can contain multiple tasks (one per agent run). The `✦ thinking
likely` flag is shown for tasks over 5 KB — a reliable heuristic for tasks that
contain substantive reasoning.

```
════════════════════════════════════════════════════════════════════════
  WARP THINKING BROWSER  ·  Tasks  ·  refactor the authentication midd…
════════════════════════════════════════════════════════════════════════

  [ 0]  2026-05-08 09:41    287.4 KB  Refactor Auth Middleware           ✦ thinking likely
  [ 1]  2026-05-08 09:53     61.2 KB  Add Unit Tests for Auth Module     ✦ thinking likely
  [ 2]  2026-05-08 10:04      1.8 KB  (untitled)                         · small

› Select task number, B to go back  [0-N / B]:
```

### Step 3 — Thinking text

The full thinking output is displayed, split into numbered blocks (one per
reasoning step). Each block shows the step ID and the complete text, word-wrapped
to 72 characters for readability.

```
════════════════════════════════════════════════════════════════════════
  WARP THINKING BROWSER  ·  Thinking  ·  Refactor Auth Middleware
════════════════════════════════════════════════════════════════════════

  4 thinking block(s) found

────────────────────────────────────────────────────────────────────────
  Block 1  ·  step 3c82f1a0-11e4-4b9d-8c77-d04a692f3e51
────────────────────────────────────────────────────────────────────────

  The user wants to refactor the JWT validation logic out of the
  Express middleware and into a dedicated service class. Let me read
  the current middleware file first to understand what's there before
  making any changes.

────────────────────────────────────────────────────────────────────────
  Block 2  ·  step 7fa04d2b-8831-4c1e-b392-0e5c18d9a743
────────────────────────────────────────────────────────────────────────

  I can see the middleware is doing three things: token extraction
  from the Authorization header, JWT verification against the secret,
  and role checking. The role checking logic is tangled in with the
  token verification which is going to make this harder to test in
  isolation. I should separate those two concerns — a TokenService for
  the cryptographic parts and a separate RoleGuard for authorization
  policy. That way each can be unit tested independently without
  needing a real token...
  ...
```

At the bottom of the screen:

```
› S = save to file,  B = back,  Q = quit  [S / B / Q]:
```

Press **S** to save, which prompts for a file path (defaulting to the current
directory with an auto-generated filename), **B** to go back to the tasks list,
or **Q** to quit.

---

## How it works

### Where Warp stores thinking text

Warp keeps its agent data in a local SQLite database:

| Platform | Path |
|----------|------|
| macOS    | `~/Library/Group Containers/2BBY89MBSN.dev.warp/Library/Application Support/dev.warp.Warp-Stable/warp.sqlite` |
| Linux    | `~/.local/state/warp-terminal/warp.sqlite` |
| Windows  | `%LOCALAPPDATA%\warp\Warp\data\warp.sqlite` |

The relevant tables are:

- **`agent_conversations`** — one row per conversation thread; stores metadata
  and token usage
- **`agent_tasks`** — one row per agent run; stores the full task data as a
  binary blob
- **`ai_queries`** — one row per user message; used here to reconstruct
  conversation titles from the first user prompt

### Binary format

Each `agent_tasks.task` blob is encoded as a
[Protocol Buffers](https://protobuf.dev/) message. The script parses this binary
format without a schema, using the wire-format rules directly:

```
Task message
  Field 1  →  task_id (string)
  Field 2  →  task title (string)
  Field 5  →  repeated step messages
    Step message
      Field 1   →  step_id (string)
      Field 15  →  thinking block (nested message)
                     contains the raw thinking text as a string field
      Field 3   →  text response block
      Field 4   →  tool use block
      Field 5   →  tool result block
```

Field 15 of each step message is where the thinking text lives. The script walks
every step in the task, extracts any field-15 content, and returns it as a list
of thinking blocks — one per reasoning step.

The protobuf parsing is done entirely in Python with no external dependencies,
using a simple varint reader and field walker (~50 lines of code).

---

## Limitations

- **No thinking = no output.** Simple or short agent responses may not have
  triggered extended reasoning. The script will say so clearly.
- **Task granularity.** Thinking is stored per task, not per conversation. A
  conversation with five separate agent runs has five tasks; you pick each one
  individually.
- **Local database only.** Tasks that ran on a different machine are not in your
  local database unless cloud sync is enabled and you have re-opened those
  conversations.
- **Protobuf schema is undocumented.** The field numbers were determined by
  inspection. A future Warp update could change the binary layout, which would
  require updating the field numbers in the parser.

---

## Author

**Lester Wilson**
lester.wilson@gmail.com

Built as a workaround for [warpdotdev/warp#9702](https://github.com/warpdotdev/warp/issues/9702)
— *Feature request: Persist agent thinking/reasoning output for review after
response completes.*

---

## Licence

MIT — do whatever you like with it.
