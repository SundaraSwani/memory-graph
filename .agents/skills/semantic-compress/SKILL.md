---
name: semantic-compress
description: LLM distillation of repo memory when structural compression hits caps. Use when memory/.semantic-pending exists, or the hook requests semantic compress, or state.yaml feels bloated.
disable-model-invocation: true
---

# Semantic Memory Compress

Structural compress (`compress-memory.py`) merges YAML mechanically. **This skill distills meaning** when lists hit caps or archive grows large.

## When to run

- `memory/.semantic-pending` exists (hook or compress flagged it)
- User asks to compress / summarize session memory
- `open` or `recent_context` in `memory/state.yaml` is at capacity

## Input (read only)

1. `memory/state.yaml` — current hot memory
2. `memory/.semantic-pending` — why structural compress flagged (if present)
3. `sessions/archive/*.yaml` — last 1–2 month files only (not all history)
4. Optional: today's `sessions/*.md` if any

Do **not** load `graphify-out/graph.json`.

## Output

Rewrite `memory/state.yaml` in place. **Max 15 lines** of YAML content (excluding comments):

```yaml
updated: YYYY-MM-DD
sessions_active: N
open:
  - "only still-actionable items"
blocked:
  - "only still-blocking items"
god_nodes_recent:
  - "only still-relevant nodes"
recent_context:
  - "one line: current project state for the next agent"
```

Rules:
- **Drop** resolved `open` items and stale context (meta-sessions, completed work)
- **Merge** duplicate or overlapping bullets into one
- **Keep** exact god node names if still relevant
- **Do not** invent facts not in source files

## After success

1. Delete `memory/.semantic-pending`
2. Write today's date (`YYYY-MM-DD`) to `memory/.semantic-last-run`
3. Do not create a session file for this meta-work unless `.cursor/` changed

Run as a **single pass** — no recursive subagents.
