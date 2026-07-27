# memory-graph

Project compass for GitHub Copilot.

## Working On

<!-- Edit this section: what you are building this week (1–3 sentences). -->
_Not set._

## Codebase

This project uses memory-graph for persistent agent memory. Key abstractions:
- `sandbox_repo()` — test fixture for hook tests
- `mg_config.py` — unified config loader
- `on-session-end.sh` — orchestrates the stop pipeline

## Where to go

- **Team knowledge:** `AGENTS.md` + `.agents/skills/` (conventions, workflows)
- **Living state:** `memory/state.yaml` (working memory)
- **Session index:** `memory.md` + `sessions/`
- **Full graph:** `graphify-out/GRAPH_REPORT.md`

## Memory tiers

| Tier | Path | Who writes |
|------|------|------------|
| Hot | `memory/state.yaml` | hooks (compress) |
| Warm | `sessions/*.md` | hooks (session end) |
| Cold | `sessions/archive/` | hooks (daily archive) |

## Hooks

Hooks fire at session start/end. See `.github/hooks/memory-graph.json`.

The Copilot adapters in `scripts/adapters/` translate Copilot payloads and call
the shared Cursor hooks in `.cursor/hooks/`.

## Graphify

This project has a knowledge graph at `graphify-out/`. Before answering
architecture questions, check `graphify-out/GRAPH_REPORT.md` for god nodes
and community structure.

After modifying code files, run `graphify update .` to keep the graph current.
