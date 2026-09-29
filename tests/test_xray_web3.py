import os
import unittest

from tests.helpers import ROOT  # noqa: F401

from sieve import xray_web3 as X

FIXROOT = os.path.join(ROOT, "tests", "fixtures", "web3")


class Web3XrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facts = X.run(FIXROOT)

    def test_discovery_and_exclusions(self):
        paths = {f["path"] for f in self.facts["files"]}
        self.assertIn(os.path.join("src", "Vault.sol"), paths)
        self.assertIn(os.path.join("programs", "vault", "src", "lib.rs"), paths)
        self.assertFalse(any("test" in p.split(os.sep) for p in paths))
        self.assertEqual(set(self.facts["languages"]), {"solidity", "vyper", "rust", "move", "cairo"})
        self.assertGreater(self.facts["nsloc_total"], 30)

    def test_entry_candidates_are_raw_not_classified(self):
        hits = {(h["file"].replace(os.sep, "/"), h["line"]) for h in self.facts["entry_candidates"]}
        # deposit() is a real external function -> must appear as a candidate line
        with open(os.path.join(FIXROOT, "src", "Vault.sol")) as fh:
            lines = fh.read().split("\n")
        dep_line = next(i + 1 for i, ln in enumerate(lines) if "function deposit" in ln)
        self.assertIn(("src/Vault.sol", dep_line), hits)
        # the multiline withdraw() signature is caught by the closing-paren pattern
        withdraw_close = next(i + 1 for i, ln in enumerate(lines) if ln.strip() == "external" and "returns" not in lines[i-1])
        self.assertTrue(any(f == "src/Vault.sol" and l >= withdraw_close - 2 for f, l in hits))
        # every candidate carries the exact matched line's text, for the agent to verify by eye
        for h in self.facts["entry_candidates"]:
            self.assertIn("text", h)
            self.assertTrue(h["text"])
        # nothing here says "access" or "role" -- that classification is not this module's job
        for h in self.facts["entry_candidates"]:
            self.assertNotIn("access", h)

    def test_tests_inventory(self):
        t = self.facts["tests"]
        self.assertEqual((t["test_files"], t["stateless_fuzz"], t["foundry_invariant"], t["echidna"]), (1, 1, 1, 1))
        self.assertEqual(t["test_functions"], 2)

    def test_nsloc_matches_pashov_heuristic(self):
        text = "// header\nfunction f() {\n  x = 1;\n}\n/* block */\n"
        self.assertEqual(X.nsloc(text, "solidity"), 3)  # blanks out and //-leading and /*-leading only

    def test_tool_leads_are_reshaped_not_reanalysed(self):
        facts = X.run(FIXROOT, slither_json=os.path.join(FIXROOT, "slither.json"),
                      aderyn_json=os.path.join(FIXROOT, "aderyn.json"))
        by_source = {}
        for lead in facts["tool_leads"]:
            by_source.setdefault(lead["source"], []).append(lead)
        self.assertEqual(by_source["slither"][0]["check"], "reentrancy-eth")
        self.assertEqual(by_source["slither"][0]["file"], "src/Vault.sol")
        self.assertEqual(by_source["slither"][0]["line"], 60)
        self.assertEqual({l["check"] for l in by_source["aderyn"]},
                         {"Centralization risk for privileged owner", "Unsafe casting"})
        self.assertEqual(facts["notes"], [])

    def test_tool_lead_bad_file_is_a_note_not_a_crash(self):
        facts = X.run(FIXROOT, slither_json="/no/such/file.json")
        self.assertEqual(facts["tool_leads"], [])
        self.assertTrue(facts["notes"])


if __name__ == "__main__":
    unittest.main()
