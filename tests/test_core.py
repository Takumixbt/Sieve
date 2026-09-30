"""Core mechanics: file writes, the scope fence, the verdict rules, citations, the sanitizer."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests import harness  # noqa: F401  (puts the repo on sys.path)

from sieve import cites, judging, kb_store, util, yamlish
from sieve.fence import Fence


class AtomicWriteTests(unittest.TestCase):
    def test_lf_bytes_survive_on_every_platform(self):
        # Regression: on Windows a text-mode write turned LF into CRLF after the receipt hash was taken, so every
        # sealed proof read back as "tampered".
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "receipt.json")
            util.atomic_write(p, "a\nb\n")
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(), b"a\nb\n")

    def test_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "x.json")
            util.write_json(p, {"k": [1, 2, {"z": "y"}]})
            self.assertEqual(util.read_json(p), {"k": [1, 2, {"z": "y"}]})


class FenceTests(unittest.TestCase):
    def fence(self, **scope):
        return Fence({"scope": scope, "out_of_scope": {"hosts": ["admin.example.com"]}, "rules": {"active_testing": True}})

    def test_exact_and_wildcard_hosts(self):
        f = self.fence(hosts=["app.example.com", "*.api.example.com"])
        self.assertTrue(f.check_host("app.example.com")[0])
        self.assertTrue(f.check_host("v1.api.example.com")[0])
        self.assertFalse(f.check_host("api.example.com")[0], "a wildcard must not match its own apex")
        self.assertFalse(f.check_host("evil.com")[0])

    def test_out_of_scope_beats_in_scope(self):
        f = self.fence(hosts=["*.example.com"])
        self.assertFalse(f.check_host("admin.example.com")[0])

    def test_loopback_needs_lab(self):
        self.assertFalse(self.fence(hosts=["a.com"]).check_host("127.0.0.1")[0])
        lab = Fence({"scope": {"hosts": []}, "rules": {"lab": True}})
        self.assertTrue(lab.check_host("localhost")[0])

    def test_ip_literal_not_listed_is_blocked(self):
        self.assertFalse(self.fence(hosts=["a.com"]).check_host("8.8.8.8")[0])

    def test_url_prefix_narrows_a_listed_host(self):
        f = self.fence(hosts=["app.example.com"], urls=["https://app.example.com/v1/"])
        self.assertTrue(f.check_url("https://app.example.com/v1/users")[0])
        self.assertFalse(f.check_url("https://app.example.com/admin")[0])

    def test_dot_path_means_the_whole_tree(self):
        f = self.fence(paths=["."])
        root = os.path.abspath("proj")
        self.assertTrue(f.check_path(os.path.join(root, "src", "A.sol"), root)[0])
        self.assertFalse(f.check_path(os.path.abspath("elsewhere.sol"), root)[0])

    def test_listed_path_only(self):
        f = self.fence(paths=["src"])
        root = os.path.abspath("proj")
        self.assertTrue(f.check_path(os.path.join(root, "src", "A.sol"), root)[0])
        self.assertFalse(f.check_path(os.path.join(root, "test", "A.t.sol"), root)[0])

    def test_contract_scope(self):
        f = self.fence(contracts=[{"chain": "ethereum", "address": "0xAbC", "name": "Vault"}])
        self.assertTrue(f.check_contract("ethereum", "0xabc")[0])
        self.assertFalse(f.check_contract("base", "0xabc")[0])
        self.assertFalse(f.check_contract("ethereum", "0xdef")[0])


class VerdictTests(unittest.TestCase):
    def vote(self, verdict, who):
        return {"verifier": who, "verdict": verdict, "reason": "r"}

    def test_straightforward_finding_clears_with_one_verifier(self):
        r = judging.final({"complexity": "straightforward", "votes": [self.vote("cleared", "v1")]})
        self.assertEqual(r["verdict"], "cleared")

    def test_complex_finding_needs_two_distinct_verifiers(self):
        one = judging.final({"complexity": "complex", "votes": [self.vote("cleared", "v1")]})
        self.assertEqual(one["verdict"], "pending-quorum")
        same = judging.final({"complexity": "complex", "votes": [self.vote("cleared", "v1"), self.vote("cleared", "v1")]})
        self.assertEqual(same["verdict"], "pending-quorum", "the same verifier twice is not a quorum")
        two = judging.final({"complexity": "complex", "votes": [self.vote("cleared", "v1"), self.vote("cleared", "v2")]})
        self.assertEqual(two["verdict"], "cleared")

    def test_any_dissent_demotes_rather_than_averages(self):
        r = judging.final({"complexity": "straightforward", "votes": [self.vote("cleared", "v1"), self.vote("demoted", "v2")]})
        self.assertEqual(r["verdict"], "demoted")

    def test_unanimous_rejection_stays_rejected(self):
        r = judging.final({"complexity": "straightforward", "votes": [self.vote("rejected", "v1"), self.vote("rejected", "v2")]})
        self.assertEqual(r["verdict"], "rejected")

    def test_proof_stage_cannot_confirm_without_cleared_gates(self):
        r = judging.final({"complexity": "straightforward", "votes": [self.vote("confirmed", "v1")]})
        self.assertNotEqual(r["verdict"], "confirmed")

    def test_confirmed_needs_cleared_gates_first(self):
        r = judging.final({"complexity": "straightforward", "votes": [self.vote("cleared", "v1"), self.vote("confirmed", "v1")]})
        self.assertEqual(r["verdict"], "confirmed")


class CitationTests(unittest.TestCase):
    def test_extracts_source_shaped_citations_only(self):
        found = cites.extract("see src/Vault.sol:7 and Vault.sol:9-10 but not http://x.com:80 or tx 0xabc:12")
        self.assertEqual([(c["path"], c["start"], c["end"]) for c in found], [("src/Vault.sol", 7, 7), ("Vault.sol", 9, 10)])

    def test_quoted_snippet_is_captured(self):
        c = cites.extract("src/A.sol:3 `require(x > 0)`")[0]
        self.assertEqual(c["snippet"], "require(x > 0)")

    def test_fabricated_line_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "src"))
            with open(os.path.join(tmp, "src", "A.sol"), "w", newline="\n") as fh:
                fh.write("line1\nline2\n")
            idx = cites.FileIndex(tmp)
            ok = cites.verify_one(idx, cites.extract("src/A.sol:2")[0])
            bad = cites.verify_one(idx, cites.extract("src/A.sol:99")[0])
            missing = cites.verify_one(idx, cites.extract("src/Nope.sol:1")[0])
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])
        self.assertFalse(missing["ok"])


class SanitizerTests(unittest.TestCase):
    def test_secrets_never_reach_a_card(self):
        text = "key AKIAABCDEFGHIJKLMNOP and mail me at someone@example.com from /Users/bob/x and ghp_" + "a" * 36
        clean, kinds = kb_store.sanitize(text)
        for needle in ("AKIAABCDEFGHIJKLMNOP", "someone@example.com", "/Users/bob/", "ghp_"):
            self.assertNotIn(needle, clean)
        self.assertTrue({"aws-access-key", "email", "home-path", "github-token"} <= set(kinds))


class YamlTests(unittest.TestCase):
    def test_frontmatter_roundtrip(self):
        meta = {"id": "X-1", "tags": ["a", "b"], "n": 3, "flag": True}
        text = yamlish.join_frontmatter(meta, "# body\n")
        got, body = yamlish.split_frontmatter(text)
        self.assertEqual(got["id"], "X-1")
        self.assertEqual(got["tags"], ["a", "b"])
        self.assertIn("# body", body)


if __name__ == "__main__":
    unittest.main()
