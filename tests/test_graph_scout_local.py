"""Unit tests for graph-scout-local.py."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.helpers import ROOT, load_hook, sandbox_repo, write_config

gs = load_hook("graph-scout-local")

FIXTURE_GRAPH = ROOT / "tests" / "fixtures" / "minimal_graph.json"

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

try:
    import graphify  # noqa: F401

    HAS_GRAPHIFY = True
except ImportError:
    HAS_GRAPHIFY = False


class TestRiskHelpers(unittest.TestCase):
    def test_risk_from_degree(self):
        self.assertEqual(gs.risk_from_degree(10), "LOW")
        self.assertEqual(gs.risk_from_degree(70), "MEDIUM")
        self.assertEqual(gs.risk_from_degree(120), "HIGH")
        self.assertEqual(gs.risk_from_degree(250), "CRITICAL")

    def test_max_risk(self):
        self.assertEqual(gs.max_risk(["LOW", "HIGH", "MEDIUM"]), "HIGH")


class TestTermsFromQuery(unittest.TestCase):
    def test_tokenizes(self):
        terms = gs.terms_from_query("compress-memory.py graph scout")
        self.assertIn("compress-memory.py", terms)
        self.assertIn("scout", terms)
        self.assertNotIn("py", terms)


class TestDeterministicRecommendation(unittest.TestCase):
    def test_critical_god_node(self):
        gods = [{"name": "compress-memory.py", "risk": "CRITICAL", "edges": 200}]
        rec = gs.deterministic_recommendation("CRITICAL", gods, {1})
        self.assertIn("drill subagent", rec)

    def test_multi_community(self):
        rec = gs.deterministic_recommendation("LOW", [], {1, 2, 3})
        self.assertIn("3 communities", rec)

    def test_low_risk(self):
        rec = gs.deterministic_recommendation("LOW", [], set())
        self.assertIn("Low graph risk", rec)


class TestWriteScoutYaml(unittest.TestCase):
    def test_drill_flag_for_high_risk(self):
        with sandbox_repo() as root:
            scout = {
                "risk": "HIGH",
                "communities": [1],
                "god_nodes": [{"name": "foo.py", "risk": "HIGH", "edges": 120}],
                "inbound_callers": ["bar.py"],
                "recommendation": "careful",
            }
            path = gs.write_scout_yaml(root, "foo", scout, 500, "local")
            text = path.read_text(encoding="utf-8")
            self.assertIn("drill_subagent: true", text)
            self.assertIn("foo.py", text)

    def test_drill_flag_for_multi_community(self):
        with sandbox_repo() as root:
            scout = {
                "risk": "LOW",
                "communities": [1, 2],
                "god_nodes": [],
                "inbound_callers": [],
                "recommendation": "span",
            }
            path = gs.write_scout_yaml(root, "q", scout, 500, "local")
            text = path.read_text(encoding="utf-8")
            self.assertIn("drill_subagent: true", text)


class TestConfigParsing(unittest.TestCase):
    def test_scout_config(self):
        with sandbox_repo() as root:
            write_config(
                root,
                "graph_scout_local: true\ngraph_scout_budget: 750\ngraph_scout_summarize: true\n",
            )
            cfg = gs.load_scout_config(root)
        self.assertTrue(cfg["graph_scout_local"])
        self.assertEqual(cfg["graph_scout_budget"], 750)
        self.assertTrue(cfg["graph_scout_summarize"])

    def test_ollama_config_requires_enabled(self):
        with sandbox_repo() as root:
            (root / ".memory-graph" / "ollama.yaml").write_text(
                "enabled: false\nhost: http://127.0.0.1:11434\n", encoding="utf-8"
            )
            self.assertIsNone(gs.load_ollama_config(root))


@unittest.skipUnless(HAS_NETWORKX, "networkx not installed")
class TestGraphIntegration(unittest.TestCase):
    def _build_graph(self):
        G = nx.Graph()
        G.add_node(
            "node_a",
            label="compress-memory.py",
            community=1,
        )
        G.add_node("node_b", label="helper.py", community=1)
        G.add_node("node_c", label="other.py", community=2)
        G.add_edge("node_a", "node_b")
        G.add_edge("node_b", "node_c")
        # inflate degree on node_a
        for i in range(110):
            nid = f"caller_{i}"
            G.add_node(nid, label=f"caller_{i}.py", community=1)
            G.add_edge(nid, "node_a")
        return G

    def test_analyze_subgraph(self):
        G = self._build_graph()
        scout = gs.analyze_subgraph(G, set(G.nodes), ["compress"])
        self.assertIn(scout["risk"], ("HIGH", "CRITICAL"))
        self.assertTrue(scout["god_nodes"])

    @unittest.skipUnless(FIXTURE_GRAPH.is_file(), "fixture graph missing")
    def test_load_graph_from_fixture(self):
        with sandbox_repo() as root:
            dest = root / "graphify-out"
            dest.mkdir(parents=True)
            dest.joinpath("graph.json").write_text(
                FIXTURE_GRAPH.read_text(encoding="utf-8"), encoding="utf-8"
            )
            G = gs.load_graph(root)
        self.assertGreater(G.number_of_nodes(), 0)

    @unittest.skipUnless(HAS_GRAPHIFY and FIXTURE_GRAPH.is_file(), "graphify or fixture missing")
    def test_traverse_graph_with_fixture(self):
        with sandbox_repo() as root:
            dest = root / "graphify-out"
            dest.mkdir(parents=True)
            dest.joinpath("graph.json").write_text(
                FIXTURE_GRAPH.read_text(encoding="utf-8"), encoding="utf-8"
            )
            G = gs.load_graph(root)
            nodes, _edges, raw = gs.traverse_graph(G, ["compress"], 500)
        self.assertTrue(nodes or raw == "")


if __name__ == "__main__":
    unittest.main()
