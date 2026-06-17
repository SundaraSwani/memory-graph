# memory-graph

Give any repo a persistent brain that survives agent sessions.

Three things it does:
1. **`main.mdc`** — a living AI brief always loaded by Cursor. Populated by graphify with architecture, god nodes, and community structure. The agent reads this before touching anything.
2. **Session memory** — after every agent stop, a hook captures what files changed and creates `sessions/YYYY-MM-DD-HH-MM.md`. You append caveman-style "why" bullets. `memory.md` is the index.
3. **Graph rebuild** — incremental AST update on every agent stop (fast, no LLM). Full rebuild on every `git commit` (via post-commit hook).

---

## Install (30 seconds)

From inside any project:
git clone this repo
```bash
cd /your/project
~/.cursor/skills/memory-graph/setup
```

Then run `/graphify .` once to build the initial graph and populate `main.mdc`.

---

## What gets installed

| File | What it does |
|------|-------------|
| `.cursor/rules/main.mdc` | AI brief — always loaded by Cursor (`alwaysApply: true`) |
| `.cursor/hooks.json` | Hook config — fires memory + graphify scripts on agent stop |
| `.cursor/hooks/memory-update.sh` | Creates session file + updates memory.md index |
| `.cursor/hooks/graphify-update.sh` | Incremental AST update if code files changed |
| `CLAUDE.md` | Points Claude Code to `main.mdc` |
| `memory.md` | Index of all sessions |
| `sessions/` | Per-session decision logs |
| `post-commit.sh` | Full graphify rebuild — installed to `.git/hooks/post-commit` |

---

## How sessions work

After every agent stop where files changed:

1. Hook creates `sessions/2026-06-17-14-32.md` with frontmatter:
   ```yaml
   ---
   date: 2026-06-17 14:32
   files_changed: 3
   files: [src/auth.ts, src/db.ts, README.md]
   ---
   ```
2. Agent appends `## Decisions` with caveman bullets — the "why":
   ```markdown
   ## Decisions
   - JWT not sessions. Stateless. Simpler.
   - auth.ts now god node. Everything touches it.
   - Refresh token deferred. Ship first.
   ```
3. `memory.md` index row added automatically.

At the next session, the agent reads `main.mdc` (god nodes + architecture) and scans `memory.md` to know what was decided before.

---

## How the graph stays fresh

| Trigger | What runs | LLM? |
|---------|-----------|------|
| Agent stop (code changed) | Incremental AST update | No |
| `git commit` | Full `--update` rebuild | Only for new docs/images |
| Manual `/graphify .` | Full pipeline | Yes |

---

## Requirements

- Cursor (for hooks + `.mdc` rules)
- Python 3.8+ (for graphify)
- Git

graphify is installed automatically by `setup`. Manual: `pip install graphifyy`
