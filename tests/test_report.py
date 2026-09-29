import os
import unittest

from tests.helpers import make_engagement, sieve, tmpdir  # noqa: F401

from sieve import report, yamlish


def write_finding(eng, fid, **fields):
    meta = {"id": fid, "kind": "FINDING", "pack": "web3", "class": "oracle-manipulation",
            "component": "Vault.rebalance", "title": "t", "severity": "high", "status": "confirmed",
            "confidence": 90}
    meta.update(fields)
    from sieve import util
    util.atomic_write(eng.path("findings", f"{fid}.md"),
                      yamlish.join_frontmatter(meta, "## Root cause\nx\n\n## Attack path\n1. y\n"))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.d = self._t.__enter__()
        self.eng = make_engagement(self.d)

    def tearDown(self):
        self._t.__exit__(None, None, None)

    def test_dedup_keeps_strongest_kind_then_confidence(self):
        write_finding(self.eng, "F-001", group_key="Vault|rebalance|oracle", confidence=60, kind="LEAD")
        write_finding(self.eng, "F-002", group_key="Vault|rebalance|oracle", confidence=90, kind="FINDING")
        items, broken = report.load_findings(self.eng)
        self.assertEqual(broken, [])
        deduped = report.dedup(items)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["id"], "F-002")

    def test_dedup_prefers_higher_confidence_within_same_kind(self):
        write_finding(self.eng, "F-001", group_key="k", confidence=70)
        write_finding(self.eng, "F-002", group_key="k", confidence=95)
        deduped = report.dedup(report.load_findings(self.eng)[0])
        self.assertEqual(deduped[0]["id"], "F-002")

    def test_broken_file_reported_not_dropped_silently(self):
        from sieve import util
        util.atomic_write(self.eng.path("findings", "F-BAD.md"), "no frontmatter here at all\n")
        items, broken = report.load_findings(self.eng)
        self.assertEqual(items, [])
        self.assertIn("F-BAD.md", broken[0])

    def test_size_trigger_shows_top_three_but_counts_are_honest(self):
        for i in range(25):
            write_finding(self.eng, f"F-{i:03d}", group_key=f"k{i}", confidence=50 + i, severity="medium")
        text, counts = report.build(self.eng)
        self.assertEqual(counts["findings"], 25)
        self.assertIn("25 findings", text)
        self.assertEqual(text.count("### 1."), 1)
        self.assertNotIn("### 4.", text)  # only the top 3 print in the terminal-shaped text

    def test_severity_and_confidence_sort(self):
        write_finding(self.eng, "F-low", group_key="a", severity="low", confidence=99)
        write_finding(self.eng, "F-crit", group_key="b", severity="critical", confidence=50)
        text, _ = report.build(self.eng)
        self.assertLess(text.index("F-crit") if "F-crit" in text else text.index("[50]"),
                        text.index("[99]"))

    def test_cli_end_to_end_with_leads_and_coverage(self):
        write_finding(self.eng, "F-001", kind="LEAD", group_key="lead1", code_smells="missing bound check")
        r = sieve("report", cwd=self.d, check=True)
        self.assertIn('"findings": 0', r.stdout)
        self.assertIn('"leads": 1', r.stdout)
        text = open(self.eng.path("report", "report.md")).read()
        self.assertIn("missing bound check", text)
        self.assertIn("Frontier:", text)

    def test_judge_and_prove_cli(self):
        r = sieve("judge", "cand-1", "--verdict", "confirmed", "--reason", "clears all four gates", cwd=self.d, check=True)
        self.assertIn("confirmed", r.stdout)
        r = sieve("prove", "record", "F-001", "--oracle", "fork-test", "--evidence", "test/Poc.t.sol::test_exploit",
                  cwd=self.d, check=True)
        self.assertIn("F-001", r.stdout)
        self.assertTrue(os.path.isfile(self.eng.path("proofs", "F-001-fork-test.json")))


if __name__ == "__main__":
    unittest.main()
