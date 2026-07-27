# memory-graph

Persistent agent memory for AI coding assistants — session hooks, tiered compression, graphify integration, and optional Ollama gateway.

## Working On

<!-- Edit this section: what you are building this week (1–3 sentences). -->
_Not set._

## Codebase

Key abstractions (god nodes — touch with care):
- `sandbox_repo()` — test fixture for all hook tests
- `mg_config.py` — unified config loader (profiles + legacy)
- `on-session-end.sh` — orchestrates the full stop pipeline
- `compress-memory.py` — structural compression engine
- `assemble-agent-brief.py` — session-start brief assembly

## Where to go

| What | Path |
|------|------|
| Team knowledge | `AGENTS.md` + `.agents/skills/` |
| Living state | `memory/state.yaml`, `memory/.agent-brief.yaml` |
| Session index | `memory.md` + `sessions/` |
| Full graph | `graphify-out/GRAPH_REPORT.md` |
| Cheat sheet | `docs/cheat-sheet.md` |

## Team knowledge (load by domain)

| Area | Skill |
|------|-------|
| Hooks, scripts, layout | `memory-graph-conventions` |
| `.cursor/hooks/` pipeline | `memory-graph-hooks` |
| `tests/` | `memory-graph-testing` |
| End-to-end feature | `ship-feature` |

## Memory tiers

| Tier | Path | Who writes |
|------|------|------------|
| Hot | `memory/state.yaml` | hooks (compress) |
| Warm | `sessions/*.md` | hooks (session end) |
| Cold | `sessions/archive/` | hooks (daily archive) |

## Hooks

Hooks fire at session start/end. Configuration:
- **Cursor:** `.cursor/hooks.json`
- **Copilot:** `.github/hooks/memory-graph.json`

The Copilot adapters in `scripts/adapters/` translate Copilot payloads and call
the shared Cursor hooks in `.cursor/hooks/`.

## SDLC workflow

| Situation | What to run |
|-----------|-------------|
| Build / implement / fix end-to-end | `ship-feature` skill (grill → research → slice → test → code → validate → commit) |
| Quick fix, 1–2 files | Graph scout → implement directly |
| Touching a god node | Graph scout + drill before editing |

## Graphify

This project has a knowledge graph at `graphify-out/`. Before answering
architecture questions, check `graphify-out/GRAPH_REPORT.md` for god nodes
and community structure.

After modifying code files, run `graphify update .` to keep the graph current.

## Testing

All tests must run without network or LLM. Use `sandbox_repo()` fixture.

```bash
bash scripts/test.sh           # full pytest suite
bash scripts/test-static.sh    # fast syntax/contract checks
```
