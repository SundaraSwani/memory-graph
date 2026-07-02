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

# daily (default): archive sessions from prior calendar days on every compress run
# age: archive when session_date older than MEMORY_ARCHIVE_DAYS (default 14)
ARCHIVE_MODE = os.environ.get("MEMORY_ARCHIVE_MODE", "daily")
ARCHIVE_DAYS = int(os.environ.get("MEMORY_ARCHIVE_DAYS", "14"))
INDEX_KEEP = int(os.environ.get("MEMORY_INDEX_KEEP", "30"))
OPEN_MAX = int(os.environ.get("MEMORY_OPEN_MAX", "10"))
BLOCKED_MAX = int(os.environ.get("MEMORY_BLOCKED_MAX", "5"))
CONTEXT_MAX = int(os.environ.get("MEMORY_CONTEXT_MAX", "5"))
GOD_NODES_MAX = int(os.environ.get("MEMORY_GOD_NODES_MAX", "8"))
SEMANTIC_INTERVAL_DAYS = int(os.environ.get("MEMORY_SEMANTIC_INTERVAL_DAYS", "7"))
SEMANTIC_ARCHIVE_BYTES = int(os.environ.get("MEMORY_SEMANTIC_ARCHIVE_BYTES", "50000"))


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


def write_state(root: Path, entries: list[dict], active_count: int | None = None) -> None:
    memory_dir = root / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    state_path = memory_dir / "state.yaml"

    prior: dict[str, list[str]] = {"open": [], "blocked": [], "recent_context": [], "god_nodes_recent": []}
    if state_path.exists():
        prior_text = state_path.read_text(encoding="utf-8", errors="replace")
        for key in prior:
            prior[key] = _yaml_list(prior_text, key)

    entries_sorted = sorted(entries, key=_session_sort_key, reverse=True)

    open_items: list[str] = list(prior["open"])
    blocked_items: list[str] = list(prior["blocked"])
    god_nodes: list[str] = list(prior["god_nodes_recent"])
    contexts: list[str] = list(prior["recent_context"])

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
        f"sessions_active: {active_count if active_count is not None else len(entries)}",
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
    return {
        "open": open_items,
        "blocked": blocked_items,
        "contexts": contexts,
        "god_nodes": god_nodes,
        "active_count": active_count if active_count is not None else len(entries),
    }


def _semantic_auto_enabled(root: Path) -> bool:
    if os.environ.get("MEMORY_SEMANTIC_AUTO", "") == "1":
        return True
    return (root / ".memory-graph-semantic-auto").is_file()


def _days_since_semantic(root: Path) -> int:
    stamp = root / "memory" / ".semantic-last-run"
    if not stamp.exists():
        return 9999
    try:
        last = datetime.strptime(stamp.read_text(encoding="utf-8").strip()[:10], "%Y-%m-%d").date()
        return (date.today() - last).days
    except ValueError:
        return 9999


def evaluate_semantic_need(root: Path, stats: dict) -> list[str]:
    reasons: list[str] = []
    if len(stats.get("open") or []) >= OPEN_MAX:
        reasons.append(f"open at cap ({OPEN_MAX})")
    if len(stats.get("contexts") or []) >= CONTEXT_MAX:
        reasons.append(f"recent_context at cap ({CONTEXT_MAX})")
    if len(stats.get("blocked") or []) >= BLOCKED_MAX:
        reasons.append(f"blocked at cap ({BLOCKED_MAX})")

    archive_dir = root / "sessions" / "archive"
    if archive_dir.is_dir():
        archive_bytes = sum(
            f.stat().st_size for f in archive_dir.glob("*.yaml") if f.is_file()
        )
        if archive_bytes >= SEMANTIC_ARCHIVE_BYTES:
            reasons.append(f"archive >= {SEMANTIC_ARCHIVE_BYTES // 1024}KB")

    if _days_since_semantic(root) >= SEMANTIC_INTERVAL_DAYS:
        reasons.append(f"interval >= {SEMANTIC_INTERVAL_DAYS} days")

    return reasons


def update_semantic_pending(root: Path, stats: dict) -> bool:
    """Write or clear memory/.semantic-pending. Returns True if pending."""
    pending = root / "memory" / ".semantic-pending"
    reasons = evaluate_semantic_need(root, stats)
    if not reasons:
        pending.unlink(missing_ok=True)
        return False

    lines = [
        "# Structural memory hit a limit — semantic compress recommended.",
        f"detected: {date.today().isoformat()}",
        "reasons:",
        *[f"  - {r}" for r in reasons],
        "",
        "Run: bash scripts/enable-semantic-ollama.sh (local Ollama, no agent tokens)",
        "  or semantic-compress skill / MEMORY_SEMANTIC_AUTO=1 hook followup.",
    ]
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


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


def _should_archive(session_date: date | None) -> bool:
    if session_date is None:
        return False
    if ARCHIVE_MODE == "daily":
        return session_date < date.today()
    return session_date < date.today() - timedelta(days=ARCHIVE_DAYS)


def compress(root: Path) -> dict:
    sessions_dir = root / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = sessions_dir / "archive"

    active: list[dict] = []
    to_archive: list[dict] = []

    for path in sorted(sessions_dir.glob("*.md")):
        entry = parse_frontmatter(path)
        entry["_path"] = path
        session_date = _parse_session_date(entry)
        if _should_archive(session_date):
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

    # Roll up today + sessions archiving this run so open/context survive daily archive
    stats = write_state(root, active + to_archive, active_count=len(active))
    trim_memory_index(root)
    semantic_pending = update_semantic_pending(root, stats)

    return {
        "active": len(active),
        "archived": len(to_archive),
        "state": str(root / "memory" / "state.yaml"),
        "semantic_pending": semantic_pending,
    }


def main() -> int:
    root = repo_root()
    if len(sys.argv) > 1 and sys.argv[1] == "--check-semantic":
        pending = root / "memory" / ".semantic-pending"
        if pending.is_file():
            print(pending.read_text(encoding="utf-8"), end="")
            return 2
        return 0

    if not (root / "sessions").is_dir() and not (root / "memory" / "state.yaml").is_file():
        return 0
    result = compress(root)
    if os.environ.get("MEMORY_COMPRESS_VERBOSE") == "1":
        print(result, file=sys.stderr)
    if result.get("semantic_pending") and _semantic_auto_enabled(root):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
