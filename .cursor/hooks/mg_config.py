#!/usr/bin/env python3
"""Unified memory-graph config loader.

Supports:
  - Nested config.yaml (profile + core + ollama sections)
  - Legacy flat config.yaml keys at top level
  - Legacy .memory-graph/ollama.yaml overlay
"""

from __future__ import annotations

import re
from pathlib import Path

PROFILE_PRESETS: dict[str, dict] = {
    "minimal": {
        "agent_brief": False,
        "tool_output_compress": False,
        "ollama_context_on_start": False,
        "graph_scout_local": False,
        "graph_scout_on_stop": False,
        "session_fill_from_transcript": True,
    },
    "standard": {
        "agent_brief": True,
        "tool_output_compress": True,
        "ollama_context_on_start": False,
        "graph_scout_local": False,
        "graph_scout_on_stop": True,
        "session_fill_from_transcript": True,
    },
    "token-first": {
        "agent_brief": True,
        "tool_output_compress": True,
        "ollama_context_on_start": True,
        "graph_scout_local": False,
        "graph_scout_on_stop": False,
        "session_fill_from_transcript": True,
    },
}

DEFAULTS: dict = {
    "profile": "standard",
    "track": "auto",
    "git_noise_threshold": 25,
    "scope_max": 40,
    "session_fill_from_transcript": True,
    "session_context_max_chars": 600,
    "archive_why_fields": True,
    "archive_enrich_on_move": True,
    "archive_monthly_summary": True,
    "graph_summary_on_stop": True,
    "graph_scout_local": False,
    "graph_scout_budget": 500,
    "graph_scout_summarize": False,
    "graph_scout_on_stop": True,
    "agent_brief": True,
    "agent_brief_max_lines": 45,
    "tool_output_compress": True,
    "tool_output_min_chars": 6000,
    "tool_output_max_summary": 1200,
    "ollama_context_on_start": False,
    "ollama_context_max_lines": 15,
    "ollama_context_cache_mins": 30,
    "ollama_context_max_chars": 1200,
    # ollama section (also exposed flat as ollama_* where useful)
    "enabled": False,
    "host": "http://127.0.0.1:11434",
    "model": "llama3.2:3b",
    "max_archive_chars": 12000,
    "max_archive_files": 2,
    "timeout": 120,
    "temperature": 0.0,
}

_SECTION_KEYS = frozenset({"core", "ollama"})


def _coerce_value(raw: str):
    val = raw.strip().strip('"').strip("'")
    low = val.lower()
    if low in ("true", "false", "yes", "no"):
        return low in ("true", "yes")
    if re.fullmatch(r"-?\d+", val):
        return int(val)
    if re.fullmatch(r"-?\d+\.\d+", val):
        return float(val)
    return val


def _parse_yaml_sections(text: str) -> tuple[str | None, dict, dict, dict]:
    """Return (profile, flat, core, ollama) from config file text."""
    profile: str | None = None
    flat: dict = {}
    core: dict = {}
    ollama: dict = {}
    section: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue

        if not line.startswith((" ", "\t")):
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if key in _SECTION_KEYS and not val:
                section = key
                continue
            section = None
            if key == "profile":
                profile = str(_coerce_value(val))
            else:
                flat[key] = _coerce_value(val)
            continue

        if section == "core":
            key, _, val = stripped.partition(":")
            core[key.strip()] = _coerce_value(val.strip())
        elif section == "ollama":
            key, _, val = stripped.partition(":")
            ollama[key.strip()] = _coerce_value(val.strip())

    return profile, flat, core, ollama


def _read_legacy_ollama(root: Path) -> dict:
    path = root / ".memory-graph" / "ollama.yaml"
    if not path.is_file():
        return {}
    out: dict = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        out[key.strip()] = _coerce_value(val)
    return out


def load_config(root: Path) -> dict:
    """Flat merged config for hooks and scripts."""
    cfg = dict(DEFAULTS)

    path = root / ".memory-graph" / "config.yaml"
    profile_name: str | None = None
    flat: dict = {}
    core: dict = {}
    ollama_sec: dict = {}

    if path.is_file():
        profile_name, flat, core, ollama_sec = _parse_yaml_sections(
            path.read_text(encoding="utf-8", errors="replace")
        )

    if profile_name and profile_name in PROFILE_PRESETS:
        cfg.update(PROFILE_PRESETS[profile_name])
    cfg["profile"] = profile_name or cfg.get("profile", "standard")

    cfg.update(core)
    cfg.update(flat)
    cfg.update(ollama_sec)

    legacy_ollama = _read_legacy_ollama(root)
    if legacy_ollama:
        cfg.update(legacy_ollama)

    if "enabled" in cfg:
        cfg["ollama_enabled"] = bool(cfg["enabled"])

    return cfg


def load_ollama_config(root: Path) -> dict | None:
    """Ollama connection config if enabled; None otherwise."""
    cfg = load_config(root)
    if not cfg.get("enabled"):
        return None
    return {
        "enabled": True,
        "host": str(cfg.get("host", DEFAULTS["host"])),
        "model": str(cfg.get("model", DEFAULTS["model"])),
        "max_archive_chars": int(cfg.get("max_archive_chars", DEFAULTS["max_archive_chars"])),
        "max_archive_files": int(cfg.get("max_archive_files", DEFAULTS["max_archive_files"])),
        "timeout": int(cfg.get("timeout", DEFAULTS["timeout"])),
        "temperature": float(cfg.get("temperature", DEFAULTS["temperature"])),
        "graph_scout_summarize": bool(cfg.get("graph_scout_summarize", False)),
        "archive_monthly_summary": bool(cfg.get("archive_monthly_summary", True)),
    }


def config_bool(cfg: dict, key: str, default: bool = False) -> bool:
    val = cfg.get(key, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "yes", "1")
    return bool(val)
