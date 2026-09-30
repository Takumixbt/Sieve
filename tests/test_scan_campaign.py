"""`sieve scan`, the campaign topology and its contracts."""
from __future__ import annotations

import os
import tempfile
import time
import unittest

from tests import harness as H

from sieve import campaign as C
from sieve import campaign_schema as schema
from sieve import scan as scanlib
from sieve.cli_campaign import _StubEng, lint_default_topology


class DetectTests(unittest.TestCase):
    def test_solidity_tree_is_web3(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = H.make_target(tmp, git=False)
            self.assertEqual(scanlib.detect_packs(root), ["web3"])

    def test_web_framework_tree_is_web(self):
        with tempfile.TemporaryDirectory() as tmp:
            H.write(os.path.join(tmp, "package.json"), '{"dependencies": {"express": "4"}}')
            H.write(os.path.join(tmp, "app.js"), "const app = require('express')()")
            self.assertEqual(scanlib.detect_packs(tmp), ["web"])

    def test_hardhat_tooling_js_next_to_contracts_is_not_a_web_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "contracts"))
            H.write(os.path.join(tmp, "contracts", "A.sol"), "contract A {}")
            for i in range(10):
                H.write(os.path.join(tmp, f"deploy{i}.js"), "// deploy script")
            self.assertEqual(scanlib.detect_packs(tmp), ["web3"])

    def test_c_sources_are_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            for n in ("a.c", "b.c", "c.h"):
                H.write(os.path.join(tmp, n), "int main(){}")
            self.assertEqual(scanlib.detect_packs(tmp), ["binary"])

    def test_empty_tree_detects_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(scanlib.detect_packs(tmp), [])


class RecommendTests(unittest.TestCase):
    def test_depth_follows_size(self):
        self.assertEqual(scanlib.recommend({"kloc": 0.3, "packs": ["web3"], "entry_points": 4})[0], "lite")
        self.assertEqual(scanlib.recommend({"kloc": 6, "packs": ["web3"], "entry_points": 40})[0], "default")
        self.assertEqual(scanlib.recommend({"kloc": 22, "packs": ["web3"], "entry_points": 90})[0], "exhaustive")
        self.assertEqual(scanlib.recommend({"kloc": 9, "packs": ["web3", "web"], "entry_points": 50})[0], "exhaustive")
        self.assertEqual(scanlib.recommend({"kloc": 1, "packs": ["web3", "web", "binary"], "entry_points": 5})[0], "exhaustive")


class ScanTests(unittest.TestCase):
    def test_scan_reuse_is_invalidated_by_an_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            H.isolated_env(tmp)
            root = H.make_target(tmp)
            rc, out = H.cli("scan", root, "--offline", "--quiet")
            self.assertEqual(rc, 0, out)
            from sieve.state import Engagement
            eng = Engagement(root)
            self.assertTrue(scanlib.fresh(eng, "xray"))
            time.sleep(1.1)
            with open(os.path.join(root, "src", "Vault.sol"), "a", newline="\n") as fh:
                fh.write("// changed\n")
            self.assertFalse(scanlib.fresh(eng, "xray"), "an edited tree must not reuse the old scan")

    def test_scan_seeds_the_frontier_and_recommends(self):
        with tempfile.TemporaryDirectory() as tmp:
            H.isolated_env(tmp)
            root = H.make_target(tmp)
            rc, out = H.cli("scan", root, "--offline", "--quiet")
            self.assertEqual(rc, 0, out)
            self.assertIn("recommended", out)
            self.assertIn("lite", out)
            from sieve import frontier
            from sieve.state import Engagement
            self.assertGreater(frontier.stats(Engagement(root))["total"], 0)

    def test_scan_refuses_a_missing_directory(self):
        rc, out = H.cli("scan", os.path.join(tempfile.gettempdir(), "definitely-not-here-xyz"))
        self.assertNotEqual(rc, 0)


