"""End to end: scan, campaign, gates, an executed proof with a negative control, report, write-back, vault.

Simulated agents write the artifacts; everything else is the real engine. The lean profile runs by default. The
full profile (71 nodes, all eight lenses, fuzz, independence audit) runs unless SIEVE_FAST_TESTS=1.
"""
from __future__ import annotations

import gc
import glob
import json
import os
import shutil
import tempfile
import unittest

from tests import harness as H

from sieve import frontier, validate, vault
from sieve.state import Engagement


class _Base(unittest.TestCase):
    profile = "lite"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sieve-e2e-")
        cls.root = H.new_engagement(cls.tmp, cls.profile)
        cls.eng = Engagement(cls.root)
        cls.log = []
        cls.result = H.drive(cls.root, log=cls.log)

    @classmethod
    def tearDownClass(cls):
        gc.collect()
        shutil.rmtree(cls.tmp, ignore_errors=True)


class LiteCampaignTests(_Base):
    def test_every_node_finished(self):
        self.assertTrue(all(v in ("done", "skipped") for v in self.result["status"].values()))

    def test_the_finding_is_confirmed_by_a_machine_not_by_a_label(self):
        tier = validate.assess(self.eng, "F-001")
        self.assertEqual(tier["tier"], "confirmed", tier)

    def test_the_proof_ran_repeatedly_and_the_negative_control_stayed_silent(self):
        execs = [r for r in validate.receipts(self.eng, "F-001") if r.get("kind") == "exec"]
        self.assertEqual(len(execs), 1)
        r = execs[0]
        self.assertEqual(r["verdict"], "pass")
        self.assertGreaterEqual(r["repeat"], 3)
        self.assertTrue(all(run["matched"] for run in r["runs"]))
        self.assertIn("patched-target", r["control"]["kinds"])
        self.assertFalse(any(run["matched"] for run in r["control"]["patch"]["runs"]), "the fix must silence the exploit")

    def test_report_prints_the_computed_tier(self):
        text = H.read(self.eng.path("report", "report.md"))
        self.assertIn("F-001", text)
        self.assertRegex(text, r"(?i)confirmed")
        self.assertIn("reentrancy", text.lower())

    def test_the_ledger_is_intact_and_editing_a_receipt_is_detected(self):
        self.assertEqual(validate.ledger_problems(self.eng), [])
        receipt = glob.glob(self.eng.path("proofs", "F-001--exec-*.json"))[0]
        with open(receipt, "rb") as fh:
            original = fh.read()
        try:
            with open(receipt, "wb") as fh:
                fh.write(original.replace(b'"pass"', b'"fail"'))
            self.assertTrue(any("modified after it was written" in p for p in validate.ledger_problems(self.eng)))
        finally:
            with open(receipt, "wb") as fh:
                fh.write(original)
        self.assertEqual(validate.ledger_problems(self.eng), [])

    def test_a_hand_written_receipt_is_detected(self):
        fake = self.eng.path("proofs", "F-001--exec-forged.json")
        with open(fake, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"kind": "exec", "verdict": "pass"}, fh)
        try:
            self.assertTrue(any("not in the ledger" in p for p in validate.ledger_problems(self.eng)))
        finally:
            os.remove(fake)

    def test_the_frontier_drained_with_receipts(self):
        self.assertEqual(frontier.stats(self.eng)["open"], 0)

    def test_write_back_made_a_confirmed_card_and_dead_end_lessons(self):
        from sieve.config import load_config
        kb = load_config(self.root).path("kb.vault")
        cards = glob.glob(os.path.join(kb, "**", "*.md"), recursive=True)
        text = "\n".join(H.read(c) for c in cards)
        self.assertIn("status: confirmed", text)
        self.assertIn("kind:** dead-end", text)

    def test_the_lean_profile_skipped_the_lens_fan_out(self):
        self.assertFalse(any("lens" in nid for nid in self.result["status"]))


