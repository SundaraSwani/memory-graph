---
name: memory-graph-setup
description: >-
  Install or upgrade memory-graph in the current project — unified config,
  session hooks, graphify codebase summary, and tiered memory. Use when setting
  up persistent agent memory or upgrading an existing install.
---

# memory-graph setup

## Quick install

```bash
# From toolkit clone or after plugin install:
bash setup
# or upgrade hooks only (keeps memory/sessions/config):
bash scripts/upgrade-memory-graph.sh
```

## One-time per project

1. Run `/graphify .` — builds code graph + `main.mdc` ## Codebase summary
2. Edit `.cursor/rules/main.mdc` → **## Working On** (your current focus)
3. Copy config: `cp .memory-graph/config.example.yaml .memory-graph/config.yaml`
4. Optional Ollama: `bash scripts/enable-semantic-ollama.sh`

## Config (single file)

`.memory-graph/config.yaml` — `profile: standard | token-first | minimal` plus `core:` and `ollama:` sections.

## Where things live

Read `memory/README.md` once. Each session: only `memory/.agent-brief.yaml`.

## Profiles

| Profile | Use when |
|---------|----------|
| `standard` | Default — agent brief + structural compression |
| `token-first` | Minimize tokens — Ollama gateway at sessionStart |
| `minimal` | Hooks only, no brief injection |

Enable token-first: `bash scripts/enable-token-first.sh`
