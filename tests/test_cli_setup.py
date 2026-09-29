import unittest

from tests.helpers import sieve  # noqa: F401


class DoctorLintTests(unittest.TestCase):
    def test_doctor_runs_and_reports_sections(self):
        r = sieve("doctor", check=True)
        for section in ("[web]", "[web3]", "[binary]", "[knowledge base]", "[persistence]"):
            self.assertIn(section, r.stdout)
        self.assertIn("coverage-debt", r.stdout)

    def test_lint_passes_on_the_shipped_content(self):
        r = sieve("lint", check=True)
        self.assertIn("clean:", r.stdout)

    def test_lint_catches_a_broken_card(self):
        import os
        import shutil
        import tempfile
        from tests.helpers import ROOT
        tmp = tempfile.mkdtemp(prefix="sieve-lint-")
        try:
            copy = os.path.join(tmp, "sieve-copy")
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns("__pycache__", ".git"))
            bad = os.path.join(copy, "packs", "web", "vectors", "broken.md")
            with open(bad, "w") as fh:
                fh.write("### WEB-BAD-01 · Missing fields\n- signal: x\n")
            env = {"SIEVE_HOME": copy}
            r = sieve("lint", cwd=copy, env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("WEB-BAD-01", r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
