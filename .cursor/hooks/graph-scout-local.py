#!/usr/bin/env python3
"""Local graph scout — graphify traversal without Cursor subagent tokens.

Enable per-repo: bash scripts/enable-graph-scout-local.sh
Config: .memory-graph/config.yaml → graph_scout_local: true

Optional Ollama one-line recommendation: ollama.yaml → graph_scout_summarize: true
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CONFIG = {
    "graph_scout_local": False,
    "graph_scout_budget": 500,
    "graph_scout_summarize": False,
}

DEFAULT_OLLAMA = {
    "enabled": False,
    "host": "http://127.0.0.1:11434",
    "model": "llama3.2:3b",
    "timeout": 60,
}

RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def repo_root() -> Path:
    root = os.environ.get("REPO_ROOT")
    return Path(root) if root else Path.cwd()


def _parse_yaml_lines(path: Path, bool_keys: set[str], int_keys: set[str]) -> dict:
    cfg = {}
    if not path.is_file():
        return cfg
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key in bool_keys:
            cfg[key] = val.lower() in ("true", "yes", "1")
        elif key in int_keys:
            try:
                cfg[key] = int(val)
            except ValueError:
                pass
        elif key in ("host", "model"):
            cfg[key] = val
    return cfg


def load_scout_config(root: Path) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(
        _parse_yaml_lines(
            root / ".memory-graph" / "config.yaml",
            {"graph_scout_local", "graph_scout_summarize"},
            {"graph_scout_budget"},
        )
    )
    return cfg


def load_ollama_config(root: Path) -> dict | None:
    cfg = dict(DEFAULT_OLLAMA)
    cfg.update(
        _parse_yaml_lines(
            root / ".memory-graph" / "ollama.yaml",
            {"enabled", "graph_scout_summarize"},
            {"timeout", "graph_scout_budget"},
        )
    )
    scout = load_scout_config(root)
    if scout.get("graph_scout_summarize"):
        cfg["graph_scout_summarize"] = True
    return cfg if cfg.get("enabled") else None


def write_status(root: Path, ok: bool, message: str) -> None:
    mem = root / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    path = mem / ".graph-scout-status"
    lines = [
        f"ok: {'true' if ok else 'false'}",
        f"date: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"message: \"{message.replace(chr(34), chr(39))}\"",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    err_path = mem / ".graph-scout-last-error"
    if ok:
        err_path.unlink(missing_ok=True)
    else:
        err_path.write_text(message + "\n", encoding="utf-8")


def risk_from_degree(degree: int) -> str:
    if degree >= 200:
        return "CRITICAL"
    if degree >= 100:
        return "HIGH"
    if degree >= 60:
        return "MEDIUM"
    return "LOW"


def max_risk(risks: list[str]) -> str:
    if not risks:
        return "LOW"
    return max(risks, key=lambda r: RISK_ORDER.get(r, 0))


def terms_from_query(query: str) -> list[str]:
    return [t.lower() for t in re.split(r"[\s,;/]+", query) if len(t) > 2]


def load_graph(root: Path):
    import networkx as nx
    from networkx.readwrite import json_graph

    gp = root / "graphify-out" / "graph.json"
    if not gp.is_file():
        raise FileNotFoundError(f"No graph at {gp} — run /graphify . first")
    raw = json.loads(gp.read_text(encoding="utf-8"))
    try:
        return json_graph.node_link_graph(raw, edges="links")
    except TypeError:
        return json_graph.node_link_graph(raw)


def traverse_graph(G, terms: list[str], budget: int) -> tuple[set[str], list[tuple], str]:
    from graphify.serve import _bfs, _score_nodes, _subgraph_to_text

    scored = _score_nodes(G, terms)
    if not scored:
        return set(), [], ""
    start = [nid for _, nid in scored[:5]]
    nodes, edges = _bfs(G, start, depth=2)
    raw = _subgraph_to_text(G, nodes, edges, token_budget=budget)
    return nodes, edges, raw


def inbound_callers(G, nid: str, limit: int = 5) -> list[str]:
    callers: list[tuple[int, str]] = []
    label = G.nodes[nid].get("label", nid)
    if G.is_directed():
        for u in G.predecessors(nid):
            callers.append((G.degree(u), G.nodes[u].get("label", u)))
    else:
        for u in G.neighbors(nid):
            if u == nid:
                continue
            callers.append((G.degree(u), G.nodes[u].get("label", u)))
    callers.sort(reverse=True)
    seen: set[str] = set()
    out: list[str] = []
    for _, name in callers:
        if name == label or name in seen:
            continue
        seen.add(name)
        out.append(name)
        if len(out) >= limit:
            break
    return out


def analyze_subgraph(G, nodes: set[str], terms: list[str]) -> dict:
    communities: set[int] = set()
    god_nodes: list[dict] = []
    risks: list[str] = []
    all_inbound: list[str] = []

    for nid in nodes:
        data = G.nodes[nid]
        comm = data.get("community")
        if comm is not None:
            try:
                communities.add(int(comm))
            except (TypeError, ValueError):
                pass
        degree = int(G.degree(nid))
        r = risk_from_degree(degree)
        risks.append(r)
        label = data.get("label", nid)
        label_l = label.lower()
        term_hit = any(t in label_l or t in nid.lower() for t in terms)
        if r in ("HIGH", "CRITICAL") or (term_hit and degree >= 30):
            god_nodes.append({"name": label, "risk": r, "edges": degree})
            all_inbound.extend(inbound_callers(G, nid))

    god_nodes.sort(key=lambda g: g["edges"], reverse=True)
    # dedupe god nodes by name
    seen_names: set[str] = set()
    deduped_gods = []
    for g in god_nodes:
        if g["name"] in seen_names:
            continue
        seen_names.add(g["name"])
        deduped_gods.append(g)

    risk = max_risk(risks)
    inbound_unique: list[str] = []
    seen_in: set[str] = set()
    for name in all_inbound:
        if name not in seen_in:
            seen_in.add(name)
            inbound_unique.append(name)

    recommendation = deterministic_recommendation(risk, deduped_gods, communities)

    return {
        "communities": sorted(communities),
        "god_nodes": deduped_gods[:8],
        "risk": risk,
        "inbound_callers": inbound_unique[:8],
        "recommendation": recommendation,
    }


def deterministic_recommendation(risk: str, god_nodes: list[dict], communities: set[int]) -> str:
    if risk in ("CRITICAL", "HIGH") and god_nodes:
        return (
            f"High blast radius on {god_nodes[0]['name']} ({god_nodes[0]['risk']}) — "
            "spawn graph-scout drill subagent before editing."
        )
    if len(communities) > 1:
        return (
            f"Task spans {len(communities)} communities — "
            "use drill subagent or graphify path for cross-community seams."
        )
    if god_nodes:
        return f"Moderate coupling near {god_nodes[0]['name']} — read memory/.graph-scout.yaml and proceed."
    return "Low graph risk — proceed; use subagent drill only if scope grows."


def ollama_recommendation(host: str, model: str, timeout: int, scout: dict, raw: str) -> str | None:
    prompt = f"""Summarize this code-graph scout for a parent coding agent in ONE sentence (max 30 words).
