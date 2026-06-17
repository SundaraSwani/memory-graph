# [REPO_NAME]

This repo uses memory-graph for persistent AI context across sessions.

## Read First

Read `.cursor/rules/main.mdc` before doing anything. It contains:
- Repo purpose and architecture
- God nodes (high-degree files — touch carefully)
- Recent session memory
- Instructions for this session

## Memory System

| File | Updated by | Purpose |
|------|------------|---------|
| `.cursor/rules/main.mdc` | graphify (post-commit) | AI orientation brief |
| `memory.md` | stop hook | Index of all sessions |
| `sessions/YYYY-MM-DD-HH-MM.md` | stop hook + you | Per-session decisions |
| `graphify-out/GRAPH_REPORT.md` | graphify | God nodes, community report |

## End of Every Session

Write `## Decisions` to the current session file in `sessions/`.
Caveman style. What was decided, what was deferred, which god nodes were touched.
