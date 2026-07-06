---
name: graph-scout
description: Query the code graph and return a compact summary. Use at task start in memory-graph repos — never load graph.json into the parent chat.
disable-model-invocation: true
---

# Graph Scout

Parent chat must not read `graphify-out/graph.json` directly.

## Option A — Local scout (preferred when enabled)

When `.memory-graph/config.yaml` has `graph_scout_local: true`:

1. Run: `bash scripts/graph-scout-local.sh "<files or concepts in scope>"`
2. Read `memory/.graph-scout.yaml` (~500 tokens max)
3. Use that summary to plan — do **not** re-query the graph in parent chat

If `drill_subagent: true` in the YAML → run **Drill** below (subagent).

Enable: `bash scripts/enable-graph-scout-local.sh`

## Option B — Subagent scout (fallback)

When local scout is disabled, graph missing, or local run failed:

Spawn as a **subagent** (Task tool).

### Scout

Input: files or concepts in scope for this task.

1. Query via `graphify query "<concept>" --budget 500` or a short Python read of `graphify-out/graph.json`.
2. Return **only** this structure (~500 tokens max):

```
communities: [ids touched]
god_nodes: [{ name, risk, edges }]
risk: LOW | MEDIUM | HIGH | CRITICAL
inbound_callers: [top callers of changed symbols]
recommendation: one sentence for the parent agent
```

## Drill (subagent — if HIGH/CRITICAL or communities > 1)

Runs after Option A when `drill_subagent: true`, or after Option B scout when risk is HIGH/CRITICAL or communities > 1.

Input: flagged god node names from scout.

1. List inbound edges (callers, consumers).
2. Note cross-community seams.
3. Return caller list + test scope suggestion. Max depth 2 — no further recursion.

Parent agent uses the summary to plan; drill output informs review/QA scope only.
