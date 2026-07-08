# memory-graph Agent Directives

## Skill file maintenance

Skill files under `.agents/skills/` are living documents. When you make a code
change that falls under a skill's domain, update the relevant skill file in the
same change if any of the following apply:

- A dependency, library, or tool is added, removed, or replaced.
- A new shared pattern is established (new hook, helper, convention, or type).
- An existing pattern is retired, superseded, or meaningfully changed.
- A rule in the skill is found to be wrong or incomplete in practice.

Do not defer skill updates to a follow-up. An outdated skill is a bug.

## Read order (every session)

1. `memory/.agent-brief.yaml` — open threads, recent context, graph scout
2. `.cursor/rules/main.mdc` → **Working On** — what the team is building now
3. Domain skill — load the convention skill for the area you are editing (see below)

## Skill index

| Skill | When to load |
|-------|--------------|
| `memory-graph-conventions` | Any change to hooks, scripts, tests, dashboard, or toolkit layout |
| `memory-graph-hooks` | Editing `.cursor/hooks/` or the session hook pipeline |
| `memory-graph-testing` | Adding or changing tests under `tests/` |
| `ship-feature` | End-to-end feature: grill → research → slice → test → code → commit |
| `graph-scout` | Task start — query code graph without loading `graph.json` |
| `memory-graph-setup` | Install or upgrade memory-graph in a target repo |
| `semantic-compress` | Manual semantic compression when caps are hit |
| `grill-me` | Clarifying requirements before building |

Workflow checklists live in `.agents/skills/memory-graph-conventions/WORKFLOWS.md`.

## Living memory vs team knowledge

| Layer | Path | Purpose |
|-------|------|---------|
| **Team knowledge** | `.agents/skills/`, `AGENTS.md` | Stable conventions — how we build |
| **Living state** | `memory/`, `sessions/` | Current threads — what's open right now |
| **Code structure** | `graphify-out/` | Auto-generated graph — what connects to what |

Team knowledge changes when patterns change. Living memory changes every session.
