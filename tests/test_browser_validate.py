"""The browser-recon node (fence-gated CloakBrowser) and the proof runner's refusals."""
from __future__ import annotations

import http.server
import importlib.util
import os
import threading
import unittest

from tests import harness as H

from sieve import campaign_actions as A
from sieve import frontier, util, validate
from sieve.state import Engagement

LAB_PAGE = """<!doctype html><html><head><title>Lab</title></head><body>
<a id="out" href="http://example.org/leave">leave</a>
<form action="/login" method="post"><input name="user"></form>
<script>localStorage.setItem("token","t"); fetch("/api/me");</script></body></html>"""


def engagement(case, hosts=(), urls=(), active=False, lab=False, packs=("web",)) -> Engagement:
    """A web engagement whose scope card is edited line by line (the card template already declares every key)."""
    tmp = H.tmpdir(case)
    H.isolated_env(tmp)
    root = os.path.join(tmp, "app")
    os.makedirs(root)
    H.write(os.path.join(root, "index.js"), "// app")
    rc, out = H.cli("init", root, "--pack", ",".join(packs), "--quiet")
    assert rc == 0, out
    eng = Engagement(root)
    card = util.read_text(eng.case_path())
    card = card.replace("  hosts: []", "  hosts: [" + ", ".join(hosts) + "]", 1)
    card = card.replace("  urls: []", "  urls: [" + ", ".join('"' + u + '"' for u in urls) + "]", 1)
    card = card.replace("  active_testing: false", "  active_testing: " + str(active).lower(), 1)
    card = card.replace("  lab: false", "  lab: " + str(lab).lower(), 1)
    util.atomic_write(eng.case_path(), card)
    return eng


class BrowserNodeTests(unittest.TestCase):
    def node(self):
        return {"id": "browser-recon", "spec": "browser-recon", "outputs": []}

    def test_source_only_engagement_opens_no_browser(self):
        eng = engagement(self)
        ok, msg = A.act_browser(eng, self.node(), [])
        self.assertTrue(ok, msg)
        self.assertIn("no live URL", msg)

    def test_passive_scope_never_opens_a_browser(self):
        eng = engagement(self, hosts=["app.example.com"], active=False)
        ok, msg = A.act_browser(eng, self.node(), [])
        self.assertTrue(ok, msg)
        self.assertIn("active_testing is false", msg)
        self.assertIn("none was opened", util.read_text(eng.path("xray", "browser-observations.md")))

    def test_a_missing_browser_is_coverage_debt_not_silence(self):
        eng = engagement(self, hosts=["app.example.com"], active=True)
        real = importlib.util.find_spec
        importlib.util.find_spec = lambda name, *a, **k: None if name == "cloakbrowser" else real(name, *a, **k)
        self.addCleanup(setattr, importlib.util, "find_spec", real)
        ok, msg = A.act_browser(eng, self.node(), [])
        self.assertTrue(ok, msg)
        self.assertIn("coverage debt", msg)
        self.assertIn("CloakBrowser", util.read_text(eng.path("waivers.tsv")))

    @unittest.skipUnless(importlib.util.find_spec("cloakbrowser") and os.environ.get("SIEVE_NO_BROWSER_TEST") != "1",
                         "CloakBrowser not installed (or SIEVE_NO_BROWSER_TEST=1)")
    def test_live_lab_page_is_observed_and_the_off_scope_click_is_refused(self):
        lab = H.tmpdir(self)
        H.write(os.path.join(lab, "index.html"), LAB_PAGE)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=lab, **k)

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        port = srv.server_address[1]
        eng = engagement(self, urls=[f"http://127.0.0.1:{port}/index.html"], active=True, lab=True)
        os.makedirs(eng.path("inputs"), exist_ok=True)
        util.write_json(eng.path("inputs", "browser.json"),
                        {"click": {f"http://127.0.0.1:{port}/index.html": ["a#out"]}})
        ok, msg = A.act_browser(eng, self.node(), [])
        self.assertTrue(ok, msg)
        self.assertIn("observed 1 page", msg)
        text = util.read_text(eng.path("xray", "browser-observations.md"))
        self.assertIn("/api/me", text, "the XHR the page fired must be in the observation")
        self.assertIn("localStorage keys: ['token']", text)
        self.assertIn("Navigations refused", text)
        self.assertIn("example.org/leave", text)


class ProofRunnerTests(unittest.TestCase):
    """The proof runner's refusals, run against a real finding."""

    @classmethod
    def setUpClass(cls):
        import shutil
        import tempfile
        cls.tmp = tempfile.mkdtemp(prefix="sieve-proof-")
        cls.root = H.new_engagement(cls.tmp, "lite")
        cls.eng = Engagement(cls.root)
        H.drive(cls.root)           # produces F-001, judged and proven
        cls._shutil = shutil

    @classmethod
    def tearDownClass(cls):
        import gc
        gc.collect()
        cls._shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_proof(self, **kw):
        args = dict(fid="F-001", oracle="custom-script", expect="REENTRANCY-CONFIRMED", control_cmd=None, control_waiver=None)
        args.update(kw)
        return validate.run_proof(self.eng, args.pop("fid"), args.pop("oracle"), args.pop("cmd"), args.pop("expect"),
                                  args.pop("control_cmd"), args.pop("control_waiver"), **args)

    def poc_cmd(self):
        poc = self.eng.path("proofs", "F-001", "poc.py")
        return f'"{__import__("sys").executable}" "{poc}"'.replace(chr(92), "/")

    def test_echo_only_proof_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_proof(cmd='echo "REENTRANCY-CONFIRMED"', control_waiver="no control possible for a printed line")
        self.assertIn("only prints text", str(cm.exception))

    def test_a_proof_with_no_control_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_proof(cmd=self.poc_cmd())
        self.assertIn("negative control", str(cm.exception))

    def test_destructive_verbs_are_refused(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_proof(cmd="rm -rf / && true", control_waiver="no control possible here at all")
        self.assertIn("recursive delete", str(cm.exception))

    def test_a_control_that_also_shows_the_signature_makes_the_proof_vacuous(self):
        rec = self.run_proof(cmd=self.poc_cmd(), control_cmd=self.poc_cmd())
        self.assertEqual(rec["verdict"], "fail")
        self.assertTrue(any("VACUOUS" in r for r in rec["reasons"]))

    def test_a_waived_control_can_never_reach_confirmed(self):
        rec = self.run_proof(cmd=self.poc_cmd(), control_waiver="the exploit needs no fix to be observed by a script")
        self.assertEqual(rec["verdict"], "pass-uncontrolled")

    def test_a_literal_credential_in_the_command_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_proof(cmd="curl -H 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123' x", control_waiver="no control is possible")
        self.assertIn("credential", str(cm.exception))

    def test_network_traffic_outside_the_fence_is_blocked(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_proof(cmd="curl https://evil.example.net/x", control_waiver="no control is possible here",
                           oracle="http-replay", targets=["https://evil.example.net"])
        self.assertIn("BLOCKED", str(cm.exception))


class PocShellTests(unittest.TestCase):
    def test_a_posix_shell_is_found_on_this_machine(self):
        argv = validate.shell_argv("true")
        self.assertEqual(argv[1:], ["-c", "true"])
        self.assertTrue(os.path.basename(argv[0]).startswith(("sh", "bash")))


if __name__ == "__main__":
    unittest.main()
