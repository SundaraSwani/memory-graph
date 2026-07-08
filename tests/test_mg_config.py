"""Unit tests for mg_config.py — unified config loader."""

from __future__ import annotations

import unittest

from tests.helpers import load_hook, sandbox_repo, write_config

mg = load_hook("mg_config")


class TestLoadConfig(unittest.TestCase):
    def test_missing_config_returns_defaults(self):
        with sandbox_repo() as root:
            cfg = mg.load_config(root)
        self.assertEqual(cfg["profile"], "standard")
        self.assertTrue(mg.config_bool(cfg, "agent_brief"))

    def test_flat_keys_backward_compat(self):
        with sandbox_repo() as root:
            write_config(
                root,
                """graph_scout_on_stop: true
graph_scout_local: true
agent_brief: true
graph_scout_budget: 500
""",
            )
            cfg = mg.load_config(root)
        self.assertTrue(mg.config_bool(cfg, "graph_scout_on_stop"))
        self.assertTrue(mg.config_bool(cfg, "graph_scout_local"))
        self.assertEqual(cfg["graph_scout_budget"], 500)

    def test_nested_sections_and_profile(self):
        with sandbox_repo() as root:
            write_config(
                root,
                """profile: token-first
core:
  agent_brief_max_lines: 50
ollama:
  enabled: true
  model: llama3.2:3b
""",
            )
            cfg = mg.load_config(root)
        self.assertEqual(cfg["profile"], "token-first")
        self.assertTrue(mg.config_bool(cfg, "ollama_context_on_start"))
        self.assertEqual(cfg["agent_brief_max_lines"], 50)
        self.assertTrue(mg.config_bool(cfg, "enabled"))
        self.assertEqual(cfg["model"], "llama3.2:3b")

    def test_profile_preset_minimal(self):
        with sandbox_repo() as root:
            write_config(root, "profile: minimal\n")
            cfg = mg.load_config(root)
        self.assertFalse(mg.config_bool(cfg, "agent_brief"))
        self.assertFalse(mg.config_bool(cfg, "tool_output_compress"))

    def test_legacy_ollama_yaml_overlay(self):
        with sandbox_repo() as root:
            write_config(root, "profile: standard\n")
            (root / ".memory-graph" / "ollama.yaml").write_text(
                "enabled: true\nmodel: legacy-model\n", encoding="utf-8"
            )
            cfg = mg.load_config(root)
        self.assertTrue(mg.config_bool(cfg, "enabled"))
        self.assertEqual(cfg["model"], "legacy-model")

    def test_load_ollama_config_when_disabled(self):
        with sandbox_repo() as root:
            write_config(root, "profile: standard\nollama:\n  enabled: false\n")
            self.assertIsNone(mg.load_ollama_config(root))

    def test_coerce_bare_numeric_stays_int(self):
        with sandbox_repo() as root:
            write_config(root, "git_noise_threshold: 1\n")
            cfg = mg.load_config(root)
        self.assertEqual(cfg["git_noise_threshold"], 1)
        self.assertIsInstance(cfg["git_noise_threshold"], int)


if __name__ == "__main__":
    unittest.main()
