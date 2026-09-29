import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from tests import mockserver
from tests.helpers import BIN, ROOT, make_engagement, sieve, tmpdir

from sieve import kb_net, kb_store, yamlish
from sieve.config import Config, deep_merge, load_config


def write_user_config(uh, base, requests=3, per=2, extra_solodit=None):
    sol = {"endpoint": base + "/api/v1/solodit/findings", "rate_limit": {"requests": requests, "per_seconds": per}}
    sol.update(extra_solodit or {})
    cfg = {"kb": {"sources": {"solodit": sol,
                              "osv": {"endpoint": base + "/v1/query"}}}}
    os.makedirs(uh, exist_ok=True)
    with open(os.path.join(uh, "sieve.yaml"), "w") as fh:
        fh.write(yamlish.dumps(cfg))


class StoreTests(unittest.TestCase):
    def test_sanitizer_redacts_secrets_but_not_hashes(self):
        txt = ("key AKIAABCDEFGHIJKLMNOP and ghp_" + "a" * 36 + " mail bob@example.com "
               "tx 0x" + "ab" * 32 + " from /home/alice/project/x.sol "
               "api_key = sk_live_abcdefghijklmnop1234 host 10.1.2.3 "
               "-----BEGIN RSA PRIVATE KEY-----\nMIIB\n-----END RSA PRIVATE KEY-----")
        clean, kinds = kb_store.sanitize(txt)
        for bad in ("AKIAABCDEFGHIJKLMNOP", "ghp_" + "a" * 36, "bob@example.com", "/home/alice/", "10.1.2.3", "MIIB"):
            self.assertNotIn(bad, clean)
        self.assertIn("0x" + "ab" * 32, clean)  # a bare tx hash is not a secret
        self.assertTrue({"aws-access-key", "github-token", "email", "home-path", "private-ip",
                         "private-key-block"} <= set(kinds))
        wallet, k2 = kb_store.sanitize("private key: 0x" + "cd" * 32)
        self.assertIn("wallet-secret", k2)

    def test_card_merge_never_downgrades_status_and_unions_used_in(self):
        with tmpdir() as vault:
            meta = {"title": "Spot oracle", "source": "solodit", "source_ref": "u1", "domain": "web3",
                    "class": "oracle-manipulation", "status": "confirmed", "used_in": ["E1:F-1"]}
            p1, a1 = kb_store.write_card(vault, meta, "# body one")
            self.assertEqual(a1, "created")
            meta2 = dict(meta, status="raw", used_in=["E2:F-9"])
            p2, a2 = kb_store.write_card(vault, meta2, "# body two")
            self.assertEqual(p1, p2)
            self.assertEqual(a2, "updated")
            m, body = kb_store.read_card(p1)
            self.assertEqual(m["status"], "confirmed")
            self.assertEqual(m["used_in"], ["E1:F-1", "E2:F-9"])
            p3, a3 = kb_store.write_card(vault, meta2, "# body two")
            self.assertEqual(a3, "unchanged")

    def test_write_card_redacts_and_counts(self):
        with tmpdir() as vault:
            p, _ = kb_store.write_card(vault, {"title": "t", "source": "own", "source_ref": "r", "domain": "web",
                                               "class": "ssrf"}, "creds AKIAABCDEFGHIJKLMNOP here")
            m, body = kb_store.read_card(p)
            self.assertNotIn("AKIA", body)
            self.assertEqual(m["redactions"], 1)

    def test_index_search_ranking_and_filters(self):
        with tmpdir() as d:
            vault = os.path.join(d, "kb")
            for title, dom, klass, status, text in [
                ("Spot price oracle manipulation", "web3", "oracle-manipulation", "confirmed", "getReserves flash loan price"),
                ("Reentrancy via ERC777 hooks", "web3", "reentrancy", "curated", "tokensReceived hook reenter"),
                ("SSRF via webhook URL", "web", "ssrf", "curated", "internal metadata endpoint webhook"),
            ]:
                kb_store.write_card(vault, {"title": title, "source": "own", "source_ref": title, "domain": dom,
                                            "class": klass, "status": status}, text)
            ix = kb_store.Index(os.path.join(d, "i.db"))
            self.assertEqual(ix.reindex([vault]), 3)
            hits = ix.search("flash loan price oracle")
            self.assertEqual(hits[0]["class"], "oracle-manipulation")
            self.assertEqual([h["class"] for h in ix.search("webhook", domain="web")], ["ssrf"])
            self.assertEqual(ix.search("webhook", domain="web3"), [])
            self.assertEqual(ix.search("the a of"), [])  # stop words only
            self.assertEqual(ix.stats()["by_status"]["confirmed"], 1)


