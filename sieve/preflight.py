"""`sieve preflight`: is everything a real audit will reach for actually working, right now?

`sieve doctor` lists which binaries exist. Preflight goes further and *exercises* the things an audit depends on: the
Burp proxy and its MCP server answer on their ports and its BApps are loaded, CloakBrowser opens the persistent test
identity with a live login and its wallet extensions, the knowledge base and vault are populated, the Stop hook is
registered, the MCP servers the agent will call (Burp, V12) are connected. Every gap comes with the exact fix, and the
result is written to `.sieve/preflight.md` so the engagement carries a receipt of what it could and could not use.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from typing import Any, Dict, List, Optional

from . import hook as hooklib
from . import repo_root, tooling, util, validate
from .config import Config

OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"
BAPPS_WANTED = ["Autorize", "Turbo Intruder", "Param Miner", "JWT Editor", "HTTP Request Smuggler", "InQL"]


def _check(area: str, name: str, status: str, detail: str, fix: str = "") -> Dict[str, str]:
    return {"area": area, "name": name, "status": status, "detail": detail, "fix": fix}


def port_open(hostport: str, timeout: float = 1.5) -> bool:
    host, _, port = hostport.replace("http://", "").replace("https://", "").rstrip("/").partition(":")
    try:
        with socket.create_connection((host or "127.0.0.1", int(port or 80)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


burp_config_path = tooling.burp_config_path
burp_extensions = tooling.burp_extensions


def claude_mcp_status(timeout: int = 40) -> Dict[str, str]:
    """{server name: 'connected' | 'failed' | 'other'} from `claude mcp list`. Empty when the CLI is not available."""
    exe = shutil.which("claude")
    if not exe:
        return {}
    try:
        out = subprocess.run([exe, "mcp", "list"], capture_output=True, text=True, timeout=timeout, errors="replace").stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    res: Dict[str, str] = {}
    for line in out.splitlines():
        m = re.match(r"^\s*([\w.:\- ]+?):\s+\S.*?\s-\s+(.*)$", line)
        if m:
            name, tail = m.group(1).strip(), m.group(2)
            res[name] = "connected" if "Connected" in tail else ("failed" if "Fail" in tail else "other")
    return res


def identity_report(proxy: bool = False, timeout: int = 120) -> Dict[str, Any]:
    script = os.path.join(repo_root(), "scripts", "browser-recon.py")
    cmd = [sys.executable, script, "--check"] + ([] if proxy else ["--no-proxy"])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": f"identity check did not run: {exc}"}
    blob = res.stdout[res.stdout.find("{"):] if "{" in res.stdout else ""
    try:
        return json.loads(blob)
    except ValueError:
        return {"error": (res.stderr or res.stdout).strip().splitlines()[-1:] or "identity check produced no output"}


def run(cfg: Config, identity: bool = True, mcp: bool = True) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    add = out.append

    # ---- core
    py = sys.version_info
    add(_check("core", "python", OK if py >= (3, 9) else FAIL, f"{py.major}.{py.minor}.{py.micro}", "install Python 3.9 or newer"))
    add(_check("core", "git", OK if shutil.which("git") else FAIL, shutil.which("git") or "not found", "install git"))
    try:
        sh = validate.shell_argv("true")[0]
        add(_check("core", "posix shell (proof runner)", OK, sh))
    except SystemExit as exc:
        add(_check("core", "posix shell (proof runner)", FAIL, "none found", str(exc)))
    gh = shutil.which("gh")
    if gh:
        rc = subprocess.run([gh, "auth", "status"], capture_output=True, text=True).returncode
        add(_check("core", "gh (GitHub CLI)", OK if rc == 0 else WARN, "authenticated" if rc == 0 else "not logged in", "gh auth login"))
    else:
        add(_check("core", "gh (GitHub CLI)", WARN, "not installed (repo cloning and pushing use it)", "winget install GitHub.cli"))

    # ---- tools
    for pack in ("web", "web3", "binary"):
        rows = tooling.load(pack)
        gaps = [t for t in rows if tooling.status(t) == "missing"]
        missing = [t["name"] for t in gaps]
        installable = [t["name"] for t in gaps if t["command"]]
        by_hand = [t["name"] for t in gaps if not t["command"]]
        manual = [t["name"] for t in rows if tooling.status(t) == "manual"]
        have = len([t for t in rows if tooling.status(t) == "ok"])
        if missing:
            fixes = ([f"sieve install {pack} --run"] if installable else []) +                     ([f"install by hand: {', '.join(by_hand)} (Burp's BApp Store for Burp extensions)"] if by_hand else [])
            add(_check("tools", f"{pack} tools", WARN, f"{have} ready; missing: {', '.join(missing)}", "; ".join(fixes)))
        else:
            add(_check("tools", f"{pack} tools", OK, f"{have} ready" + (f"; manual: {', '.join(manual)}" if manual else "")))

    # ---- burp
    burp_cfg = cfg.get("tools.burp", {}) or {}
    proxy_addr = str(burp_cfg.get("proxy", "127.0.0.1:8080"))
    mcp_addr = str(burp_cfg.get("mcp", "127.0.0.1:13337"))
    p_ok, m_ok = port_open(proxy_addr), port_open(mcp_addr)
    add(_check("burp", "proxy listener", OK if p_ok else WARN, f"{proxy_addr} " + ("answers" if p_ok else "is closed"),
               "start Burp Suite (Proxy > Proxy settings must listen on " + proxy_addr + ")"))
    add(_check("burp", "MCP server", OK if m_ok else WARN, f"{mcp_addr} " + ("answers" if m_ok else "is closed"),
               "start Burp and load the MCP extension (MCP tab shows its host and port; set tools.burp.mcp in sieve.yaml)"))
    exts = burp_extensions()
    if exts is None:
        add(_check("burp", "BApps", INFO, "Burp's user config was not found on this machine", "open Burp once so it writes UserConfig.json"))
    else:
        loaded = [e["name"] for e in exts if e["loaded"]]
        missing_b = [b for b in BAPPS_WANTED if not any(b.lower() in n.lower() for n in loaded)]
        has_mcp = any("mcp" in n.lower() for n in loaded)
        have_files = tooling.burp_downloaded()
        dl_only = [b for b in missing_b if any(b.lower() in n.lower() for n in have_files)]
        absent = [b for b in missing_b if b not in dl_only]
        fixes = []
        if dl_only:
            fixes.append("downloaded but not enabled: " + ", ".join(dl_only) + " (Burp > Extensions > Installed: enable it; a Python BApp such as "
                         "Autorize needs the Jython jar set under Extensions > Extension settings > Python environment)")
        if absent:
            fixes.append("Burp > Extensions > BApp Store > install " + ", ".join(absent))
        add(_check("burp", "BApps loaded", OK if not missing_b else WARN, "loaded: " + (", ".join(loaded) or "none")
                   + ("; missing: " + ", ".join(missing_b) if missing_b else ""), "; ".join(fixes)))
        if not has_mcp:
            add(_check("burp", "MCP extension", WARN, "no MCP extension is loaded in Burp", "BApp Store > MCP Server"))

    # ---- browser
    have_cloak = importlib.util.find_spec("cloakbrowser") is not None
    add(_check("browser", "cloakbrowser", OK if have_cloak else FAIL, "importable" if have_cloak else "not installed",
               "pip install cloakbrowser"))
    if have_cloak:
        builds = glob.glob(os.path.join(os.path.expanduser("~"), ".cloakbrowser", "chromium-*"))
        add(_check("browser", "chromium build", OK if builds else WARN, os.path.basename(sorted(builds)[-1]) if builds else "not downloaded yet",
                   "the first launch downloads it: python scripts/browser-recon.py --check"))
        if identity:
            rep = identity_report(proxy=False)
            if rep.get("error"):
                add(_check("browser", "test identity", FAIL, str(rep["error"]), "python scripts/browser-recon.py --setup"))
            else:
                probs = []
                if not rep.get("google_session"):
                    probs.append("no signed-in Google session in the profile")
                if rep.get("extensions_missing"):
                    probs.append("extension path(s) missing: " + ", ".join(os.path.basename(os.path.dirname(e)) for e in rep["extensions_missing"]))
                want = len(rep.get("extensions_requested") or [])
                got = len(rep.get("extensions_loaded") or [])
                if want and got < want:
                    probs.append(f"{got} of {want} wallet extensions loaded")
                add(_check("browser", "test identity", OK if not probs else WARN,
                           f"profile {rep.get('profile')}; {rep.get('cookie_count', 0)} cookies; Google session: "
                           f"{'yes' if rep.get('google_session') else 'no'}; extensions loaded: {got} of {want}"
                           + ("; problems: " + "; ".join(probs) if probs else ""),
                           "python scripts/browser-recon.py --setup (headed: sign the dedicated test identity in)" if probs else ""))
            cfgfile = os.path.join(os.path.expanduser("~"), ".sieve", "browser", "browser-config.json")
            legacy = os.path.join(os.path.expanduser("~"), ".helix", "browser-config.json")
            src = cfgfile if os.path.isfile(cfgfile) else (legacy if os.path.isfile(legacy) else "")
            if src:
                bc = util.read_json(src, {}) or {}
                px = bc.get("proxy")
                if px:
                    reach = port_open(str(px))
                    add(_check("browser", "browser proxy", OK if reach else WARN, f"{px} " + ("reachable" if reach else "NOT reachable: pages will not load through it"),
                               "start Burp, or clear the proxy: python scripts/browser-recon.py --setup --no-proxy" if not reach else ""))

    # ---- knowledge base, vault, hook
    from . import kb_store, vault
    ix = kb_store.Index(cfg.path("kb.index"))
    try:
        st = ix.stats()
    finally:
        ix.close()
    n = int(st.get("precedents", 0))
    add(_check("knowledge", "precedent tier", OK if n else WARN, f"{n} row(s) from {len(st.get('precedents_by_source', {}))} source(s)",
               "sieve kb ingest"))
    root = vault.vault_root(cfg)
    add(_check("knowledge", "vault", OK if os.path.isfile(os.path.join(root, "Sieve.md")) else WARN, root, "sieve vault init"))
    hk = hooklib.installed()
    add(_check("persistence", "Stop hook", OK if any(hk.values()) else WARN, "registered" if any(hk.values()) else "not registered",
               "sieve hooks install --scope user"))

    # ---- external services the agent calls through MCP
    if mcp:
        ms = claude_mcp_status()
        if not ms:
            add(_check("mcp", "claude mcp list", INFO, "the claude CLI is not available here; the agent checks its own tool list"))
        else:
            for name, want in (("burp", "Burp MCP: authenticated replay, Repeater, Intruder, Collaborator"),
                               ("v12", "V12: an independent automated audit, folded in as leads")):
                s = ms.get(name)
                add(_check("mcp", name, OK if s == "connected" else WARN, f"{s or 'not registered'}: {want}",
                           {"burp": "claude mcp add --transport http burp http://" + mcp_addr, "v12": "claude mcp add --transport http v12 https://v12.sh/api/mcp"}[name]))

    # ---- containers (MobSF for mobile targets)
    docker = shutil.which("docker")
    if docker:
        try:
            up = subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, timeout=20).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            up = False
        if up:
            imgs = subprocess.run([docker, "images", "--format", "{{.Repository}}"], capture_output=True, text=True, timeout=20).stdout
            have_mobsf = "mobile-security-framework-mobsf" in imgs
            add(_check("containers", "docker + MobSF image", OK if have_mobsf else WARN,
                       "Docker is up; MobSF image " + ("present" if have_mobsf else "not pulled"),
                       "docker pull opensecurity/mobile-security-framework-mobsf:latest"))
        else:
            add(_check("containers", "docker", WARN, "installed but the engine is not running", "start Docker Desktop"))

    # ---- keys (presence only; never the values)
    key_file = os.path.expanduser(str(cfg.get("tools.etherscan_key_file", "~/.claude/secrets/etherscan_api_key.txt")))
    have_key = os.path.isfile(key_file) or bool(os.environ.get("ETHERSCAN_API_KEY"))
    add(_check("keys", "etherscan (on-chain reads)", OK if have_key else WARN, "key present" if have_key else "no key",
               f"save the key to {key_file} or set ETHERSCAN_API_KEY"))
    rpc = os.environ.get("ETH_RPC_URL") or os.environ.get("RPC_URL")
    add(_check("keys", "fork RPC", OK if rpc else INFO, "set" if rpc else "ETH_RPC_URL not set: fork-test proofs need an archive RPC per chain",
               "export ETH_RPC_URL=... when a proof needs a mainnet fork"))
    return out


def readiness(checks: List[Dict[str, str]]) -> Dict[str, str]:
    """Per pack: can a full engagement run, and what is the blocker."""
    def st(area: str, name: str) -> Optional[str]:
        return next((c["status"] for c in checks if c["area"] == area and c["name"] == name), None)
    res: Dict[str, str] = {}
    web3_missing = [t["name"] for t in tooling.load("web3") if t["name"] in ("forge", "slither") and tooling.status(t) != "ok"]
    res["web3"] = "ready" if not web3_missing else "blocked: " + ", ".join(web3_missing)
    blockers = []
    if st("browser", "cloakbrowser") != OK:
        blockers.append("CloakBrowser")
    if st("burp", "proxy listener") != OK:
        blockers.append("Burp proxy")
    res["web"] = "ready" if not blockers else "degraded: " + ", ".join(blockers)
    bin_missing = [t["name"] for t in tooling.load("binary") if t["name"] in ("gdb",) and tooling.status(t) != "ok"]
    dis = any(tooling.status(t) == "ok" for t in tooling.load("binary") if t["name"] in ("r2",))
    res["binary"] = "ready" if (not bin_missing and dis) else "degraded: needs a disassembler (Ghidra or radare2)"
    return res


def render(checks: List[Dict[str, str]], ready: Dict[str, str]) -> str:
    mark = {OK: "ok  ", WARN: "WARN", FAIL: "FAIL", INFO: "info"}
    lines = ["# Preflight", "", "| area | check | status | detail |", "|---|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['area']} | {c['name']} | {mark[c['status']]} | {c['detail'].replace('|', '/')} |")
    fixes = [c for c in checks if c["fix"] and c["status"] in (WARN, FAIL)]
    if fixes:
        lines += ["", "## Fixes", ""] + [f"- **{c['name']}**: `{c['fix']}`" if " " in c["fix"] and c["fix"].split()[0] in
                                        ("sieve", "python", "pip", "winget", "gh", "claude", "export", "start") else f"- **{c['name']}**: {c['fix']}"
                                        for c in fixes]
    lines += ["", "## Readiness", ""] + [f"- {p}: {s}" for p, s in ready.items()]
    lines += ["", "Every gap above that a run proceeds without is coverage debt, named in the report.", ""]
    return "\n".join(lines)
