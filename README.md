# memory-graph

Give any repo a persistent brain that survives agent sessions — without bloating every Cursor turn.

**Design goal:** cut Cursor context per turn via an Ollama context gateway; persistent memory on session stop, slim injection on session start.

---

## What it does

| Layer | What | Token cost |
|-------|------|------------|
| **Brief** | `.cursor/rules/main.mdc` — purpose + god nodes table | ~small, always loaded |
| **Context gateway** | `memory/.cursor-context.yaml` — Ollama distill at stop, inject at start | ~1200 chars / sessionStart |
| **Agent brief** | `memory/.agent-brief.yaml` — fallback when gateway off | One read / sessionStart inject |
| **Working memory** | `memory/state.yaml` — hook-maintained rollup | Not read directly when gateway on |
| **Sessions** | `sessions/` + `memory.md` index | Written by hook; read by Ollama at stop only |
| **Graph** | graphify → local scout on demand | Off by default in token-first profile |
| **Tool compress** | `postToolUse` hook — large Shell/Grep/Read | Rules-based, no LLM |
| **Compression** | Structural (every stop) + semantic (opt-in Ollama) | Structural = free |

---

## Quick start

```bash
cd /your/project

curl -sL https://github.com/SundaraSwani/memory-graph/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=1 && bash setup
bash scripts/enable-token-savers.sh    # agent brief + tool compress
bash scripts/enable-token-first.sh     # Ollama gateway + no scout auto-inject (recommended for token savings)
/graphify .    # once — builds graph, populates god nodes in main.mdc
```

→ **[Cheat sheet](docs/cheat-sheet.md)** for commands, env vars, and troubleshooting.

`setup` installs hooks, rules, graphify, and the post-commit hook. **gstack is opt-in:** `INSTALL_GSTACK=1 bash setup`.

---

## How the session hook works

On every agent **stop** (when project files changed):

1. **Smart gate** — skip session file if fewer than 3 files changed and no god-node blast radius
2. **Session file** — structured YAML frontmatter only (no extra agent turn)
3. **Structural compress** — rollup → `memory/state.yaml`, archive prior days
4. **Semantic compress** — only if enabled and caps hit (see below)
5. **Graphify AST update** — background, no LLM (when code files changed)

**Change detection** (`MEMORY_TRACK`, default `auto`):

| Mode | Behavior |
|------|----------|
| `auto` | Cursor ledger first when present; else git diff (deletions stripped when >25 paths) |
| `git` | Git diff only |
| `cursor` | Cursor ledger only — works without git |

Config: `MEMORY_TRACK=…` or `.memory-graph/config.yaml` → `track: auto|git|cursor`

**Session fields:** `context`, `open`, and `blocked` are auto-filled from the stop-hook transcript when empty (Ollama improves quality when enabled).

**Never creates a session for:** pure Q&A, edits under `.cursor/`, `sessions/`, `memory.md`, `graphify-out/`.

```yaml
# sessions/2026-07-02-1.md — example
---
date: 2026-07-02
time: 14:32
session: 1
topics: "app/campaigns, app/signup"
scope:
  - app/campaigns.go
  - app/signup.go
god_nodes_touched: []
open: []
blocked: []
context: ""
facts: []
---
```

The agent may refine `context:` and `open:` after the hook runs. The stop hook auto-fills them from the chat transcript when empty (Ollama when enabled).

---

## Memory tiers (structural compression)

Runs automatically on every file-changing stop and on `git commit`. **No LLM.**

| Tier | Location | Contents |
|------|----------|----------|
| **Hot** | `memory/state.yaml` | Merged `open`, `blocked`, `recent_context`, `god_nodes_recent` |
| **Warm** | `sessions/*.md` | Today's session files |
| **Cold** | `sessions/archive/YYYY-MM.yaml` | Prior days (archived daily by default) |
| **Index** | `memory.md` | Last 30 sessions (trimmed automatically) |

```bash
# Manual run
python3 .cursor/hooks/compress-memory.py

# Keep session files for 14 days instead of daily archive
MEMORY_ARCHIVE_MODE=age MEMORY_ARCHIVE_DAYS=14 python3 .cursor/hooks/compress-memory.py
```

When lists hit their caps (`open` ≥ 10, etc.), the hook writes `memory/.semantic-pending` — your signal to run semantic compression (below).

---

## Semantic compression (optional, per repo)

Structural merge is mechanical — it can't drop stale items or summarize. **Semantic compression** distills memory when caps are hit.

**Default: off.** Each git repo opts in independently. Other repos on your machine are unaffected.

### Option A — Local Ollama (recommended)

Uses your machine. **No Cursor agent tokens.**

**1. Install Ollama** (one-time, system-wide)

```bash
# https://ollama.com/download
ollama serve
ollama pull llama3.2:3b
```

**2. Enable for this repo**

```bash
bash scripts/enable-semantic-ollama.sh
```