Do not invent nodes. Prefer drill subagent if risk is HIGH or CRITICAL.

Scout:
risk: {scout['risk']}
communities: {scout['communities']}
god_nodes: {json.dumps(scout['god_nodes'][:5])}
inbound_callers: {scout['inbound_callers'][:5]}

Subgraph excerpt:
{raw[:2500]}

One sentence recommendation:"""

    url = host.rstrip("/") + "/api/generate"
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = (data.get("response") or "").strip()
    return text.split("\n")[0][:240] if text else None


def yaml_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', "'") + '"'


def write_scout_yaml(root: Path, query: str, scout: dict, budget: int, mode: str) -> Path:
    mem = root / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    out = mem / ".graph-scout.yaml"
    lines = [
        "# Auto-generated by graph-scout-local.py — read instead of loading graph.json.",
        f"query: {yaml_quote(query)}",
        f"updated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"mode: {mode}",
        f"budget: {budget}",
        f"risk: {scout['risk']}",
        f"communities: {scout['communities']}",
        "god_nodes:",
    ]
    if scout["god_nodes"]:
        for g in scout["god_nodes"]:
            lines.append(
                f"  - {{ name: {yaml_quote(g['name'])}, risk: {g['risk']}, edges: {g['edges']} }}"
            )
    else:
        lines.append("  []")
    lines.append("inbound_callers:")
    if scout["inbound_callers"]:
        for name in scout["inbound_callers"]:
            lines.append(f"  - {yaml_quote(name)}")
    else:
        lines.append("  []")
    lines.append(f"recommendation: {yaml_quote(scout['recommendation'])}")
    if scout["risk"] in ("HIGH", "CRITICAL") or len(scout["communities"]) > 1:
        lines.append("drill_subagent: true")
    else:
        lines.append("drill_subagent: false")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def run(root: Path, query: str, dry_run: bool = False) -> int:
    cfg = load_scout_config(root)
    if not cfg.get("graph_scout_local"):
        msg = "Local graph scout not enabled. Run: bash scripts/enable-graph-scout-local.sh"
        write_status(root, False, msg)
        print(msg, file=sys.stderr)
        return 1

    if not query.strip():
        msg = "Usage: graph-scout-local.py \"files or concepts in scope\""
        write_status(root, False, msg)
        print(msg, file=sys.stderr)
        return 1

    budget = int(cfg.get("graph_scout_budget") or 500)
    terms = terms_from_query(query)

    try:
        G = load_graph(root)
    except FileNotFoundError as e:
        msg = str(e)
        write_status(root, False, msg)
        print(msg, file=sys.stderr)
        return 2
    except ImportError:
        msg = "graphify not installed — pip install graphifyy"
        write_status(root, False, msg)
        print(msg, file=sys.stderr)
        return 2

    if not terms:
        terms = terms_from_query(query.replace("/", " "))

    nodes, _edges, raw = traverse_graph(G, terms, budget)
    if not nodes:
        scout = {
            "communities": [],
            "god_nodes": [],
            "risk": "LOW",
            "inbound_callers": [],
            "recommendation": "No graph nodes matched — use graph-scout subagent or /graphify .",
        }
        mode = "local-no-match"
    else:
        scout = analyze_subgraph(G, nodes, terms)
        mode = "local"

    ollama_cfg = load_ollama_config(root)
    summarize = bool(cfg.get("graph_scout_summarize") or (ollama_cfg and ollama_cfg.get("graph_scout_summarize")))
    if summarize and ollama_cfg and raw:
        try:
            rec = ollama_recommendation(
                ollama_cfg["host"],
                ollama_cfg["model"],
                int(ollama_cfg.get("timeout") or 60),
                scout,
                raw,
            )
            if rec:
                scout["recommendation"] = rec
                mode = mode + "+ollama"
        except urllib.error.URLError as e:
            # Keep deterministic recommendation; warn in status
            write_status(root, True, f"scout ok (ollama summarize failed: {e})")
            if dry_run:
                print(f"# ollama summarize failed: {e}", file=sys.stderr)

    if dry_run:
        print(json.dumps({"mode": mode, "scout": scout, "raw_excerpt": raw[:1500]}, indent=2))
        return 0

    write_scout_yaml(root, query, scout, budget, mode)
    write_status(root, True, f"scout ok ({mode})")
    _maybe_assemble_brief(root)
    print(f"Wrote {root / 'memory' / '.graph-scout.yaml'} (risk={scout['risk']})")
    return 0


def _maybe_assemble_brief(root: Path) -> None:
    brief_py = root / ".cursor" / "hooks" / "assemble-agent-brief.py"
    if not brief_py.is_file():
        return
    try:
        import subprocess

        subprocess.run(
            [sys.executable, str(brief_py)],
            env={**os.environ, "REPO_ROOT": str(root)},
            capture_output=True,
            timeout=30,
            check=False,
        )
    except Exception:
        pass


def check(root: Path) -> int:
    cfg = load_scout_config(root)
    gp = root / "graphify-out" / "graph.json"
    print("Graph scout local:")
    print(f"  enabled: {bool(cfg.get('graph_scout_local'))}")
    print(f"  budget: {cfg.get('graph_scout_budget', 500)}")
    print(f"  ollama summarize: {bool(cfg.get('graph_scout_summarize'))}")
    if gp.is_file():
        print(f"  graph: {gp} (ok)")
    else:
        print(f"  graph: missing — run /graphify .")
        return 2
    if not cfg.get("graph_scout_local"):
        print("\nEnable: bash scripts/enable-graph-scout-local.sh")
        return 1
    try:
        import graphify  # noqa: F401
    except ImportError:
        print("  graphify package: missing — pip install graphifyy")
        return 2
    print("  graphify package: ok")
    return 0


def main() -> int:
    root = repo_root()
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        return check(root)
    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run":
        query = " ".join(sys.argv[2:]).strip()
        cfg = load_scout_config(root)
        if not cfg.get("graph_scout_local"):
            print("Enable local scout first: bash scripts/enable-graph-scout-local.sh", file=sys.stderr)
            return 1
        return run(root, query, dry_run=True)
    query = " ".join(sys.argv[1:]).strip()
    return run(root, query, dry_run=False)


if __name__ == "__main__":
    sys.exit(main())
