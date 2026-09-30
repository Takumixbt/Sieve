"""The knowledge base: precedent tier, ingest parsers (network faked), search across both tiers, promotion."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import zipfile

from tests import harness as H

from sieve import kb_ingest, kb_store

DEFIHACKLABS_2024 = """# DeFi Hacks Reproduce - Foundry

## 2024 - List of Past DeFi Incidents

### 20241227 Bizness - Reentrancy

### Lost: 15.7k USD

```sh
forge test --contracts ./src/test/2024-12/Bizness_exp.sol -vvv
```
#### Contract
[Bizness_exp.sol](../../src/test/2024-12/Bizness_exp.sol)
### Link reference

https://x.com/TenArmorAlert/status/1872857132363645205

---

### 20241223 Moonhacker - improper input validation

### Lost:  318.9 k

#### Contract
[Moonhacker_exp.sol](../../src/test/2024-12/Moonhacker_exp.sol)
### Link reference

https://x.com/example/status/1
"""

H1_CSV = """program,title,link,upvotes,bounty,vuln_type
Visma Public,[IDOR]Ability to pause and resume the invoice of other users,hackerone.com/reports/1,5,250.0,Insecure Direct Object Reference (IDOR)
curl,Heap-buffer-overflow read in curl_formadd,hackerone.com/reports/2,9,0.0,Out-of-bounds Read
"""

KEV = json.dumps({"vulnerabilities": [{
    "cveID": "CVE-2026-0001", "vendorProject": "Acme", "product": "Gateway", "vulnerabilityName": "Acme Gateway SQL Injection",
    "shortDescription": "Acme Gateway contains a SQL injection that permits remote code execution.", "dateAdded": "2026-09-01",
    "knownRansomwareCampaignUse": "Known", "cwes": ["CWE-89"]}]})


def osv_zip() -> bytes:
    rec = {"id": "OSV-2024-1", "summary": "Heap-buffer-overflow in parse_len", "details": "OSS-Fuzz report",
           "aliases": ["CVE-2024-1"], "published": "2024-05-05T00:00:00Z",
           "references": [{"type": "FIX", "url": "https://github.com/acme/lib/commit/abc1234def"}],
           "affected": [{"package": {"name": "acme-lib", "ecosystem": "OSS-Fuzz"},
                         "ranges": [{"type": "GIT", "repo": "https://github.com/acme/lib", "events": [{"introduced": "0"}, {"fixed": "abc1234def"}]}]}]}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("OSV-2024-1.json", json.dumps(rec))
        zf.writestr("readme.txt", "not json")
    return buf.getvalue()


class FakeNet:
    """Replaces kb_ingest's transport so parsers are tested against known bytes."""

    def __init__(self):
        self.calls = []

    def text(self, url, **kw):
        self.calls.append(url)
        if "/past/2024/README.md" in url:
            return DEFIHACKLABS_2024
        if "/past/" in url:
            raise kb_ingest.IngestError("HTTP 404 for " + url)
        if url.endswith("data.csv"):
            return H1_CSV
        if "known_exploited" in url:
            return KEV
        raise kb_ingest.IngestError("unexpected url " + url)

    def raw(self, url, **kw):
        self.calls.append(url)
        if "OSS-Fuzz/all.zip" in url:
            return osv_zip()
        raise kb_ingest.IngestError("unexpected url " + url)


class IngestParserTests(unittest.TestCase):
    def setUp(self):
        self.net = FakeNet()
        self._t, self._g = kb_ingest.http_text, kb_ingest.http_get
        kb_ingest.http_text, kb_ingest.http_get = self.net.text, self.net.raw

    def tearDown(self):
        kb_ingest.http_text, kb_ingest.http_get = self._t, self._g

    def rows(self, fn, **opts):
        return list(fn(opts, lambda *_: None))

    def test_defihacklabs_incidents(self):
        rows = self.rows(kb_ingest.src_defihacklabs)
        self.assertEqual(len(rows), 2)
        biz = next(r for r in rows if "Bizness" in r["title"])
        self.assertEqual(biz["class"], "reentrancy")
        self.assertEqual(biz["domain"], "web3")
        self.assertIn("15.7k", biz["body"])
        self.assertTrue(biz["url"].startswith("https://x.com/"))

    def test_hackerone_domain_and_class(self):
        rows = self.rows(kb_ingest.src_hackerone)
        idor = next(r for r in rows if "invoice" in r["title"])
        self.assertEqual((idor["class"], idor["domain"]), ("idor", "web"))
        curl = next(r for r in rows if "curl" in r["title"])
        self.assertEqual(curl["domain"], "binary", "a memory-safety report belongs to the binary pack")
        self.assertEqual(curl["url"], "https://hackerone.com/reports/2")

    def test_kev(self):
        row = self.rows(kb_ingest.src_cisa_kev)[0]
        self.assertEqual(row["class"], "sql-injection")
        self.assertIn("CVE-2026-0001", row["title"])
        self.assertEqual(row["severity"], "critical")

    def test_osv_keeps_the_fix_commit(self):
        row = self.rows(kb_ingest.src_osv, osv_ecosystem="OSS-Fuzz")[0]
        self.assertEqual(row["domain"], "binary")
        self.assertEqual(row["class"], "memory-corruption")
        self.assertIn("abc1234def", row["fix"])


