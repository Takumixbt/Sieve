"""External leads, preflight, tool probing (Burp config, path probes, WSL, Windows installs), wallet extension resolution."""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import threading
import unittest

from tests import harness as H

from sieve import campaign_actions as A
from sieve import frontier, leads, preflight, tooling, util
from sieve.config import load_config
from sieve.state import Engagement


def scanned(case) -> Engagement:
    tmp = H.tmpdir(case)
    H.isolated_env(tmp)
    root = H.make_target(tmp)
    rc, out = H.cli("scan", root, "--offline", "--quiet")
    assert rc == 0, out
    return Engagement(root)


class LeadTests(unittest.TestCase):
    def test_a_lead_becomes_an_open_frontier_row_and_never_a_finding(self):
        eng = scanned(self)
        before = frontier.stats(eng)["total"]
        res = leads.add(eng, {"source": "V12", "title": "Reentrancy in withdraw", "file": "src/Vault.sol", "line": 7,
                              "severity": "High", "detail": "external call before the balance update"})
        self.assertEqual(res["added"], 1)
        rows = [r for r in frontier.load(eng) if r["kind"] == "external-lead"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["status"], rows[0]["prio"], rows[0]["source"]), ("open", "5", "v12"))
        self.assertEqual(frontier.stats(eng)["total"], before + 1)
        self.assertEqual(os.listdir(eng.path("findings")) if os.path.isdir(eng.path("findings")) else [], [],
                         "an outside tool's report must not create a finding")
        self.assertIn("never a finding", util.read_text(eng.path("xray", "external-leads.md")))

    def test_adding_the_same_lead_twice_is_idempotent(self):
        eng = scanned(self)
        raw = {"source": "burp", "title": "Reflected parameter in /search", "severity": "medium"}
        leads.add(eng, raw)
        self.assertEqual(leads.add(eng, raw)["added"], 0)
        self.assertEqual(len(leads.load(eng)), 1)

    def test_a_malformed_lead_is_refused(self):
        with self.assertRaises(ValueError):
            leads.normalise({"title": "x"})

    def test_severity_sets_priority(self):
        self.assertEqual([leads.SEV_PRIO[s] for s in ("critical", "medium", "low")], [5, 4, 3])

    def test_the_campaign_node_reapplies_stored_leads(self):
        eng = scanned(self)
        H.write(leads.path(eng), json.dumps([{"source": "nuclei", "title": "exposed admin panel", "severity": "high"}]))
        ok, msg = A.act_external_leads(eng, {}, [])
        self.assertTrue(ok, msg)
        self.assertIn("1 external lead", msg)
        self.assertEqual(sum(1 for r in frontier.load(eng) if r["kind"] == "external-lead"), 1)

    def test_no_leads_is_recorded_not_skipped(self):
        eng = scanned(self)
        ok, msg = A.act_external_leads(eng, {}, [])
        self.assertTrue(ok)
        self.assertIn("None supplied", util.read_text(eng.path("xray", "external-leads.md")))

    def test_cli_add_and_import(self):
        eng = scanned(self)
        rc, out = H.cli("leads", "add", "--source", "v12", "--title", "Unchecked return value", "--severity", "low", cwd=eng.root)
        self.assertEqual(rc, 0, out)
        path = os.path.join(eng.root, "batch.json")
        H.write(path, json.dumps({"findings": [{"title": "Missing access control on setFee", "severity": "high", "file": "src/Vault.sol", "line": 5},
                                               {"title": "x"}]}))
        rc, out = H.cli("leads", "import", path, "--source", "v12", cwd=eng.root)
        self.assertEqual(rc, 0, out)
        self.assertIn("1 skipped as malformed", out)
        self.assertEqual(len(leads.load(eng)), 2)


class PreflightTests(unittest.TestCase):
    def test_port_open_reflects_a_real_listener(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        self.addCleanup(srv.close)
        port = srv.getsockname()[1]
        self.assertTrue(preflight.port_open(f"127.0.0.1:{port}"))
        srv.close()
        self.assertFalse(preflight.port_open(f"127.0.0.1:{port}"))

    def test_run_covers_every_area_without_opening_a_browser_or_the_claude_cli(self):
        tmp = H.tmpdir(self)
        H.isolated_env(tmp)
        tooling._WSL = {}
        cfg = load_config()
        checks = preflight.run(cfg, identity=False, mcp=False)
        areas = {c["area"] for c in checks}
        self.assertTrue({"core", "tools", "burp", "browser", "knowledge", "persistence", "keys"} <= areas, areas)
        self.assertTrue(all(c["status"] in ("ok", "warn", "fail", "info") for c in checks))
        self.assertFalse(any(c["name"] == "test identity" for c in checks), "identity=False must not open the profile")
        for c in checks:
            if c["status"] in ("warn", "fail"):
                self.assertTrue(c["fix"] or c["area"] == "browser", f"a gap with no fix: {c}")

    def test_secret_values_never_appear_in_the_report(self):
        tmp = H.tmpdir(self)
        H.isolated_env(tmp)
        os.environ["ETHERSCAN_API_KEY"] = "SUPERSECRETVALUE123456"
        self.addCleanup(os.environ.pop, "ETHERSCAN_API_KEY", None)
        tooling._WSL = {}
        checks = preflight.run(load_config(), identity=False, mcp=False)
        self.assertNotIn("SUPERSECRETVALUE123456", json.dumps(checks))

    def test_render_lists_fixes_and_readiness(self):
        checks = [{"area": "burp", "name": "proxy listener", "status": "warn", "detail": "closed", "fix": "start Burp Suite"},
                  {"area": "core", "name": "git", "status": "ok", "detail": "found", "fix": ""}]
        text = preflight.render(checks, {"web3": "ready", "web": "degraded: Burp proxy"})
        self.assertIn("## Fixes", text)
        self.assertIn("start Burp Suite", text)
        self.assertIn("web: degraded: Burp proxy", text)

    def test_config_get(self):
        rc, out = H.cli("config", "get", "external.v12.max_cost_cents")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.strip(), "3000")
        rc, out = H.cli("config", "get", "no.such.key")
        self.assertNotEqual(rc, 0)


