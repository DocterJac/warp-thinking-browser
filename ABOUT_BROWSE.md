# warp_thinking_browse

You asked Warp's agent to work through something complex. The model spent two minutes reasoning — weighing trade-offs, catching its own mistakes, arriving at a conclusion you hadn't considered. Then the response appeared, the thinking collapsed into a thumbnail-sized viewport, and all of that reasoning became effectively unreachable. You scroll a tiny window, trying to reconstruct a chain of thought that ran for thousands of words. You paid for that thinking. You just can't read it.

---

## What if

warp_thinking_browse is a terminal browser that reads the Warp SQLite database directly and lets you navigate your conversations, select tasks, and read the full thinking output as plain, scrollable, saveable text. No tiny viewport. No screenshots. Just the reasoning, presented at a size your eyes can actually use.

---

## Why this matters

**For debugging.** When the agent does something unexpected, the thinking tells you why. Not the sanitised explanation in the response — the actual reasoning that led to the decision. The moment where it misread your intent is in there, if you can read it.

**For learning.** Watching how a model reasons through an unfamiliar domain is one of the fastest ways to learn it yourself. But only if you can actually read the reasoning. A collapsed viewport teaches you nothing.

**For prompt refinement.** If the thinking shows the model misunderstood your intent at step two, you know exactly where your prompt failed. The response alone never tells you this — it just shows you the consequence.

**For sharing.** Your colleagues don't have access to your Warp session. A saved thinking file is a self-contained artefact you can paste into a PR comment, a Slack thread, or a post-mortem. The reasoning becomes citable.

---

## What it looks like

A three-screen terminal interface. The first screen lists your 500 most recent conversations by timestamp and opening question. Type a number to open one. The second screen shows every task in that conversation — timestamp, blob size, title, and a definitive `✦ thinking confirmed` or `· no thinking` flag. This is not a guess. It is a confirmed protobuf field probe against the binary data. Pick a task and the third screen displays every thinking block, numbered by step and word-wrapped to 72 characters. Press S to save the full output to a text file.

Two filters let you find what you're looking for when you remember the reasoning but not the session. Title filter narrows by what you asked. Thinking search scans the actual thinking text across every task in the filtered list. They stack: title filter runs first (instant), then thinking search operates on the results.

---

## The data you already have

Warp stores the complete thinking text in its local SQLite database every time the agent runs. It has been doing this since you started using it. Every past session, every reasoning chain — it is all already written to disk. This tool just reads what Warp already saved.

---

*Free. Open source. Runs locally. Your data stays on your machine.*
