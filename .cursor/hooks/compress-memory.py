#!/usr/bin/env python3
"""memory-graph: deterministic memory compression (no LLM).

Rolls up session frontmatter into memory/state.yaml, archives old sessions,
and trims memory.md. Safe to run on every hook stop or post-commit.
"""

from __future__ import annotations

import os
import re
import sys
from collections import OrderedDict
from datetime import date, datetime, timedelta
from pathlib import Path

ARCHIVE_DAYS = int(os.environ.get("MEMORY_ARCHIVE_DAYS", "14"))
INDEX_KEEP = int(os.environ.get("MEMORY_INDEX_KEEP", "30"))
OPEN_MAX = int(os.environ.get("MEMORY_OPEN_MAX", "10"))
BLOCKED_MAX = int(os.environ.get("MEMORY_BLOCKED_MAX", "5"))
CONTEXT_MAX = int(os.environ.get("MEMORY_CONTEXT_MAX", "5"))
GOD_NODES_MAX = int(os.environ.get("MEMORY_GOD_NODES_MAX", "8"))


def repo_root() -> Path:
    root = os.environ.get("REPO_ROOT")
    if root:
        return Path(root)
    return Path.cwd()


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {"_file": str(path.name)}

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"_file": str(path.name)}

    body = parts[2] if len(parts) > 2 else ""
    data: dict = {"_file": str(path.name)}

    # Legacy sessions: lift first line from ## Decisions if context empty
    if body.strip():
        dm = re.search(r"## Decisions\s*\n+((?:- .+\n?)+)", body)
        if dm:
            first = dm.group(1).strip().splitlines()[0].lstrip("- ").strip()
            if first and not first.startswith("<!--"):
                data["_body_context"] = first

    fm = parts[1]
    m = re.search(r"^date:\s*(\S+)", fm, re.M)
    if m:
        data["date"] = m.group(1)

    m = re.search(r"^session:\s*(\d+)", fm, re.M)
    if m:
        data["session"] = int(m.group(1))

    m = re.search(r'^context:\s*"(.*)"', fm, re.M)
    if m:
        data["context"] = m.group(1).strip()

    for key in ("open", "blocked", "god_nodes_touched", "scope", "facts"):
        data[key] = _yaml_list(fm, key)

    return data


def _yaml_list(body: str, key: str) -> list[str]:
    m = re.search(rf"^{key}:\s*\[\]\s*$", body, re.M)
    if m:
        return []

    block = re.search(rf"^{key}:\s*\n((?:  - .+\n?)*)", body, re.M)
    if not block:
        return []

    return [
        line.strip()[2:].strip().strip('"')
        for line in block.group(1).splitlines()
        if line.strip().startswith("- ")
    ]


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        norm = item.strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _session_sort_key(entry: dict) -> tuple:
    d = entry.get("date", "1970-01-01")
    s = entry.get("session", 0)
    return (d, s)


def _parse_session_date(entry: dict) -> date | None:
    raw = entry.get("date", "")
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _archive_month_path(archive_dir: Path, month: str) -> Path:
    return archive_dir / f"{month}.yaml"