class ToolProbeTests(unittest.TestCase):
    def test_burp_bapps_are_read_from_burps_own_config(self):
        tmp = H.tmpdir(self)
        os.makedirs(os.path.join(tmp, "BurpSuite"))
        H.write(os.path.join(tmp, "BurpSuite", "UserConfig.json"), json.dumps({"user_options": {"extender": {"extensions": [
            {"name": "Param Miner", "loaded": True}, {"name": "Turbo Intruder", "loaded": True},
            {"name": "Autorize", "loaded": False}, {"name": "Burp MCP Server (Unrestricted)", "loaded": True}]}}}))
        old = os.environ.get("APPDATA")
        os.environ["APPDATA"] = tmp
        self.addCleanup(lambda: os.environ.__setitem__("APPDATA", old) if old is not None else os.environ.pop("APPDATA", None))
        row = lambda name: {"name": name, "bin": "", "command": "", "job": "", "install": ""}
        self.assertEqual(tooling.status(row("Param Miner")), "ok")
        self.assertEqual(tooling.status(row("Burp MCP Server")), "ok")
        self.assertEqual(tooling.status(row("Autorize")), "missing", "configured but not loaded is not usable")
        self.assertEqual(tooling.status(row("InQL")), "missing")

    def test_a_tool_found_only_by_path_counts_as_installed(self):
        tmp = H.tmpdir(self)
        os.makedirs(os.path.join(tmp, "ghidra_99"))
        H.write(os.path.join(tmp, "ghidra_99", "ghidraRun.bat"), "@echo off")
        os.environ["GHIDRA_INSTALL_DIR"] = os.path.join(tmp, "ghidra_99")
        self.addCleanup(os.environ.pop, "GHIDRA_INSTALL_DIR", None)
        self.assertEqual(tooling.status({"name": "Ghidra", "bin": "", "command": "", "job": "", "install": ""}), "ok")

    def test_wsl_only_tools_count_on_windows(self):
        tooling._WSL = {"valgrind": "/usr/bin/valgrind"}
        self.addCleanup(setattr, tooling, "_WSL", None)
        st = tooling.status({"name": "valgrind", "bin": "valgrind", "command": "sudo apt install -y valgrind", "job": "", "install": ""})
        self.assertEqual(st, "ok" if os.name == "nt" else "missing")

    @unittest.skipUnless(os.name == "nt", "Windows install overrides")
    def test_windows_gets_native_install_commands_for_linux_only_rows(self):
        cmds = {t["name"]: t["command"] for t in tooling.load("binary")}
        self.assertNotIn("apt", cmds["jadx"])
        self.assertIn("winget", cmds["jadx"])
        self.assertIn("pipx", cmds["checksec"])


def load_script():
    spec = importlib.util.spec_from_file_location("browser_recon", os.path.join(H.ROOT, "scripts", "browser-recon.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ExtensionResolutionTests(unittest.TestCase):
    ID = "bfnaelmomeimhlpmgjnjophhpkkoljpa"

    def chrome(self, versions):
        tmp = H.tmpdir(self)
        for v in versions:
            d = os.path.join(tmp, "Default", "Extensions", self.ID, v)
            os.makedirs(d)
            H.write(os.path.join(d, "manifest.json"), "{}")
        mod = load_script()
        mod.chrome_roots = lambda: [tmp]
        return mod, tmp

    def test_a_stale_path_resolves_to_the_newest_installed_version(self):
        mod, tmp = self.chrome(["26.29.1_0", "26.30.2_0", "26.9.0_0"])
        stale = os.path.join(tmp, "Default", "Extensions", self.ID, "26.29.1_0")
        got = mod.resolve_extension(stale)
        self.assertTrue(got.endswith("26.30.2_0"), got)

    def test_a_bare_id_resolves(self):
        mod, tmp = self.chrome(["1.0.0_0", "1.10.0_0"])
        self.assertTrue(mod.resolve_extension(self.ID).endswith("1.10.0_0"))

    def test_a_directory_without_an_id_is_left_alone(self):
        mod, tmp = self.chrome(["1.0.0_0"])
        self.assertEqual(mod.resolve_extension(tmp), tmp)

    def test_an_id_that_is_not_installed_falls_back_to_what_was_given(self):
        mod, tmp = self.chrome(["1.0.0_0"])
        other = "a" * 32
        self.assertEqual(mod.resolve_extension(other), other)

    def test_version_ordering_is_numeric_not_lexical(self):
        mod, _ = self.chrome(["1.0.0_0"])
        self.assertGreater(mod._version_key("26.30.2_0"), mod._version_key("26.9.0_0"))


if __name__ == "__main__":
    unittest.main()
