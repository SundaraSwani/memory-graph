#!/usr/bin/env python3
"""Write ## Codebase section in main.mdc from graphify report + god nodes.

Ledger-triggered (no git). Ollama when enabled; deterministic fallback otherwise.
Preserves ## Working On (human-edited) and ## Where to go sections.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path


def _load_mg_config():
    path = Path(__file__).resolve().parent / "mg_config.py"
    spec = importlib.util.spec_from_file_location("mg_config", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mg = _load_mg_config()


def repo_root() -> Path:
    root = os.environ.get("REPO_ROOT")
    return Path(root) if root else Path.cwd()


def top_god_nodes(graph_path: Path, limit: int = 8) -> list[tuple[str, int]]:
    if not graph_path.is_file():
        return []
    try:
        g = json.loads(graph_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    nodes = g.get("nodes", [])
    links = g.get("links", g.get("edges", []))
    degree: Counter = Counter()
    for e in links:
        degree[e.get("source", "")] += 1
        degree[e.get("target", "")] += 1
    node_by_id = {n["id"]: n for n in nodes}
    out: list[tuple[str, int]] = []
    for nid, deg in degree.most_common(limit):
        label = node_by_id.get(nid, {}).get("label", nid)
        out.append((str(label), int(deg)))
    return out


def read_graph_report(root: Path, max_chars: int = 4000) -> str:
    report = root / "graphify-out" / "GRAPH_REPORT.md"
    if not report.is_file():
        return ""
    text = report.read_text(encoding="utf-8", errors="replace").strip()
    return text[:max_chars]


def deterministic_summary(root: Path) -> str:
    report = read_graph_report(root, 2500)
    gods = top_god_nodes(root / "graphify-out" / "graph.json", 6)
    lines: list[str] = []
    if gods:
        god_bits = ", ".join(f"`{name}` ({deg})" for name, deg in gods[:5])
        lines.append(f"Core abstractions (god nodes): {god_bits}.")
    if report:
        for section in ("Summary", "Community Hubs", "God Nodes"):
            m = re.search(
                rf"## {re.escape(section)}[^\n]*\n(.*?)(?=\n## |\Z)",
                report,
                re.DOTALL,
            )
            if m:
                chunk = re.sub(r"\s+", " ", m.group(1).strip())[:400]
                if chunk:
                    lines.append(chunk)
    if not lines:
        return "_No graph yet. Run `/graphify .` once to build._"
    return " ".join(lines)[:900]


def ollama_summary(root: Path, cfg: dict) -> str | None:
    report = read_graph_report(root, 3500)
    if not report:
        return None
    gods = top_god_nodes(root / "graphify-out" / "graph.json", 8)
    god_lines = "\n".join(f"- {name} ({deg} edges)" for name, deg in gods)
    system = """You summarize a codebase for a coding agent's always-on project brief.

Reply with plain prose only — no YAML, no markdown headings, no bullet lists.
Max 12 lines. Describe: what the repo does, major subsystems/communities, and
which god nodes are central. Be concrete; do not invent modules not in the source."""
    user = f"GRAPH REPORT:\n{report}\n\nGOD NODES:\n{god_lines or '(none)'}"
    url = str(cfg["host"]).rstrip("/") + "/api/chat"
    body = json.dumps(
        {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user[:8000]},
            ],
            "stream": False,
            "options": {"temperature": float(cfg.get("temperature", 0))},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=int(cfg.get("timeout", 60))) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    text = ((data.get("message") or {}).get("content") or "").strip()
    return text[:1200] if text else None


def _default_main_mdc(repo_name: str) -> str:
    return f"""---
description: Project compass — working focus + codebase summary for {repo_name}.
alwaysApply: true
---

# {repo_name}

## Working On

<!-- Edit this section: what you are building this week (1–3 sentences). Hooks never overwrite. -->
_Not set._

## Codebase

<!-- graph-summary-updated: never -->
_No graph yet. Run `/graphify .` once to build._

## Where to go

- **Living state (every session):** `memory/.agent-brief.yaml`
- **Tier map (read once):** `memory/README.md`
- **Full graph report:** `graphify-out/GRAPH_REPORT.md` (via graph scout — not inline)
"""


def _extract_section(mdc: str, heading: str) -> str:
    pat = rf"(## {re.escape(heading)}\n\n)(.*?)(?=\n## |\Z)"
    m = re.search(pat, mdc, re.DOTALL)
    return m.group(2).strip() if m else ""


def _replace_section(mdc: str, heading: str, body: str, marker_comment: str | None = None) -> str:
    body = body.strip()
    if marker_comment:
        body = f"<!-- {marker_comment}: {date.today().isoformat()} -->\n{body}"
    pat = rf"(## {re.escape(heading)}\n\n)(.*?)(?=\n## |\Z)"
    if re.search(pat, mdc, re.DOTALL):
        return re.sub(pat, rf"\g<1>{body}\n\n", mdc, count=1, flags=re.DOTALL)
    return mdc.rstrip() + f"\n\n## {heading}\n\n{body}\n"


def _is_legacy_mdc(mdc: str) -> bool:
    return "## God Nodes" in mdc or "## Session Memory" in mdc or "## Purpose" in mdc


def _migrate_legacy_mdc(mdc: str, repo_name: str) -> str:
    working = _extract_section(mdc, "Purpose")
    if not working or working.startswith("_Not set"):
        working = _extract_section(mdc, "Working On")
    if not working or working.startswith("_Not set"):
        working = "_Not set._"
    return _default_main_mdc(repo_name).replace("_Not set._", working, 1)


def update_main_mdc(root: Path) -> tuple[bool, str]:
    cfg = mg.load_config(root)
    if not mg.config_bool(cfg, "graph_summary_on_stop", True):
        return False, "graph_summary_on_stop disabled"

    mdc_path = root / ".cursor/rules" / "main.mdc"
    repo_name = root.name
    if mdc_path.is_file():
        mdc = mdc_path.read_text(encoding="utf-8", errors="replace")
        if _is_legacy_mdc(mdc) and "## Codebase" not in mdc:
            mdc = _migrate_legacy_mdc(mdc, repo_name)
    else:
        mdc_path.parent.mkdir(parents=True, exist_ok=True)
        mdc = _default_main_mdc(repo_name)

    working_on = _extract_section(mdc, "Working On")
    if not working_on:
        working_on = "_Not set._"

    ollama_cfg = mg.load_ollama_config(root)
    summary = None
    if ollama_cfg:
        summary = ollama_summary(root, ollama_cfg)
    if not summary:
        summary = deterministic_summary(root)

    mdc = _replace_section(mdc, "Working On", working_on)
    mdc = _replace_section(
        mdc, "Codebase", summary, marker_comment="graph-summary-updated"
    )
    if "## Where to go" not in mdc:
        mdc = mdc.rstrip() + (
            "\n\n## Where to go\n\n"
            "- **Living state (every session):** `memory/.agent-brief.yaml`\n"
            "- **Tier map (read once):** `memory/README.md`\n"
        )

    mdc_path.write_text(mdc.strip() + "\n", encoding="utf-8")
    return True, f"updated Codebase ({len(summary)} chars)"


def main() -> int:
    root = repo_root()
    ok, msg = update_main_mdc(root)
    if not ok:
        print(msg, file=sys.stderr)
        return 1
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