class VaultTests(_Base):
    def test_export_writes_one_namespaced_graph_into_the_shared_vault(self):
        rc, out = H.cli("vault", "init", cwd=self.root)
        self.assertEqual(rc, 0, out)
        rc, out = H.cli("vault", "export", cwd=self.root)
        self.assertEqual(rc, 0, out)
        from sieve.config import load_config
        root = vault.vault_root(load_config(self.root))
        ns = vault.namespace(self.eng)
        folder = os.path.join(root, "Engagements", ns)
        self.assertTrue(os.path.isfile(os.path.join(folder, "findings", f"{ns}-F-001.md")))
        self.assertTrue(os.path.isfile(os.path.join(folder, f"{self.eng.load()['id']}.md")))
        self.assertTrue(os.path.isfile(os.path.join(folder, f"{ns}-Report.md")))
        self.assertFalse(os.path.exists(os.path.join(folder, ".obsidian")), "one .obsidian config, at the vault root")
        self.assertTrue(os.path.isdir(os.path.join(root, ".obsidian")))
        front = H.read(os.path.join(root, "Sieve.md"))
        self.assertIn(self.eng.load()["id"], front)

    def test_finding_note_links_its_class_hub_and_carries_the_confirmed_tag(self):
        H.cli("vault", "export", cwd=self.root)
        from sieve.config import load_config
        root = vault.vault_root(load_config(self.root))
        ns = vault.namespace(self.eng)
        note = H.read(os.path.join(root, "Engagements", ns, "findings", f"{ns}-F-001.md"))
        self.assertIn("[[class-reentrancy|reentrancy]]", note)
        self.assertRegex(note, r"tags:.*confirmed")
        self.assertTrue(os.path.isfile(os.path.join(root, "KB", "_hubs", "class-reentrancy.md")))

    def test_invariants_carry_a_coverage_state(self):
        H.cli("vault", "export", cwd=self.root)
        from sieve.config import load_config
        root = vault.vault_root(load_config(self.root))
        ns = vault.namespace(self.eng)
        inv = H.read(os.path.join(root, "Engagements", ns, "invariants", f"{ns}-INV-1.md"))
        self.assertRegex(inv, r"coverage: (broken|clean|dead-end|unprobed)")

    def test_reexport_is_idempotent(self):
        H.cli("vault", "export", cwd=self.root)
        rc, out = H.cli("vault", "export", cwd=self.root)
        self.assertEqual(rc, 0, out)
        from sieve.config import load_config
        root = vault.vault_root(load_config(self.root))
        front = H.read(os.path.join(root, "Sieve.md"))
        self.assertEqual(front.count(self.eng.load()["id"]), 1, "an engagement is listed once however often it is exported")

    def test_note_names_never_collide_across_engagements(self):
        first = vault.namespace(self.eng)
        tmp2 = tempfile.mkdtemp(prefix="sieve-e2e2-")
        self.addCleanup(lambda: (gc.collect(), shutil.rmtree(tmp2, ignore_errors=True)))
        os.environ["SIEVE_VAULT"] = os.path.join(self.tmp, "vault")   # keep the shared vault
        root2 = H.make_target(tmp2)
        H.cli("scan", root2, "--offline", "--quiet")
        second = vault.namespace(Engagement(root2))
        self.assertNotEqual(first, second, "two engagements of the same target still get distinct namespaces")


@unittest.skipIf(os.environ.get("SIEVE_FAST_TESTS") == "1", "SIEVE_FAST_TESTS=1")
class DefaultCampaignTests(_Base):
    profile = "default"

    def test_every_node_finished(self):
        self.assertGreater(self.result["nodes"], 60)
        self.assertTrue(all(v in ("done", "skipped") for v in self.result["status"].values()))

    def test_all_eight_lenses_ran(self):
        self.assertEqual(sum(1 for nid in self.result["status"] if nid.startswith("lens-")), 8)

    def test_the_fuzz_result_became_frontier_work_that_was_closed_with_a_receipt(self):
        st = json.loads(H.read(self.eng.path("campaign", "state.json")))
        self.assertIn("broken", st["nodes"]["fuzz-absorb"]["note"])
        rows = [r for r in frontier.load(self.eng) if r["kind"] == "fuzz-break"]
        self.assertTrue(rows)
        self.assertTrue(all(r["status"] in ("done", "dead") for r in rows))

    def test_the_independence_audit_ran_and_the_finding_is_still_confirmed(self):
        self.assertEqual(self.result["status"]["independence-audit"], "done")
        self.assertEqual(validate.assess(self.eng, "F-001")["tier"], "confirmed")


if __name__ == "__main__":
    unittest.main()