class TopologyTests(unittest.TestCase):
    def setUp(self):
        self.topo = C.load_topology(C.default_topology())

    def expand(self, packs, profile):
        nodes = C.expand(self.topo, _StubEng(packs), profile)
        self.assertEqual(C.validate_topology(nodes), [], f"{packs} {profile}")
        return nodes

    def test_every_profile_valid_for_every_pack_combination(self):
        for packs in (["web3"], ["web"], ["binary"], ["web3", "web"], ["web3", "web", "binary"]):
            for prof in ("lite", "default", "exhaustive"):
                self.expand(packs, prof)

    def test_shipped_topology_lints_clean(self):
        self.assertEqual(lint_default_topology(), [])

    def test_lite_drops_the_lens_fan_out_but_keeps_the_gates(self):
        specs = {n["spec"] for n in self.expand(["web3"], "lite")}
        for gone in ("lens", "invariants-merge", "strategy", "fuzz", "independence-audit"):
            self.assertNotIn(gone, specs)
        for kept in ("threat-model", "hunt", "roaming", "triage", "reportability", "prove", "prove-run", "verify", "report"):
            self.assertIn(kept, specs)

    def test_default_and_exhaustive_keep_every_lens_and_the_fuzz_node(self):
        for prof in ("default", "exhaustive"):
            nodes = self.expand(["web3"], prof)
            self.assertEqual(sum(1 for n in nodes if n["spec"] == "lens"), 8)
            self.assertTrue(any(n["spec"] == "fuzz" for n in nodes))
            self.assertTrue(any(n["spec"] == "independence-audit" for n in nodes))

    def test_depth_is_monotonic(self):
        counts = {p: sum(1 for n in self.expand(["web3"], p) if n["kind"] == "agentic") for p in ("lite", "default", "exhaustive")}
        self.assertLess(counts["lite"], counts["default"])
        self.assertLess(counts["default"], counts["exhaustive"])

    def test_pack_specific_nodes(self):
        self.assertFalse(any(n["spec"] == "fuzz" for n in self.expand(["web"], "default")), "fuzzing is a web3 node")
        self.assertTrue(any(n["spec"] == "browser-recon" for n in self.expand(["web"], "lite")))
        self.assertFalse(any(n["spec"] == "browser-recon" for n in self.expand(["web3"], "lite")))

    def test_seed_waits_for_the_x_ray_narrative_in_every_profile(self):
        # Regression: in the lean profile the seed node once ran before the narrative existed.
        for prof in ("lite", "default", "exhaustive"):
            nodes = {n["id"]: n for n in self.expand(["web3"], prof)}
            self.assertIn("narrative-web3", nodes["seed"]["depends_on"], prof)

    def test_drain_waits_for_the_fuzzer(self):
        nodes = {n["id"]: n for n in self.expand(["web3"], "default")}
        self.assertIn("fuzz-absorb", nodes["drain"]["depends_on"])

    def test_estimate_reports_every_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            H.isolated_env(tmp)
            root = H.make_target(tmp)
            H.cli("scan", root, "--offline", "--quiet")
            from sieve.state import Engagement
            est = C.estimate(Engagement(root))
            self.assertEqual(set(est), {"lite", "default", "exhaustive"})
            self.assertLess(est["lite"]["agentic"], est["exhaustive"]["agentic"])


class ContractTests(unittest.TestCase):
    def test_every_contract_example_satisfies_its_own_contract(self):
        for name, c in schema.CONTRACTS.items():
            self.assertEqual(schema.validate_json(name, c["example"]), [], name)

    def test_fuzz_contract_rejects_a_bad_result(self):
        ex = schema.CONTRACTS["fuzz@1"]["example"]
        bad = dict(ex, runs=[dict(ex["runs"][0], result="green")])
        self.assertTrue(schema.validate_json("fuzz@1", bad))

    def test_threat_model_needs_three_goals(self):
        ex = schema.CONTRACTS["threat-model@1"]["example"]
        self.assertTrue(schema.validate_json("threat-model@1", dict(ex, attack_goals=ex["attack_goals"][:1])))


if __name__ == "__main__":
    unittest.main()
