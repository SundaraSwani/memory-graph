# [REPO_NAME]

Read `.cursor/rules/main.mdc` for architecture, god nodes, and session memory.
Read `.cursor/rules/sdlc.mdc` for the enforced SDLC workflow.

## gstack

Use gstack skills for the full SDLC loop. Available skills:
/office-hours, /spec, /autoplan, /plan-ceo-review, /plan-eng-review, /plan-design-review,
/review, /codex, /qa, /qa-only, /design-review, /ship, /land-and-deploy,
/retro, /learn, /investigate, /document-release, /careful, /guard, /freeze.

Never use `mcp__claude-in-chrome__*` tools — use `/browse` from gstack instead.

## Workflow entry point

New feature or build request → grill first (`/grill-me` or `/grill-with-docs`) → then follow sdlc.mdc.

## Memory

- `memory.md` — session index
- `sessions/` — per-session decision logs (caveman "why" bullets)
- `graphify-out/GRAPH_REPORT.md` — full codebase graph with god nodes
