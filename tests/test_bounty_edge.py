"""Bug-bounty edge: reasoning markers with substance, a triage panel with different angles, duplicate detection."""
from __future__ import annotations

import os
import unittest

from tests import harness as H

from sieve import blocks, campaign, leads, util
from sieve.state import Engagement


class MarkerTests(unittest.TestCase):
    def test_bare_or_repeated_markers_do_not_count(self):
        text = ("[Feynman] [Socratic] [Inversion]\n"
                "[Feynman: withdraw sends ether before it updates the caller's balance]\n"
                "[Feynman: withdraw sends ether before it updates the caller's balance]\n"
                "[Socratic: why does deposit not check msg.sender against the registry?]\n"
                "[Inversion: what would have to be true for the owner check to be skipped]\n")
        c = blocks.count_markers(text)
        self.assertEqual(c, {"Feynman": 1, "Socratic": 1, "Inversion": 1})

    def test_short_marker_bodies_do_not_count(self):
        self.assertEqual(blocks.count_markers("[Feynman: ok] [Feynman: fine]")["Feynman"], 0)


class PanelTests(unittest.TestCase):
    def test_panelists_get_different_angles(self):
        self.assertGreaterEqual(len(campaign.PANEL_FOCI), 3)
        self.assertEqual(len(set(campaign.PANEL_FOCI)), len(campaign.PANEL_FOCI))

    def test_the_rendered_prompts_differ_by_panelist(self):
        tmp = H.tmpdir(self)
        root = H.new_engagement(tmp, "lite")
        eng = Engagement(root)
        topo, nodes, st = campaign.load(eng, allow_drift=True)
        panel = [n for n in nodes if n["spec"] == "triage"]
        self.assertGreaterEqual(len(panel), 2)
        texts = []
        for n in panel[:2]:
            path, _ = campaign.render_prompt(eng, n, nodes, st["profile"])
            texts.append(util.read_text(path))
        self.assertNotEqual(texts[0], texts[1])
        self.assertIn("CODE PATH", texts[0])
        self.assertIn("ECONOMICS", texts[1])
        self.assertNotIn("{{panel_focus}}", texts[0])


class DuplicateTests(unittest.TestCase):
    def eng(self, known: str) -> Engagement:
        tmp = H.tmpdir(self)
        root = H.new_engagement(tmp, "lite")
        eng = Engagement(root)
        text = util.read_text(eng.case_path()).replace("## Known issues and prior audits", "## Known issues and prior audits\n\n" + known, 1)
        util.atomic_write(eng.case_path(), text)
        return eng

    def test_a_finding_that_restates_a_known_issue_is_flagged(self):
        eng = self.eng("- Reentrancy in Vault.withdraw allows repeated withdrawals (audit 2025-03, issue H-2)")
        hit = leads.possible_duplicate(eng, "Reentrancy in withdraw drains the vault", "Vault.withdraw", "reentrancy")
        self.assertIn("H-2", hit)

    def test_an_unrelated_finding_is_not_flagged(self):
        eng = self.eng("- Reentrancy in Vault.withdraw allows repeated withdrawals (audit 2025-03, issue H-2)")
        self.assertEqual(leads.possible_duplicate(eng, "Oracle price can be manipulated with a flash loan", "Pool.price", "oracle-manipulation"), "")

    def test_no_known_issues_means_no_flag(self):
        eng = self.eng("")
        self.assertEqual(leads.possible_duplicate(eng, "Reentrancy in withdraw", "Vault.withdraw", "reentrancy"), "")


class EndToEndDuplicateTests(unittest.TestCase):
    def test_the_report_carries_the_flag(self):
        tmp = H.tmpdir(self)
        H.isolated_env(tmp)
        root = H.make_target(tmp)
        rc, out = H.cli("scan", root, "--offline", "--quiet")
        self.assertEqual(rc, 0, out)
        rc, out = H.cli("campaign", "init", "--profile", "lite", cwd=root)
        eng = Engagement(root)
        text = util.read_text(eng.case_path()).replace("## Known issues and prior audits",
                                                       "## Known issues and prior audits\n\n- Reentrancy in Vault.withdraw allows repeated withdrawals (prior audit H-2)", 1)
        util.atomic_write(eng.case_path(), text)
        H.drive(root)
        report = util.read_text(eng.path("report", "report.md"))
        self.assertIn("Possible duplicate", report)
        self.assertIn("H-2", report)


if __name__ == "__main__":
    unittest.main()
