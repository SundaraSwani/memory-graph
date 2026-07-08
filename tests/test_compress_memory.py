"""Unit tests for compress-memory.py."""

from __future__ import annotations

import os
import unittest
from datetime import date, timedelta
from pathlib import Path

from tests.helpers import load_hook, sandbox_repo, session_md, write_config

cm = load_hook("compress-memory")


class TestParseFrontmatter(unittest.TestCase):
    def test_parses_lists_and_context(self):
        with sandbox_repo() as root:
            path = root / "sessions" / "2026-07-08-1.md"
            path.write_text(
                session_md("2026-07-08", context="did work", open_items=["fix tests"]),
                encoding="utf-8",
            )
            data = cm.parse_frontmatter(path)
        self.assertEqual(data["date"], "2026-07-08")
        self.assertEqual(data["context"], "did work")
        self.assertEqual(data["open"], ["fix tests"])

    def test_legacy_decisions_lift(self):
        with sandbox_repo() as root:
            path = root / "sessions" / "2026-07-08-1.md"
            path.write_text(
                session_md("2026-07-08", body="## Decisions\n- Shipped feature X.\n"),
                encoding="utf-8",
            )
            data = cm.parse_frontmatter(path)
        self.assertEqual(data["_body_context"], "Shipped feature X.")


class TestWriteState(unittest.TestCase):
    def test_merges_and_caps(self):
        with sandbox_repo() as root:
            entries = [
                {
                    "date": "2026-07-08",
                    "open": [f"task {i}" for i in range(15)],
                    "blocked": [],
                    "god_nodes_touched": [],
                    "context": "today work",
                }
            ]
            stats = cm.write_state(root, entries, active_count=1)
            self.assertLessEqual(len(stats["open"]), cm.OPEN_MAX)
            state = (root / "memory" / "state.yaml").read_text(encoding="utf-8")
            self.assertIn("today work", state)

    def test_merges_with_prior_state(self):
        with sandbox_repo() as root:
            (root / "memory" / "state.yaml").write_text(
                'open:\n  - "prior task"\nblocked: []\nrecent_context: []\ngod_nodes_recent: []\n',
                encoding="utf-8",
            )
            entries = [{"date": "2026-07-08", "open": ["new task"], "blocked": [], "context": "ctx"}]
            stats = cm.write_state(root, entries)
        self.assertIn("prior task", stats["open"])
        self.assertIn("new task", stats["open"])


class TestTrimMemoryIndex(unittest.TestCase):
    def test_keeps_last_rows(self):
        with sandbox_repo() as root:
            rows = "\n".join(f"| 2026-05-{i:02d} 10:00 | {i} | t | 1 | [v](s) |" for i in range(1, 36))
            (root / "memory.md").write_text(
                "# Index\n\n| Date/Time | Session | Topics | Files | Session File |\n"
                "|-----------|---------|--------|-------|--------------|\n"
                f"{rows}\n",
                encoding="utf-8",
            )
            cm.trim_memory_index(root)
            text = (root / "memory.md").read_text(encoding="utf-8")
            self.assertEqual(text.count("| 2026"), cm.INDEX_KEEP)
            self.assertIn("Index trimmed", text)


class TestArchiveAndCompress(unittest.TestCase):
    def test_daily_archive_leaves_today_active(self):
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m")
        old_date = (date.today() - timedelta(days=1)).isoformat()
        with sandbox_repo() as root:
            (root / "sessions" / f"{old_date}-1.md").write_text(
                session_md(old_date, context="old"), encoding="utf-8"
            )
            (root / "sessions" / f"{today}-1.md").write_text(
                session_md(today, context="active", open_items=["keep"]), encoding="utf-8"
            )
            result = cm.compress(root)
            archive = root / "sessions" / "archive" / f"{yesterday}.yaml"
            self.assertEqual(result["archived"], 1)
            self.assertEqual(result["active"], 1)
            self.assertFalse((root / "sessions" / f"{old_date}-1.md").exists())
            self.assertTrue(archive.is_file())
            self.assertIn("old", archive.read_text(encoding="utf-8"))
            state = (root / "memory" / "state.yaml").read_text(encoding="utf-8")
            self.assertIn("keep", state)

    def test_idempotent_second_run(self):
        today = date.today().isoformat()
        with sandbox_repo() as root:
            (root / "sessions" / f"{today}-1.md").write_text(
                session_md(today, open_items=["task"]), encoding="utf-8"
            )
            cm.compress(root)
            first_count = len(list((root / "sessions").glob("*.md")))
            cm.compress(root)
            second_count = len(list((root / "sessions").glob("*.md")))
        self.assertEqual(first_count, second_count)
        self.assertEqual(first_count, 1)

    def test_age_mode_archive(self):
        old = (date.today() - timedelta(days=20)).isoformat()
        month = old[:7]
        with sandbox_repo() as root:
            old_mode = os.environ.get("MEMORY_ARCHIVE_MODE")
            old_days = os.environ.get("MEMORY_ARCHIVE_DAYS")
            os.environ["MEMORY_ARCHIVE_MODE"] = "age"
            os.environ["MEMORY_ARCHIVE_DAYS"] = "14"
            try:
                cm.ARCHIVE_MODE = "age"
                cm.ARCHIVE_DAYS = 14
                (root / "sessions" / f"{old}-1.md").write_text(
                    session_md(old, context="aged out"), encoding="utf-8"
                )
                result = cm.compress(root)
                self.assertEqual(result["archived"], 1)
                self.assertTrue((root / "sessions" / "archive" / f"{month}.yaml").is_file())
            finally:
                if old_mode is None:
                    os.environ.pop("MEMORY_ARCHIVE_MODE", None)
                else:
                    os.environ["MEMORY_ARCHIVE_MODE"] = old_mode
                if old_days is None:
                    os.environ.pop("MEMORY_ARCHIVE_DAYS", None)
                else:
                    os.environ["MEMORY_ARCHIVE_DAYS"] = old_days
                cm.ARCHIVE_MODE = os.environ.get("MEMORY_ARCHIVE_MODE", "daily")
                cm.ARCHIVE_DAYS = int(os.environ.get("MEMORY_ARCHIVE_DAYS", "14"))


class TestSemanticPending(unittest.TestCase):
    def test_triggers_on_open_cap(self):
        with sandbox_repo() as root:
            (root / "memory" / ".semantic-last-run").write_text(
                date.today().isoformat(), encoding="utf-8"
            )
            entries = [{"date": "2026-07-08", "open": [f"t{i}" for i in range(cm.OPEN_MAX)]}]
            stats = cm.write_state(root, entries)
            reasons = cm.evaluate_semantic_need(root, stats)
            pending = cm.update_semantic_pending(root, stats)
            self.assertTrue(any("open at cap" in r for r in reasons))
            self.assertTrue(pending)
            self.assertTrue((root / "memory" / ".semantic-pending").is_file())

    def test_clears_when_no_reasons(self):
        with sandbox_repo() as root:
            (root / "memory" / ".semantic-last-run").write_text(
                date.today().isoformat(), encoding="utf-8"
            )
            (root / "memory" / ".semantic-pending").write_text("stale\n", encoding="utf-8")
            stats = {"open": [], "blocked": [], "contexts": [], "god_nodes": []}
            pending = cm.update_semantic_pending(root, stats)
            self.assertFalse(pending)
            self.assertFalse((root / "memory" / ".semantic-pending").exists())


if __name__ == "__main__":
    unittest.main()
