import json
import os
import unittest

from tests.helpers import ROOT, tmpdir  # noqa: F401

from sieve import xray_web as W

FIX = os.path.join(ROOT, "tests", "fixtures", "web")


class WebXrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facts = W.run(openapi=[os.path.join(FIX, "openapi.json")], har=[os.path.join(FIX, "sample.har")])
        cls.rows = {(r["method"], r["path"]): r for r in cls.facts["surface"]}

    def test_openapi_security_semantics(self):
        g = self.rows
        self.assertEqual(g[("GET", "/v1/invoices/{id}")]["auth"], "yes")   # inherits global security
        self.assertEqual(g[("GET", "/v1/public/status")]["auth"], "no")    # operation-level security: [] overrides
        self.assertEqual(g[("POST", "/v1/invoices")]["body_params"], ["amount", "currency", "customerId"])

    def test_har_is_ground_truth_for_auth_and_records_hosts(self):
        self.assertEqual(self.rows[("GET", "/api/users/{id}")]["auth"], "yes")   # Authorization header present
        self.assertIn("har", self.rows[("GET", "/api/users/{id}")]["sources"])
        self.assertIn("cdn.thirdparty.io", self.facts["hosts"])

    def test_sources_merge_across_inputs(self):
        # openapi has /api/users/{userId}; har has /api/users/123 -> same normalised path, both sources present
        r = self.rows[("GET", "/api/users/{id}")]
        self.assertEqual(set(r["sources"]), {"openapi", "har"})

    def test_url_list_ingestion(self):
        with tmpdir() as d:
            p = os.path.join(d, "urls.txt")
            with open(p, "w") as fh:
                fh.write("https://app.example.com/api/export?fmt=csv\n# comment\napp.example.com/health\n")
            facts = W.run(url_lists=[p])
            paths = {r["path"] for r in facts["surface"]}
            self.assertEqual(paths, {"/api/export", "/health"})

    def test_bad_input_is_a_note_not_a_crash(self):
        facts = W.run(openapi=["/no/such/file.json"])
        self.assertEqual(facts["surface"], [])
        self.assertTrue(facts["notes"])

    def test_norm_path(self):
        self.assertEqual(W.norm_path("/u/123/x/550e8400-e29b-41d4-a716-446655440000?q=1"), "/u/{id}/x/{id}")

    def test_surface_tsv_shape(self):
        header, rows = W.surface_tsv(self.facts)
        self.assertEqual(header, ["method", "path", "auth", "sources", "where"])
        self.assertEqual(len(rows), len(self.facts["surface"]))
        blob = json.dumps(rows)
        self.assertNotIn("AKIA", blob)  # this module never ingests raw JS, so no secret handling needed here


if __name__ == "__main__":
    unittest.main()
