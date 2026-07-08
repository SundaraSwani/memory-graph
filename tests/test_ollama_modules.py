"""Unit tests for ollama-context-gateway.py and semantic-compress-ollama.py."""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.helpers import load_hook, sandbox_repo, write_config

gateway = load_hook("ollama-context-gateway")
semantic = load_hook("semantic-compress-ollama")


class TestYamlHelpers(unittest.TestCase):
    def test_extract_yaml_strips_fence_and_prose(self):
        raw = 'Here you go:\n```yaml\nupdated: 2026-07-08\nopen:\n  - "x"\n```'
        out = gateway.extract_yaml(raw)
        self.assertTrue(out.startswith("updated:"))

    def test_validate_context(self):
        good = "updated: 2026-07-08\nopen:\n  - x\nrecent:\n  - y\n"
        bad = "open:\n  - x\n"
        self.assertTrue(gateway.validate_context(good))
        self.assertFalse(gateway.validate_context(bad))

    def test_semantic_validate_output(self):
        self.assertTrue(semantic.validate_output("updated: 2026-07-08\nopen:\n  - x\n"))

    def test_trim_lines(self):
        text = "\n".join(f"line {i}" for i in range(20))
        out = gateway.trim_lines(text, 5)
        self.assertIn("truncated", out)
        self.assertEqual(len(out.splitlines()), 6)


class TestCacheFresh(unittest.TestCase):
    def test_fresh_cache(self):
        with sandbox_repo() as root:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            (root / "memory" / ".cursor-context-meta").write_text(
                f"generated_at: {ts}\n", encoding="utf-8"
            )
            (root / "memory" / ".cursor-context.yaml").write_text("open: []\n", encoding="utf-8")
            self.assertTrue(gateway.cache_fresh(root, 30))

    def test_stale_cache(self):
        with sandbox_repo() as root:
            old = datetime.fromtimestamp(time.time() - 7200, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            (root / "memory" / ".cursor-context-meta").write_text(
                f"generated_at: {old}\n", encoding="utf-8"
            )
            (root / "memory" / ".cursor-context.yaml").write_text("open: []\n", encoding="utf-8")
            self.assertFalse(gateway.cache_fresh(root, 30))


class TestFallbackFromState(unittest.TestCase):
    def test_builds_fallback(self):
        with sandbox_repo() as root:
            (root / "memory" / "state.yaml").write_text(
                "# Auto-generated\nupdated: 2026-07-08\nopen:\n  - \"seed\"\n",
                encoding="utf-8",
            )
            fb = gateway.fallback_from_state(root, 10)
        self.assertIn("fallback", fb)
        self.assertIn("seed", fb)


class TestGatherSource(unittest.TestCase):
    def test_includes_state_pending_and_archive(self):
        with sandbox_repo() as root:
            (root / "memory" / "state.yaml").write_text("open:\n  - seed\n", encoding="utf-8")
            (root / "memory" / ".semantic-pending").write_text("reasons:\n", encoding="utf-8")
            archive = root / "sessions" / "archive"
            archive.mkdir(parents=True)
            (archive / "2026-06.yaml").write_text("archived session\n", encoding="utf-8")
            source = semantic.gather_source(root, 5000, 2)
        self.assertIn("state.yaml", source)
        self.assertIn("semantic-pending", source)
        self.assertIn("2026-06.yaml", source)

    def test_archive_truncation_budget(self):
        with sandbox_repo() as root:
            archive = root / "sessions" / "archive"
            archive.mkdir(parents=True)
            (archive / "2026-07.yaml").write_text("x" * 3000, encoding="utf-8")
            source = semantic.gather_source(root, 1000, 2)
        self.assertIn("truncated", source)


class TestGatewayRun(unittest.TestCase):
    def test_disabled_exits_clean(self):
        with sandbox_repo() as root:
            code = gateway.run(root, dry_run=False, force=False)
            status = (root / "memory" / ".cursor-context-status").read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("disabled", status)

    def test_dry_run_prints_source(self):
        with sandbox_repo() as root:
            write_config(root, "ollama_context_on_start: true\n")
            (root / "memory" / "state.yaml").write_text(
                "open:\n  - dry run seed\n", encoding="utf-8"
            )
            import io
            from contextlib import redirect_stdout

            buf = io.StringIO()
            with redirect_stdout(buf):
                code = gateway.run(root, dry_run=True, force=True)
            out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("dry run seed", out)


class TestSemanticConfig(unittest.TestCase):
    def test_disabled_returns_none(self):
        with sandbox_repo() as root:
            write_config(root, "profile: standard\nollama:\n  enabled: false\n")
            self.assertIsNone(semantic.load_config(root))


if __name__ == "__main__":
    unittest.main()