class BrokerTests(unittest.TestCase):
    def _setup(self, base, requests=3, per=2, **kw):
        d = tempfile.mkdtemp(prefix="sieve-kb-")
        uh = os.path.join(d, "uh")
        write_user_config(uh, base, requests, per, **kw)
        env = {"SIEVE_USER_HOME": uh, "CYFRIN_API_KEY": "test-key"}
        return d, uh, env

    def _cfg_ix(self, uh):
        os.environ["SIEVE_USER_HOME"] = uh
        cfg = load_config()
        return cfg, kb_store.Index(os.path.join(uh, "index.db"))

    def test_solodit_search_normalises_and_caches(self):
        with mockserver.run_mock() as (base, st):
            d, uh, env = self._setup(base)
            os.environ["CYFRIN_API_KEY"] = "test-key"
            cfg, ix = self._cfg_ix(uh)
            b = kb_net.Broker(ix)
            h1 = kb_net.solodit_search(b, cfg, "price manipulation", impact=["high"])
            h2 = kb_net.solodit_search(b, cfg, "price manipulation", impact=["high"])
            self.assertEqual(len(st["requests"]), 1, "second identical query must come from cache")
            self.assertEqual(h1, h2)
            self.assertEqual(h1[0]["severity"], "high")
            self.assertEqual(h1[0]["firm"], "Sherlock")
            self.assertEqual(h1[0]["tags"], ["Oracle", "Flash Loan"])
            self.assertTrue(h1[0]["url"].startswith("https://solodit.cyfrin.io/issues/"))
            self.assertEqual(st["requests"][0]["body"]["filters"]["impact"], ["HIGH"])

    def test_request_shape_fallback_is_learned(self):
        with mockserver.run_mock(mode="flat") as (base, st):
            d, uh, env = self._setup(base)
            os.environ["CYFRIN_API_KEY"] = "test-key"
            cfg, ix = self._cfg_ix(uh)
            b = kb_net.Broker(ix)
            kb_net.solodit_search(b, cfg, "alpha")
            self.assertEqual(len(st["requests"]), 2)  # nested rejected with 400, flat accepted
            kb_net.solodit_search(b, cfg, "beta")
            self.assertEqual(len(st["requests"]), 3)  # learned: goes straight to flat

    def test_missing_and_wrong_key(self):
        with mockserver.run_mock() as (base, st):
            d, uh, env = self._setup(base)
            cfg, ix = self._cfg_ix(uh)
            os.environ.pop("CYFRIN_API_KEY", None)
            with self.assertRaises(kb_net.AuthError) as cm:
                kb_net.solodit_search(kb_net.Broker(ix), cfg, "x")
            self.assertIn("CYFRIN_API_KEY", str(cm.exception))
            os.environ["CYFRIN_API_KEY"] = "wrong"
            with self.assertRaises(kb_net.AuthError):
                kb_net.solodit_search(kb_net.Broker(ix), cfg, "y")
            os.environ["CYFRIN_API_KEY"] = "test-key"

    def test_429_backs_off_and_retries(self):
        with mockserver.run_mock(fail_429=1, retry_after=1) as (base, st):
            d, uh, env = self._setup(base, requests=5, per=1)
            os.environ["CYFRIN_API_KEY"] = "test-key"
            cfg, ix = self._cfg_ix(uh)
            t0 = time.time()
            hits = kb_net.solodit_search(kb_net.Broker(ix), cfg, "retry me")
            self.assertEqual(len(hits), 1)
            self.assertGreaterEqual(time.time() - t0, 0.9)
            self.assertEqual(len(st["requests"]), 2)

    def test_sliding_window_holds_across_processes(self):
        limit, per = 3, 2
        with mockserver.run_mock() as (base, st):
            d, uh, env = self._setup(base, requests=limit, per=per)
            e = dict(os.environ, SIEVE_HOME=ROOT, **env)
            procs = []
            for i in range(4):  # four "agents", three distinct queries each -> 12 requests
                script = ("from sieve import kb_net,kb_store\nfrom sieve.config import load_config\n"
                          "import os\ncfg=load_config()\nix=kb_store.Index(os.path.join(os.environ['SIEVE_USER_HOME'],'index.db'))\n"
                          "b=kb_net.Broker(ix)\n"
                          f"for j in range(3): kb_net.solodit_search(b,cfg,'agent{i} query{{}}'.format(j))\n")
                procs.append(subprocess.Popen([sys.executable, "-c", script], env=e, cwd=ROOT,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            for p in procs:
                out, err = p.communicate(timeout=120)
                self.assertEqual(p.returncode, 0, err)
            ts = sorted(r["t"] for r in st["requests"])
            self.assertEqual(len(ts), 12)
            # in EVERY window of `per` seconds the server saw at most `limit` requests
            for i, t in enumerate(ts):
                in_window = [x for x in ts if t <= x < t + per - 0.05]
                self.assertLessEqual(len(in_window), limit, f"window starting {t}: {len(in_window)} requests")
            self.assertGreaterEqual(ts[-1] - ts[0], per * 2 - 0.5, "12 requests at 3/2s cannot finish faster than ~8s")

    def test_rate_limited_error_when_wait_exceeds_budget(self):
        with mockserver.run_mock() as (base, st):
            d, uh, env = self._setup(base, requests=1, per=30)
            os.environ["CYFRIN_API_KEY"] = "test-key"
            cfg, ix = self._cfg_ix(uh)
            b = kb_net.Broker(ix)
            kb_net.solodit_search(b, cfg, "one")
            t0 = time.time()
            with self.assertRaises(kb_net.RateLimited):
                b.call("solodit", cfg.source("solodit"), "k2", 1, lambda: (200, {}, {}), max_wait=1.0)
            self.assertLess(time.time() - t0, 3)

    def test_offline_mode_never_touches_network(self):
        with mockserver.run_mock() as (base, st):
            d, uh, env = self._setup(base)
            os.environ["CYFRIN_API_KEY"] = "test-key"
            cfg, ix = self._cfg_ix(uh)
            with self.assertRaises(kb_net.KBError):
                kb_net.solodit_search(kb_net.Broker(ix, offline=True), cfg, "x")
            self.assertEqual(st["requests"], [])

    def test_osv_query(self):
        with mockserver.run_mock() as (base, st):
            d, uh, env = self._setup(base)
            cfg, ix = self._cfg_ix(uh)
            hits = kb_net.osv_query(kb_net.Broker(ix), cfg, "lodash", "npm", "4.17.11")
            self.assertEqual(hits[0]["title"], "Prototype pollution in lodash")
            self.assertEqual(hits[0]["severity"], "high")
            self.assertIn("CVE-2019-10744", hits[0]["tags"])
            self.assertEqual(st["requests"][0]["body"]["package"], {"name": "lodash", "ecosystem": "npm"})


class KbCliTests(unittest.TestCase):
    def test_use_add_writeback_flow(self):
        with mockserver.run_mock() as (base, st), tmpdir() as d:
            uh = os.path.join(d, "uh")
            write_user_config(uh, base)
            env = {"SIEVE_USER_HOME": uh, "CYFRIN_API_KEY": "test-key"}
            proj = os.path.join(d, "proj")
            os.makedirs(proj)
            eng = make_engagement(proj)
            r = sieve("kb", "search", "price manipulation", "--online", "--domain", "web3", cwd=proj, env=env, check=True)
            self.assertIn("Oracle price manipulation", r.stdout)
            import re
            ref = re.search(r"ref: (solodit:\S+)", r.stdout).group(1)  # copy the ref exactly as printed
            r = sieve("kb", "use", ref, "--finding", "F-001", "--class", "oracle-manipulation", cwd=proj, env=env, check=True)
            self.assertIn("created curated card", r.stdout)
            cards = [os.path.join(b, f) for b, _, fs in os.walk(os.path.join(uh, "kb")) for f in fs]
            self.assertEqual(len(cards), 1)
            meta, body = kb_store.read_card(cards[0])
            self.assertEqual(meta["status"], "curated")
            self.assertTrue(meta["used_in"][0].endswith(":F-001"))
            self.assertNotIn("AKIA", body)
            self.assertNotIn("bob@example.com", body)
            # curated card is found offline afterwards
            r = sieve("kb", "search", "price manipulation", "--offline", cwd=proj, env=env, check=True)
            self.assertIn("local/curated", r.stdout)
            # add a web precedent by hand
            r = sieve("kb", "add", "--title", "SSRF in PDF renderer", "--domain", "web", "--class", "ssrf",
                      "--url", "https://example.org/report/1", "--body", "renderer fetched http://169.254.169.254/",
                      "--used-in", "F-002", cwd=proj, env=env, check=True)
            self.assertIn("created", r.stdout)
            # write back a confirmed finding
            fdir = os.path.join(eng.dir, "findings")
            with open(os.path.join(fdir, "F-001.md"), "w") as fh:
                fh.write(yamlish.join_frontmatter(
                    {"id": "F-001", "title": "Vault reads spot price", "pack": "web3", "class": "oracle-manipulation",
                     "vector": "W3-ORC-01", "severity": "high", "kind": "FINDING", "status": "confirmed",
                     "confidence": 90, "stack": "solidity", "tell": "getReserves\\("},
                    "## Root cause\nprice = reserve1/reserve0\n\n## Attack path\n1. flash loan\n\n## Remediation\nuse TWAP\n"))
            with open(os.path.join(fdir, "F-002.md"), "w") as fh:
                fh.write(yamlish.join_frontmatter({"id": "F-002", "title": "weak", "pack": "web3", "kind": "FINDING",
                                                   "status": "confirmed", "confidence": 60}, "## Root cause\nx\n"))
            r = sieve("kb", "writeback", cwd=proj, env=env, check=True)
            self.assertIn("1 confirmed card(s) written", r.stdout)
            self.assertIn("skip F-002", r.stdout)
            r = sieve("kb", "search", "spot price reserve", "--offline", cwd=proj, env=env, check=True)
            self.assertIn("local/confirmed", r.stdout)

    def test_search_reports_missing_key_without_crashing(self):
        with tmpdir() as d:
            uh = os.path.join(d, "uh")
            os.makedirs(uh)
            r = sieve("kb", "search", "reentrancy", "--online", "--domain", "web3", cwd=d,
                      env={"SIEVE_USER_HOME": uh, "CYFRIN_API_KEY": ""})
            self.assertEqual(r.returncode, 0)
            self.assertIn("CYFRIN_API_KEY", r.stdout)


if __name__ == "__main__":
    unittest.main()
