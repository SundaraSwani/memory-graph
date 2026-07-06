#!/usr/bin/env python3
"""Memory Observatory — scan repos with memory-graph installed."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_ROOTS = ("~/Desktop", "~/Documents", "~/Projects", "~/dev", "~/code")
DEFAULT_MAX_DEPTH = 4
ACTIVE_MINUTES = 45
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        "target",
        "graphify-out",
    }
)


@dataclass
class RepoMetrics:
    id: str
    label: str
    path: str
    sessions_total: int = 0
    sessions_today: int = 0
    active_now: bool = False
    semantic_enabled: str = "off"
    compression_rate: float = 0.0
    hot_bytes: int = 0
    warm_bytes: int = 0
    cold_bytes: int = 0
    pending_semantic: bool = False
    recent_context: str = ""
    last_change: str = ""
    sessions_by_day: dict[str, int] = field(default_factory=dict)


@dataclass
class SemanticEvent:
    time: str
    repo: str
    mode: str
    before_lines: int
    after_lines: int
    detail: str = ""


@dataclass
class TelemetryEvent:
    time: str
    repo: str
    event: str
    detail: str


def expand_path(raw: str) -> Path:
    return Path(os.path.expanduser(raw.strip())).resolve()


def load_roots() -> list[Path]:
    env = os.environ.get("OBSERVATORY_ROOTS", "").strip()
    if env:
        roots = [expand_path(p) for p in env.split(":") if p.strip()]
    else:
        config = Path.home() / ".memory-graph" / "observatory.yaml"
        roots = _roots_from_yaml(config) if config.is_file() else []
        if not roots:
            roots = [expand_path(p) for p in DEFAULT_ROOTS]

    if os.environ.get("OBSERVATORY_INCLUDE_CWD", "0") == "1":
        cwd = Path.cwd().resolve()
        if cwd not in roots:
            roots.append(cwd)

    # When launched from a project, prefer that repo's root over generic home paths
    for candidate in _memory_repo_ancestors(Path.cwd().resolve()):
        if candidate not in roots:
            roots.insert(0, candidate)

    seen: set[str] = set()
    unique: list[Path] = []
    for r in roots:
        key = str(r)
        if key not in seen and r.is_dir():
            seen.add(key)
            unique.append(r)
    return unique


def _memory_repo_ancestors(start: Path) -> list[Path]:
    out: list[Path] = []
    for parent in [start, *start.parents]:
        if is_memory_repo(parent):
            out.append(parent)
        if parent.parent == parent:
            break
    return out


def _roots_from_yaml(path: Path) -> list[Path]:
    text = path.read_text(encoding="utf-8", errors="replace")
    roots: list[Path] = []
    for line in text.splitlines():
        m = re.match(r"^\s*-\s+(.+)$", line)
        if m and not line.strip().startswith("#"):
            roots.append(expand_path(m.group(1)))
    return roots


def is_memory_repo(path: Path) -> bool:
    return (path / ".memory-graph").is_dir() or (path / "memory" / "state.yaml").is_file()


def discover_repos(roots: list[Path] | None = None, max_depth: int | None = None) -> list[Path]:
    roots = roots or load_roots()
    depth_limit = max_depth or int(os.environ.get("OBSERVATORY_MAX_DEPTH", DEFAULT_MAX_DEPTH))
    found: dict[str, Path] = {}

    for root in roots:
        if is_memory_repo(root):
            found[str(root)] = root
        if not root.is_dir():
            continue
        for dirpath, dirnames, _ in os.walk(root, topdown=True):
            rel_parts = Path(dirpath).relative_to(root).parts
            if len(rel_parts) >= depth_limit:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".")]
            candidate = Path(dirpath)
            if is_memory_repo(candidate):
                found[str(candidate.resolve())] = candidate.resolve()

    return sorted(found.values(), key=lambda p: p.name.lower())


def _file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _dir_bytes(path: Path, pattern: str = "*") -> int:
    if not path.is_dir():
        return 0
    total = 0
    try:
        for f in path.glob(pattern):
            if f.is_file():
                total += _file_bytes(f)
    except OSError:
        pass
    return total


def _parse_simple_yaml_list(text: str, key: str) -> list[str]:
    m = re.search(rf"^{key}:\s*\[\]\s*$", text, re.M)
    if m:
        return []
    block = re.search(rf"^{key}:\s*\n((?:  - .+\n?)*)", text, re.M)
    if not block:
        return []
    return [
        line.strip()[2:].strip().strip('"')
        for line in block.group(1).splitlines()
        if line.strip().startswith("- ")
    ]


def _read_state(repo: Path) -> dict[str, Any]:
    path = repo / "memory" / "state.yaml"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    ctx = _parse_simple_yaml_list(text, "recent_context")
    active = 0
    m = re.search(r"^sessions_active:\s*(\d+)", text, re.M)
    if m:
        active = int(m.group(1))
    return {"recent_context": ctx, "sessions_active": active, "mtime": path.stat().st_mtime}


def _count_memory_index(repo: Path) -> int:
    path = repo / "memory.md"
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(r"^\|\s*\d{4}-\d{2}-\d{2}", text, re.M))


def _parse_session_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {"_file": path.name}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"_file": path.name}
    fm = parts[1]
    data: dict[str, Any] = {"_file": path.name, "mtime": path.stat().st_mtime}
    for key, pattern in (
        ("date", r"^date:\s*(\S+)"),
        ("time", r"^time:\s*(\S+)"),
        ("session", r"^session:\s*(\d+)"),
        ("topics", r'^topics:\s*"(.*)"'),
    ):
        m = re.search(pattern, fm, re.M)
        if m:
            data[key] = m.group(1)
    m = re.search(r'^context:\s*"(.*)"', fm, re.M)
    if m:
        data["context"] = m.group(1).strip()
    scope = _parse_simple_yaml_list(fm, "scope")
    if scope:
        data["scope"] = scope
    return data


def _sessions_today(repo: Path, today: str) -> list[dict[str, Any]]:
    sessions_dir = repo / "sessions"
    if not sessions_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(sessions_dir.glob("*.md")):
        meta = _parse_session_frontmatter(path)
        if meta.get("date") == today:
            out.append(meta)
    return out


def _sessions_by_day(repo: Path, days: int = 7) -> dict[str, int]:
    counts: dict[str, int] = {}
    start = date.today() - timedelta(days=days - 1)
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        counts[d] = 0

    index = repo / "memory.md"
    if index.is_file():
        text = index.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"^\|\s*(\d{4}-\d{2}-\d{2})", text, re.M):
            d = m.group(1)
            if d in counts:
                counts[d] += 1

    sessions_dir = repo / "sessions"
    if sessions_dir.is_dir():
        for path in sessions_dir.glob("*.md"):
            meta = _parse_session_frontmatter(path)
            d = str(meta.get("date", ""))[:10]
            if d in counts:
                counts[d] += 1

    return counts


def _semantic_mode(repo: Path) -> str:
    ollama = repo / ".memory-graph" / "ollama.yaml"
    if ollama.is_file():
        text = ollama.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^enabled:\s*true\s*$", text, re.M | re.I):
            return "ollama"
    auto_flag = repo / ".memory-graph" / "semantic-auto"
    if auto_flag.is_file():
        return "cursor"
    last = repo / "memory" / ".semantic-last-run"
    if last.is_file():
        return "ollama" if ollama.is_file() else "cursor"
    return "off"


def _format_last_change(meta: dict[str, Any]) -> str:
    if not meta:
        return ""
    t = meta.get("time", "")
    d = meta.get("date", "")
    scope = meta.get("scope") or []
    n = len(scope) if isinstance(scope, list) else 0
    topics = meta.get("topics", "")
    if t and d:
        head = f"{t} · {n} files" if n else str(t)
    elif d:
        head = str(d)
    else:
        head = meta.get("_file", "session")
    if topics:
        short = topics if len(topics) < 48 else topics[:45] + "..."
        return f"{head} · {short}"
    ctx = meta.get("context", "")
    if ctx:
        short = ctx if len(ctx) < 48 else ctx[:45] + "..."
        return f"{head} · {short}"
    return head


def _recently_active(repo: Path, state: dict[str, Any], latest_mtime: float) -> bool:
    threshold = datetime.now().timestamp() - ACTIVE_MINUTES * 60
    if latest_mtime >= threshold:
        return True
    if state.get("sessions_active", 0) > 0:
        return state.get("mtime", 0) >= threshold
    changed = repo / ".memory-graph" / "changed-files"
    if changed.is_file() and changed.stat().st_mtime >= threshold:
        return True
    return False


def scan_repo(repo: Path, today: date | None = None) -> RepoMetrics:
    today = today or date.today()
    today_s = today.isoformat()
    state = _read_state(repo)
    ctx_lines = state.get("recent_context") or []
    recent = ctx_lines[0] if ctx_lines else ""

    hot = _file_bytes(repo / "memory" / "state.yaml")
    hot += _file_bytes(repo / "memory" / ".agent-brief.yaml")
    warm = _dir_bytes(repo / "sessions", "*.md")
    cold = _dir_bytes(repo / "sessions" / "archive", "*.yaml")
    cold += _dir_bytes(repo / "sessions" / "archive", "*.yml")
    total = hot + warm + cold
    compression = round((warm + cold) / total, 2) if total else 0.0

    today_sessions = _sessions_today(repo, today_s)
    index_count = _count_memory_index(repo)
    sessions_total = max(index_count, len(today_sessions))

    archive_dir = repo / "sessions" / "archive"
    if archive_dir.is_dir():
        for path in archive_dir.glob("*.yaml"):
            text = path.read_text(encoding="utf-8", errors="replace")
            archive_hits = len(re.findall(r"^\s+date:\s*\d{4}-\d{2}-\d{2}", text, re.M))
            sessions_total = max(sessions_total, index_count + archive_hits)

    latest_meta: dict[str, Any] = {}
    latest_mtime = 0.0
    sessions_dir = repo / "sessions"
    if sessions_dir.is_dir():
        for path in sessions_dir.glob("*.md"):
            meta = _parse_session_frontmatter(path)
            mt = float(meta.get("mtime", 0))
            if mt >= latest_mtime:
                latest_mtime = mt
                latest_meta = meta

    return RepoMetrics(
        id=repo.name,
        label=repo.name,
        path=str(repo),
        sessions_total=sessions_total,
        sessions_today=len(today_sessions),
        active_now=_recently_active(repo, state, latest_mtime),
        semantic_enabled=_semantic_mode(repo),
        compression_rate=compression,
        hot_bytes=hot,
        warm_bytes=warm,
        cold_bytes=cold,
        pending_semantic=(repo / "memory" / ".semantic-pending").is_file(),
        recent_context=recent,
        last_change=_format_last_change(latest_meta),
        sessions_by_day=_sessions_by_day(repo),
    )


def _semantic_events(repo: Path, metrics: RepoMetrics) -> list[SemanticEvent]:
    events: list[SemanticEvent] = []
    last = repo / "memory" / ".semantic-last-run"
    status = repo / "memory" / ".semantic-ollama-status"
    if not last.is_file() and not status.is_file():
        return events
    when = ""
    mode = metrics.semantic_enabled if metrics.semantic_enabled != "off" else "structural"
    detail = ""
    if status.is_file():
        text = status.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^date:\s*(\S+)", text, re.M)
        if m:
            when = m.group(1)
        m = re.search(r"^message:\s*\"(.*)\"", text, re.M)
        if m:
            detail = m.group(1)
        mode = "ollama"
    if last.is_file() and not when:
        when = last.read_text(encoding="utf-8", errors="replace").strip()[:10]
    pending = repo / "memory" / ".semantic-pending"
    before = 18
    after = max(8, len(_read_state(repo).get("recent_context", [])) + 4)
    if pending.is_file():
        detail = pending.read_text(encoding="utf-8", errors="replace").strip()[:120]
        before = 22
    if when:
        events.append(
            SemanticEvent(
                time=when,
                repo=metrics.label,
                mode=mode,
                before_lines=before,
                after_lines=after,
                detail=detail or "distilled working memory",
            )
        )
    return events


def _telemetry(repo: Path, metrics: RepoMetrics) -> list[TelemetryEvent]:
    events: list[TelemetryEvent] = []
    sessions_dir = repo / "sessions"
    if not sessions_dir.is_dir():
        return events
    for path in sorted(sessions_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
        meta = _parse_session_frontmatter(path)
        ts = f"{meta.get('date', '')} {meta.get('time', '')}".strip()
        scope = meta.get("scope") or []
        n = len(scope) if isinstance(scope, list) else 0
        events.append(
            TelemetryEvent(
                time=str(meta.get("time", path.stat().st_mtime))[:8],
                repo=metrics.label,
                event="session end",
                detail=f"{n} files · {metrics.last_change or 'compress OK'}",
            )
        )
    if metrics.pending_semantic:
        events.insert(
            0,
            TelemetryEvent(
                time=datetime.now().strftime("%H:%M:%S"),
                repo=metrics.label,
                event="semantic pending",
                detail="memory cap hit · awaiting distill",
            ),
        )
    state_path = repo / "memory" / "state.yaml"
    if state_path.is_file():
        events.insert(
            0,
            TelemetryEvent(
                time=datetime.fromtimestamp(state_path.stat().st_mtime).strftime("%H:%M:%S"),
                repo=metrics.label,
                event="structural compress",
                detail=f"state.yaml · {metrics.hot_bytes} B hot",
            ),
        )
    return events


def scan_all(roots: list[Path] | None = None) -> dict[str, Any]:
    repos_paths = discover_repos(roots)
    repos = [scan_repo(p) for p in repos_paths]
    semantic_events: list[SemanticEvent] = []
    telemetry: list[TelemetryEvent] = []
    for path, metrics in zip(repos_paths, repos):
        semantic_events.extend(_semantic_events(path, metrics))
        telemetry.extend(_telemetry(path, metrics))

    semantic_events.sort(key=lambda e: e.time, reverse=True)
    telemetry.sort(key=lambda e: e.time, reverse=True)

    total_sessions = sum(r.sessions_total for r in repos)
    today_sessions = sum(r.sessions_today for r in repos)
    pending = sum(1 for r in repos if r.pending_semantic)
    avg_compression = round(sum(r.compression_rate for r in repos) / len(repos), 2) if repos else 0.0

    day_keys = sorted({d for r in repos for d in r.sessions_by_day})
    if not day_keys:
        start = date.today() - timedelta(days=6)
        day_keys = [(start + timedelta(days=i)).isoformat() for i in range(7)]

    series: dict[str, list[int]] = {}
    for r in repos:
        series[r.label] = [r.sessions_by_day.get(d, 0) for d in day_keys]

    return {
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "roots": [str(p) for p in (roots or load_roots())],
        "summary": {
            "repos": len(repos),
            "sessions_today": today_sessions,
            "sessions_total": total_sessions,
            "avg_compression": avg_compression,
            "semantic_pending": pending,
        },
        "repos": [asdict(r) for r in repos],
        "sessions_by_day": {"categories": day_keys, "series": series},
        "semantic_events": [asdict(e) for e in semantic_events[:10]],
        "telemetry": [asdict(e) for e in telemetry[:12]],
    }


def main() -> None:
    print(json.dumps(scan_all(), indent=2))


if __name__ == "__main__":
    main()
