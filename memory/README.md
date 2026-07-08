# Memory map

One-time orientation for humans and agents. **Each session start:** read only `memory/.agent-brief.yaml` (~45 lines).

## Read order

| Tier | Path | What |
|------|------|------|
| **Compass** | `.cursor/rules/main.mdc` | Working On (you edit) + Codebase (graphify/Ollama) |
| **Living** | `memory/.agent-brief.yaml` | Merged open items, context, god nodes, scout |
| **Hot** | `memory/state.yaml` | Hook rollup (included in brief) |
| **Warm** | `sessions/*.md` | Today's sessions (what + why) |
| **Cold** | `sessions/archive/YYYY-MM.yaml` | Prior days + monthly summary |
| **Index** | `memory.md` | Last 30 sessions |

## Config

Single file: `.memory-graph/config.yaml`

```yaml
profile: standard   # standard | token-first | minimal
core: { ... }
ollama: { enabled: false, ... }
```

- `profile: token-first` — Ollama gateway on, slim sessionStart injection
- `profile: minimal` — hooks only, no agent brief
- Legacy `ollama.yaml` still works during migration

## What hooks write vs you

| Field | Who |
|-------|-----|
| `main.mdc` → Working On | **You** (1–3 sentences) |
| `main.mdc` → Codebase | **Hook** (graphify + Ollama) |
| `sessions/*.md` context/why/outcome | **Hook** (transcript fill) + you may refine |
| `memory/.agent-brief.yaml` | **Hook** (assemble-agent-brief) |

## Setup

```bash
bash setup                              # or plugin: memory-graph-setup skill
/graphify .                             # once — graph + Codebase summary
bash scripts/enable-semantic-ollama.sh  # optional local Ollama
```

Ops reference → `docs/cheat-sheet.md`