def _append_archive(archive_dir: Path, month: str, entries: list[dict]) -> None:
    if not entries:
        return
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = _archive_month_path(archive_dir, month)

    chunks: list[str] = []
    if dest.exists():
        existing = dest.read_text(encoding="utf-8", errors="replace").strip()
        if existing:
            chunks.append(existing)

    for e in sorted(entries, key=_session_sort_key):
        path: Path = e["_path"]
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        chunks.append(f"---\n# source: {path.name}\n{raw}\n---")

    dest.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def write_state(root: Path, entries: list[dict]) -> None:
    memory_dir = root / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    state_path = memory_dir / "state.yaml"

    entries_sorted = sorted(entries, key=_session_sort_key, reverse=True)

    open_items: list[str] = []
    blocked_items: list[str] = []
    god_nodes: list[str] = []
    contexts: list[str] = []

    for e in entries_sorted:
        open_items.extend(e.get("open") or [])
        blocked_items.extend(e.get("blocked") or [])
        god_nodes.extend(e.get("god_nodes_touched") or [])
        ctx = (e.get("context") or "").strip()
        if ctx:
            prefix = e.get("date", "")[:10]
            contexts.append(f"{prefix}: {ctx}")
        elif e.get("_body_context"):
            prefix = e.get("date", "")[:10]
            contexts.append(f"{prefix}: {e['_body_context'][:200]}")

    open_items = _dedupe_preserve(open_items)[:OPEN_MAX]
    blocked_items = _dedupe_preserve(blocked_items)[:BLOCKED_MAX]
    god_nodes = _dedupe_preserve(god_nodes)[:GOD_NODES_MAX]
    contexts = _dedupe_preserve(contexts)[:CONTEXT_MAX]

    lines = [
        "# Auto-generated by compress-memory.py — working memory for the next agent.",
        "# Read this before architectural work. Full history → sessions/archive/",
        f"updated: {date.today().isoformat()}",
        f"sessions_active: {len(entries)}",
        "",
    ]

    def _list_block(key: str, items: list[str]) -> None:
        lines.append(f"{key}:")
        if not items:
            lines.append("  []")
        else:
            for item in items:
                lines.append(f'  - "{_escape(item)}"')
        lines.append("")

    _list_block("open", open_items)
    _list_block("blocked", blocked_items)
    _list_block("god_nodes_recent", god_nodes)
    _list_block("recent_context", contexts)

    state_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def trim_memory_index(root: Path) -> None:
    index_path = root / "memory.md"
    if not index_path.exists():
        return

    lines = index_path.read_text(encoding="utf-8", errors="replace").splitlines()
    pre_table: list[str] = []
    rows: list[str] = []
    in_rows = False

    for line in lines:
        if re.match(r"^\|[-| ]+\|$", line):
            in_rows = True
            continue
        if re.match(r"^\| Date", line):
            continue
        if line.startswith("> Index trimmed") or line.startswith("> Working memory"):
            continue
        if in_rows and line.startswith("|"):
            rows.append(line)
        elif not in_rows:
            pre_table.append(line)

    while pre_table and pre_table[-1].strip() == "":
        pre_table.pop()

    if not rows:
        return

    kept = rows[-INDEX_KEEP:]
    note = "\n> Working memory → `memory/state.yaml`.\n"
    if len(kept) < len(rows):
        note = (
            f"\n> Index trimmed to last {INDEX_KEEP} rows. "
            f"Working memory → `memory/state.yaml`. Archive → `sessions/archive/`.\n"
        )

    table = [
        "",
        "| Date/Time | Session | Topics | Files | Session File |",
        "|-----------|---------|--------|-------|--------------|",
        *kept,
        "",
    ]
    index_path.write_text("\n".join(pre_table) + note + "\n".join(table), encoding="utf-8")


def compress(root: Path) -> dict:
    sessions_dir = root / "sessions"
    archive_dir = sessions_dir / "archive"
    cutoff = date.today() - timedelta(days=ARCHIVE_DAYS)

    active: list[dict] = []
    to_archive: list[dict] = []

    for path in sorted(sessions_dir.glob("*.md")):
        entry = parse_frontmatter(path)
        entry["_path"] = path
        session_date = _parse_session_date(entry)
        if session_date and session_date < cutoff:
            to_archive.append(entry)
        else:
            active.append(entry)

    by_month: dict[str, list[dict]] = {}
    for entry in to_archive:
        d = _parse_session_date(entry)
        month = d.strftime("%Y-%m") if d else "unknown"
        by_month.setdefault(month, []).append(entry)

    for month, entries in by_month.items():
        _append_archive(archive_dir, month, entries)
        for entry in entries:
            entry["_path"].unlink(missing_ok=True)

    write_state(root, active)
    trim_memory_index(root)

    return {
        "active": len(active),
        "archived": len(to_archive),
        "state": str(root / "memory" / "state.yaml"),
    }


def main() -> int:
    root = repo_root()
    if not (root / "sessions").is_dir():
        return 0
    result = compress(root)
    if os.environ.get("MEMORY_COMPRESS_VERBOSE") == "1":
        print(result, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