Creates `.memory-graph/ollama.yaml` (gitignored). Example template is committed at `.memory-graph/ollama.example.yaml`.

**3. Verify**

```bash
bash scripts/check-ollama.sh
```

**What happens when enabled**

```
Structural caps hit → memory/.semantic-pending
    → hook calls semantic-compress-ollama.py
    → Ollama rewrites memory/state.yaml (≤15 lines)
    → clears pending, no Cursor followup
```

**Status files**

| File | Purpose |
|------|---------|
| `memory/.semantic-ollama-status` | Last run: ok / message |
| `memory/.semantic-ollama-last-error` | Why Ollama failed (server down, model missing, bad output) |

**Config** (`.memory-graph/ollama.yaml`)

```yaml
enabled: true
host: http://127.0.0.1:11434
model: llama3.2:3b          # must match: ollama pull <model>
max_archive_chars: 12000
timeout: 120
```

**Disable for this repo:** `enabled: false` in config, or `rm .memory-graph/ollama.yaml`.

---

### Option B — Cursor agent

Uses the `semantic-compress` skill via a one-time hook followup when caps hit. Costs agent tokens.

```bash
bash scripts/enable-semantic-auto.sh
```

Only use if you don't have Ollama. Don't enable both unless you want Ollama first with agent as fallback.

**Manual check**

```bash
python3 .cursor/hooks/compress-memory.py --check-semantic   # exit 2 if pending
```

---

### Which option should I use?

| | Ollama | Cursor agent |
|---|--------|--------------|
| **Cost** | Free (local GPU/CPU) | Cursor tokens |
| **Setup** | Install Ollama + enable script | One enable script |
| **Privacy** | Stays on your machine | Cloud model |
| **Quality** | Depends on model size | Usually higher |

---

## Graph traversal (graph scout)

Do **not** load `graphify-out/graph.json` into chat.

**Option A — Local (optional, no Cursor tokens):**

```bash
bash scripts/enable-graph-scout-local.sh
bash scripts/graph-scout-local.sh "compress-memory hooks"
# → memory/.graph-scout.yaml (~500 tokens)
```

**Option B — Subagent (default fallback):** scout + drill subagents when local is off or `drill_subagent: true`.

See `.cursor/rules/main.mdc` and `.agents/skills/graph-scout/SKILL.md`.

| Trigger | What runs | LLM? |
|---------|-----------|------|
| Agent stop (code changed) | graphify `--update` (AST) | No |
| `git commit` | graphify full rebuild | Only for new docs/images |
| Manual `/graphify .` | Full pipeline | Yes |

---

## What gets installed

| Path | Purpose |
|------|---------|
| `.cursor/rules/main.mdc` | Slim AI brief (always loaded) |
| `.cursor/rules/sdlc.mdc` | Opt-in workflow router (~50 lines) — points to `ship-feature` |
| `.cursor/hooks/on-session-end.sh` | Session + compress + optional Ollama |
| `.cursor/hooks/track-changed-files.sh` | Cursor afterFileEdit → change ledger |
| `.cursor/hooks/compress-memory.py` | Structural compression |
| `.cursor/hooks/graph-scout-local.py` | Local graph scout (optional) |
| `.cursor/hooks/semantic-compress-ollama.py` | Ollama semantic compression |
| `.cursor/hooks/ollama-context-gateway.py` | Ollama context gateway (sessionStart inject) |
| `scripts/enable-token-first.sh` | Token-first profile (gateway on, scout off) |
| `.memory-graph/ollama.example.yaml` | Ollama config template |
| `memory.md` + `sessions/` | Session index and files |
| `post-commit.sh` | graphify rebuild on commit |

---

## Testing

Sandbox tests use isolated `/tmp` dirs — no network, no LLM.

```bash
bash scripts/test.sh                    # full suite
bash scripts/test-static.sh             # fast syntax/contract checks
bash scripts/test-compress-sandbox.sh   # compression + hook gates
```

**memory-graph development only** — block push if tests fail:

```bash
bash scripts/install-dev-hooks.sh
git push   # runs tests automatically; use --no-verify to skip
```

---

## Optional: gstack + ship-feature

**End-to-end features:** **`ship-feature`** skill — [.agents/skills/ship-feature/SKILL.md](.agents/skills/ship-feature/SKILL.md). Slim router: [sdlc.mdc](.cursor/rules/sdlc.mdc).

**gstack** (optional extras):

```bash
INSTALL_GSTACK=1 bash setup
```

Adds `/spec`, `/review`, `/qa`, `/ship` when you need them outside the ship-feature loop.

---

## Requirements

- **Cursor** — hooks + `.mdc` rules
- **Python 3.8+** — graphify + compression scripts
- **Git**
- **Ollama** — only if using local semantic compression
- **Bun 1.0+** — only if using gstack browser features

---

## Docs

- **[Cheat sheet](docs/cheat-sheet.md)** — install, compress, Ollama, graph, tests, troubleshooting
