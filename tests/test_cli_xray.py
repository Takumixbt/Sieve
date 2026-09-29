import json
import os
import shutil
import unittest

from tests.helpers import ROOT, make_engagement, sieve, tmpdir  # noqa: F401

FIX_WEB3 = os.path.join(ROOT, "tests", "fixtures", "web3")
FIX_WEB = os.path.join(ROOT, "tests", "fixtures", "web")


class CliXrayTests(unittest.TestCase):
    def test_xray_web3_writes_facts_and_reports_tool_leads(self):
        with tmpdir() as d:
            proj = os.path.join(d, "proj")
            shutil.copytree(FIX_WEB3, proj)
            eng = make_engagement(proj, packs=("web3",))
            r = sieve("xray", "web3", "--slither", os.path.join(proj, "slither.json"),
                     "--aderyn", os.path.join(proj, "aderyn.json"), cwd=proj, check=True)
            self.assertIn("entry-point candidate", r.stdout)
            self.assertIn("tool lead", r.stdout)
            facts = json.load(open(eng.path("xray", "facts.json")))
            self.assertGreater(len(facts["web3"]["entry_candidates"]), 0)
            self.assertEqual(len(facts["web3"]["tool_leads"]), 3)

    def test_xray_web_merges_and_writes_surface_tsv(self):
        with tmpdir() as d:
            eng = make_engagement(d, packs=("web",))
            r = sieve("xray", "web", "--openapi", os.path.join(FIX_WEB, "openapi.json"),
                     "--har", os.path.join(FIX_WEB, "sample.har"), cwd=d, check=True)
            self.assertIn("endpoint(s) merged", r.stdout)
            self.assertTrue(os.path.isfile(eng.path("xray", "surface.tsv")))
            from sieve import util
            header, rows = util.read_tsv(eng.path("xray", "surface.tsv"))
            self.assertEqual(header, ["method", "path", "auth", "sources", "where"])
            self.assertGreater(len(rows), 0)

    def test_xray_git(self):
        with tmpdir() as d:
            import subprocess
            subprocess.run(["git", "init", "-q"], cwd=d, check=True)
            with open(os.path.join(d, "a.sol"), "w") as fh:
                fh.write("contract A {}\n")
            subprocess.run(["git", "add", "-A"], cwd=d, check=True)
            subprocess.run(["git", "-c", "user.email=a@e.com", "-c", "user.name=A", "commit", "-qm", "init"],
                          cwd=d, check=True)
            eng = make_engagement(d, packs=("web3",))
            r = sieve("xray", "git", cwd=d, check=True)
            self.assertIn("repo shape", r.stdout)
            self.assertTrue(os.path.isfile(eng.path("xray", "git-security.json")))

    def test_map_requires_architecture_json_first(self):
        with tmpdir() as d:
            make_engagement(d)
            r = sieve("xray", "map", cwd=d)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("architecture.json", r.stderr)

    def test_map_renders_svg(self):
        with tmpdir() as d:
            eng = make_engagement(d)
            os.makedirs(eng.path("xray"), exist_ok=True)
            arch = {"title": "Test", "nodes": [{"id": "u", "label": "User", "type": "actor"},
                                               {"id": "v", "label": "Vault", "type": "protocol"}],
                   "edges": [{"from": "u", "to": "v", "label": "deposit"}]}
            with open(eng.path("xray", "architecture.json"), "w") as fh:
                json.dump(arch, fh)
            r = sieve("xray", "map", cwd=d, check=True)
            self.assertIn("architecture.svg", r.stdout)
            svg = open(eng.path("xray", "architecture.svg")).read()
            self.assertIn("<svg", svg)
            self.assertIn("Vault", svg)


if __name__ == "__main__":
    unittest.main()
