---
name: graph-scout
description: Query the code graph via subagent and return a compact summary. Use at task start in memory-graph repos — never load graph.json into the parent chat.
disable-model-invocation: true
---

# Graph Scout

Spawn as a **subagent** (Task tool). Parent chat must not read `graphify-out/graph.json` directly.

## Scout (always)

Input: files or concepts in scope for this task.

1. Query via `graphify query "<concept>"` or a short Python read of `graphify-out/graph.json`.
2. Return **only** this structure (~500 tokens max):

```
communities: [ids touched]
god_nodes: [{ name, risk, edges }]
risk: LOW | MEDIUM | HIGH | CRITICAL
inbound_callers: [top callers of changed symbols]
recommendation: one sentence for the parent agent
```

## Drill (if scout risk is HIGH/CRITICAL or communities > 1)

Input: flagged god node names from scout.

1. List inbound edges (callers, consumers).
2. Note cross-community seams.
3. Return caller list + test scope suggestion. Max depth 2 — no further recursion.

Parent agent uses the summary to plan; drill output informs review/QA scope only.
