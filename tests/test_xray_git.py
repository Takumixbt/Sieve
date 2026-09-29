import os
import subprocess
import unittest

from tests.helpers import tmpdir  # noqa: F401

from sieve import xray_git


def git(d, *args, date=None, author="Alice <alice@example.com>"):
    env = dict(os.environ, GIT_AUTHOR_NAME=author.split(" <")[0], GIT_AUTHOR_EMAIL="a@e.com",
               GIT_COMMITTER_NAME=author.split(" <")[0], GIT_COMMITTER_EMAIL="a@e.com")
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", d, *args], env=env, check=True, capture_output=True)


def write(d, rel, text):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        fh.write(text)


class GitSecurityTests(unittest.TestCase):
    def test_no_git(self):
        with tmpdir() as d:
            self.assertEqual(xray_git.analyze(d)["repo_shape"]["shape"], "no_git")

    def test_squashed_import(self):
        with tmpdir() as d:
            git(d, "init", "-q")
            write(d, "src/A.sol", "contract A {}\n")
            git(d, "add", "-A")
            git(d, "commit", "-qm", "import", date="2026-01-01T00:00:00")
            r = xray_git.analyze(d)
            self.assertEqual(r["repo_shape"]["shape"], "squashed_import")

    def test_history_signals(self):
        with tmpdir() as d:
            git(d, "init", "-q")
            git(d, "config", "commit.gpgsign", "false")
            write(d, "src/Vault.sol", "contract Vault {\n function w(uint a) external { bal -= a; }\n}\n")
            write(d, "test/Vault.t.sol", "contract T {}\n")
            write(d, "lib/openzeppelin-contracts/ERC20.sol", "contract ERC20 {}\n")
            git(d, "add", "-A")
            git(d, "commit", "-qm", "initial vault", date="2026-01-01T10:00:00")
            write(d, "src/Vault.sol",
                  "contract Vault {\n function w(uint a) external {\n  require(bal >= a);\n  bal -= a;\n }\n}\n")
            git(d, "add", "-A")
            git(d, "commit", "-qm", "fix: underflow in withdraw, add require check", date="2026-01-05T10:00:00", author="Bob <b@e.com>")
            write(d, "src/Oracle.sol", "contract Oracle { // TODO: staleness check\n}\n")
            git(d, "add", "-A")
            git(d, "commit", "-qm", "add price oracle", date="2026-02-20T10:00:00")
            write(d, "src/Oracle.sol", "contract Oracle { // TODO: staleness check\n uint x;\n}\n" + "// pad\n" * 300)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "rework oracle", date="2026-02-25T10:00:00")
            r = xray_git.analyze(d, src_dirs=["src"], late_days=30)
            self.assertEqual(r["repo_shape"]["shape"], "normal_dev")
            self.assertEqual(r["repo_shape"]["commits"], 4)
            top = r["fix_candidates"][0]
            self.assertIn("underflow", top["subject"])
            self.assertTrue(any("adds guard-like" in x for x in top["reasons"]))
            self.assertEqual({h["file"]: h["modifications"] for h in r["hotspots"]},
                             {"src/Vault.sol": 2, "src/Oracle.sol": 2})
            self.assertTrue(any(x["file"] == "src/Oracle.sol" and x["line"] == 1 and x["type"] == "TODO"
                                for x in r["tech_debt"]["items"]))
            self.assertTrue(r["tech_debt"]["items"][0].get("author"))
            self.assertEqual({c["author"] for c in r["contributors"]}, {"Alice", "Bob"})
            self.assertTrue(any(f["library"] == "openzeppelin" for f in r["forked_deps"]))
            self.assertGreaterEqual(r["late_changes"]["commits"], 1)
            self.assertTrue(r["late_changes"]["top"][0]["large"])
            areas = {a["area"] for a in r["dangerous_area_changes"]}
            self.assertIn("oracle_price", areas)
            # test co-change is reported with its honest caveat
            self.assertIn("NOT test coverage", r["dev_patterns"]["note"])


if __name__ == "__main__":
    unittest.main()
