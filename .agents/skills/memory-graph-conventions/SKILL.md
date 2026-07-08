---
name: memory-graph-conventions
description: Conventions for the memory-graph toolkit (Python hooks, bash scripts, sandbox tests, Memory Observatory dashboard). Apply when editing .cursor/hooks/, scripts/, tests/, dashboard/, or docs/ in this repo.
version: 1.0.0
---

# memory-graph toolkit

Persistent agent memory for Cursor repos — session hooks, tiered compression,
graphify integration, and optional Ollama gateway. Apply this skill whenever the
change touches toolkit code (not consumer-repo app logic).

## Layout

```
.cursor/
├── rules/
│   ├── main.mdc              # Always-on compass (Working On + Codebase summary)
│   ├── sdlc.mdc              # Opt-in workflow router → ship-feature
│   └── graphify.mdc          # Graph navigation rules
└── hooks/
    ├── on-session-end.sh     # Main pipeline — session, compress, graphify
    ├── on-session-start.sh   # Agent brief / Ollama context inject
    ├── compress-memory.py    # Structural compression → memory/state.yaml
    ├── assemble-agent-brief.py
    ├── mg_config.py          # Unified config loader (profiles + legacy)
    ├── graph-scout-local.py
    ├── ollama-context-gateway.py
    ├── fill-session-from-transcript.py
    └── semantic-compress-ollama.py

scripts/                      # Enable scripts, test runners, upgrade path
tests/                        # Sandbox unit tests (no network, no LLM)
tests/helpers.py              # sandbox_repo(), load_hook(), write_config()
dashboard/                    # Memory Observatory (scan.py, serve.py)
memory/                       # Living state (hooks write; agents read brief only)
sessions/                     # Daily session files
.memory-graph/
├── config.yaml               # Live config (gitignored in consumer repos)
└── config.example.yaml       # Committed template
docs/cheat-sheet.md           # Ops reference
graphify-out/                 # Auto-generated — never hand-edit
.agents/skills/               # Team knowledge (this file + siblings)
AGENTS.md                     # Skill maintenance contract
```

**Key principle:** hooks are the runtime. Scripts enable features. Tests prove
hook contracts in isolated `/tmp` sandboxes. Skills encode how to change all three.

## God nodes (touch with care)

From graphify — highest blast radius:

| Symbol | Role |
|--------|------|
| `sandbox_repo()` | Test fixture — every hook test depends on it |
| `compress-memory.py` | Structural compression engine |
| `assemble-agent-brief.py` | Session-start brief assembly |
| `mg_config.py` | Single config entry point for all hooks |
| `on-session-end.sh` | Orchestrates the full stop pipeline |
| `scan.py` | Memory Observatory multi-repo scanner |

Before editing a god node: run graph scout. See `graph-scout` skill.

## Config system

- **Single loader:** `mg_config.py` — all hooks import `load_config(repo_root)`.
- **Profiles:** `minimal` | `standard` | `token-first` — presets in `PROFILE_PRESETS`.
- **Legacy:** flat `config.yaml` keys and `.memory-graph/ollama.yaml` still work.
- **New keys:** add to `DEFAULTS`, relevant profile preset, `config.example.yaml`, and a test in `test_mg_config.py`.

Never read config ad-hoc in hooks — always go through `mg_config.load_config()`.

## Memory tiers

| Tier | Path | Who writes |
|------|------|------------|
| Brief | `memory/.agent-brief.yaml` | `assemble-agent-brief.py` (hook) |
| Hot | `memory/state.yaml` | `compress-memory.py` (hook) |
| Warm | `sessions/*.md` | `on-session-end.sh` + transcript fill |
| Cold | `sessions/archive/` | `compress-memory.py` (daily archive) |
| Index | `memory.md` | `on-session-end.sh` |

Agents read `memory/.agent-brief.yaml` at session start — not `state.yaml` directly
(unless gateway is off).

## Investigate before editing

- Hook change → read `on-session-end.sh` pipeline order first.
- Config change → read `mg_config.py` + `config.example.yaml`.
- Test change → read `tests/helpers.py` patterns.
- Use `rg` over `find`. Examples:
  - `rg "load_config" .cursor/hooks/`
  - `rg "sandbox_repo" tests/`

## Build and dev commands

```sh
bash scripts/test.sh              # full pytest suite
bash scripts/test-static.sh       # fast syntax/contract checks
bash scripts/test-compress-sandbox.sh
bash scripts/upgrade-memory-graph.sh   # refresh hooks from toolkit source
/graphify .                       # build or update code graph
graphify update .                 # AST-only update after code edits
```

## Workflows

See `WORKFLOWS.md` in this directory for step-by-step procedures:

- **Adding a hook** — new `.cursor/hooks/` script + tests + config keys
- **Adding a config key** — mg_config → example → test → docs
- **Adding a skill** — SKILL.md + AGENTS.md index + setup copy list
- **Shipping a feature** — use `ship-feature` skill

## See also

Load these skills when the task ventures into a specific area:

- `memory-graph-hooks` — stop/start pipeline, hook contracts, side effects
- `memory-graph-testing` — sandbox tests, fixtures, no-LLM rule
- `ship-feature` — end-to-end development loop with commit-per-slice
- `graph-scout` — pre-edit graph risk assessment