class PrecedentTierTests(unittest.TestCase):
    def setUp(self):
        self.ix = kb_store.Index(os.path.join(H.tmpdir(self), "index.db"))
        self.addCleanup(self.ix.close)

    def rows(self, n=3):
        return [kb_ingest._row("test", "web3", f"Vault price manipulation {i}", f"https://x/{i}", "oracle spot price flash loan drain",
                               klass="oracle-manipulation", fix="https://github.com/a/b/commit/abc1234") for i in range(n)]

    def test_replace_is_idempotent_and_scoped_to_a_source(self):
        self.assertEqual(self.ix.replace_precedents("test", self.rows(3)), 3)
        self.assertEqual(self.ix.replace_precedents("test", self.rows(2)), 2)
        other = [kb_ingest._row("other", "web", "IDOR in invoices", "https://y/1", "user reads another user's invoice", klass="idor")]
        self.ix.replace_precedents("other", other)
        self.assertEqual(self.ix.stats()["precedents_by_source"], {"test": 2, "other": 1})

    def test_search_returns_precedents_with_their_fix(self):
        self.ix.replace_precedents("test", self.rows(2))
        hits = self.ix.search("oracle spot price manipulation", domain="web3")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["status"], "precedent")
        self.assertIn("abc1234", hits[0]["body"])

    def test_domain_filter_separates_packs(self):
        self.ix.replace_precedents("test", self.rows(2))
        self.assertEqual(self.ix.search("oracle price", domain="web"), [])

    def test_get_resolves_a_precedent_like_a_card(self):
        self.ix.replace_precedents("test", self.rows(1))
        pid = self.ix.search("oracle")[0]["id"]
        card = self.ix.get(pid)
        self.assertEqual(card["source"], "test")
        self.assertEqual(card["status"], "precedent")

    def test_reindexing_the_vault_does_not_drop_precedents(self):
        self.ix.replace_precedents("test", self.rows(2))
        self.ix.reindex([], extra=[])
        self.assertEqual(self.ix.stats()["precedents"], 2)

    def test_curated_cards_outrank_precedents(self):
        self.ix.replace_precedents("test", self.rows(2))
        meta = {"id": "KB-W3-1", "title": "Vault price manipulation confirmed", "domain": "web3", "class": "oracle-manipulation",
                "status": "confirmed", "source": "own", "tags": ["oracle"]}
        self.ix.upsert(meta, "oracle spot price flash loan drain", "")
        self.assertEqual(self.ix.search("oracle spot price manipulation", domain="web3")[0]["status"], "confirmed")


class ClassifierTests(unittest.TestCase):
    def test_known_shapes(self):
        cases = {"Read-only Reentrancy": "reentrancy", "Oracle Price Manipulation": "oracle-manipulation",
                 "Blind SQL injection in login": "sql-injection", "Stored XSS in comments": "xss",
                 "heap-buffer-overflow in decoder": "memory-corruption", "Server-side request forgery": "ssrf",
                 "something entirely unrelated": "other"}
        for text, want in cases.items():
            self.assertEqual(kb_ingest.classify(text), want, text)


class IngestRunTests(unittest.TestCase):
    def test_fresh_sources_are_skipped_and_failures_do_not_wipe_data(self):
        if True:
            ix = kb_store.Index(os.path.join(H.tmpdir(self), "i.db"))
            self.addCleanup(ix.close)
            net = FakeNet()
            t, g = kb_ingest.http_text, kb_ingest.http_get
            kb_ingest.http_text, kb_ingest.http_get = net.text, net.raw
            try:
                first = kb_ingest.ingest(ix, ["hackerone"], {}, lambda *_: None)
                self.assertEqual(first["hackerone"]["rows"], 2)
                again = kb_ingest.ingest(ix, ["hackerone"], {}, lambda *_: None)
                self.assertIn("skipped", again["hackerone"])
                kb_ingest.http_text = lambda url, **kw: (_ for _ in ()).throw(kb_ingest.IngestError("HTTP 503"))
                broken = kb_ingest.ingest(ix, ["hackerone"], {}, lambda *_: None, refresh=True)
                self.assertIn("error", broken["hackerone"])
                self.assertEqual(ix.stats()["precedents_by_source"], {"hackerone": 2}, "a failed refresh must keep the old rows")
            finally:
                kb_ingest.http_text, kb_ingest.http_get = t, g

    def test_offline_mode_refuses_the_network(self):
        os.environ["SIEVE_OFFLINE"] = "1"
        self.addCleanup(os.environ.pop, "SIEVE_OFFLINE", None)
        with self.assertRaises(kb_ingest.IngestError):
            kb_ingest.http_get("https://example.com/")


class CliTests(unittest.TestCase):
    def test_sources_and_stats_commands_run_without_a_key(self):
        if True:
            H.isolated_env(H.tmpdir(self))
            rc, out = H.cli("kb", "sources")
            self.assertEqual(rc, 0, out)
            self.assertIn("defihacklabs", out)
            self.assertIn("hackerone", out)
            rc, out = H.cli("kb", "search", "reentrancy", "--offline")
            self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
