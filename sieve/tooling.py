"""The tool roster, read straight from references/local-tooling.md.

That file is the single source of truth: each table row is `| tool | job | install |`, and an
`<!-- install:<group> -->` marker names the group every following table belongs to. `sieve doctor`
and `sieve install` both read it, so the roster, the install commands, and the health check can
never drift apart.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import time
from typing import Dict, List, Optional

from . import repo_root, util

MARK = re.compile(r"<!--\s*install:([\w-]+)\s*-->")
SPLIT = re.compile(r"(?<!\\)\|")
TICKS = re.compile(r"`([^`]+)`")

# `sieve install <name>` -> the marker groups it covers
GROUPS = {
    "prereq": ["prereq"],
    "web": ["web", "burp", "web-confirm"],
    "web3": ["web3"],
    "web3-chains": ["web3-chains"],
    "binary": ["binary"],
}

# Where tools land that a fresh shell's PATH may not include yet.
EXTRA_BIN_DIRS = ["~/tools/bin", "~/.sieve/venv/Scripts", "~/.local/bin", "~/go/bin", "~/.cargo/bin", "~/.foundry/bin", "~/.sieve/venv/bin",
                  "~/.avm/bin", "~/.local/share/solana/install/active_release/bin", "~/.heimdall/bin",
                  "~/.bifrost/bin", "~/.aptos/bin"]


# ---------------------------------------------------------------- this machine's specifics

# The install table is written for Linux and macOS. On Windows these tools have a native route instead.
_WIN_WINGET = "winget install --id {} -e --silent --accept-package-agreements --accept-source-agreements"
WINDOWS_INSTALL = {
    "checksec": "pipx install checksec.py",
    "binwalk": "cargo install binwalk",
    "jadx": _WIN_WINGET.format("Skylot.jadx"),
    "adb": _WIN_WINGET.format("Google.PlatformTools"),
    "pwntools": "python -m venv ~/.sieve/venv && ~/.sieve/venv/Scripts/pip install pwntools",
    "angr": "python -m venv ~/.sieve/venv && ~/.sieve/venv/Scripts/pip install angr",
}

# Tools with no executable on PATH: an install directory or an application, probed by path.
PATH_PROBES = {
    "Ghidra": ["~/tools/ghidra*/ghidraRun.bat", "~/tools/ghidra*/ghidraRun", "$GHIDRA_INSTALL_DIR/ghidraRun*"],
    "Burp Suite Pro": ["$LOCALAPPDATA/Programs/BurpSuite/BurpSuite.exe", "$LOCALAPPDATA/Programs/BurpSuitePro/BurpSuitePro.exe",
                       "/Applications/Burp Suite Professional.app", "/usr/local/BurpSuitePro/BurpSuitePro", "~/BurpSuitePro/BurpSuitePro"],
}

# Burp extensions are probed in Burp's own configuration: the substring that identifies each one.
BURP_EXT = {"Burp MCP Server": "mcp", "Autorize": "autorize", "Turbo Intruder": "turbo intruder", "Param Miner": "param miner",
            "JWT Editor": "jwt editor", "HTTP Request Smuggler": "request smuggler", "InQL": "inql"}


def burp_config_path() -> Optional[str]:
    for p in (os.path.join(os.environ.get("APPDATA", ""), "BurpSuite", "UserConfig.json"),
              os.path.join(os.path.expanduser("~"), ".BurpSuite", "UserConfig.json"),
              os.path.join(os.path.expanduser("~"), "Library", "Application Support", "BurpSuite", "UserConfig.json")):
        if p and os.path.isfile(p):
            return p
    return None


def burp_extensions() -> Optional[List[Dict[str, object]]]:
    """The extensions Burp itself has configured, read from its user config on disk (its own state, not a guess)."""
    p = burp_config_path()
    if not p:
        return None
    d = util.read_json(p, {}) or {}
    exts = (((d.get("user_options") or {}).get("extender") or {}).get("extensions")) or []
    return [{"name": str(e.get("name", "")), "loaded": bool(e.get("loaded"))} for e in exts if isinstance(e, dict)]


def burp_downloaded() -> List[str]:
    """Names of BApps Burp has downloaded (BappManifest.bmf in its bapps folder), whether or not they are enabled."""
    cfg = burp_config_path()
    if not cfg:
        return []
    names: List[str] = []
    for mf in glob.glob(os.path.join(os.path.dirname(cfg), "bapps", "*", "BappManifest.bmf")):
        try:
            for line in util.read_text(mf).splitlines():
                if line.lower().startswith("name:"):
                    names.append(line.split(":", 1)[1].strip())
                    break
        except OSError:
            continue
    return names


_WSL: Optional[Dict[str, str]] = None


def wsl_tools() -> Dict[str, str]:
    """{binary: path inside WSL} for every roster binary WSL has. Windows only, one batched call (a cold WSL start takes
    a while), cached for a day in ~/.sieve/wsl-tools.json. Linux-only tools live here on a Windows machine."""
    global _WSL
    if _WSL is not None:
        return _WSL
    if os.name != "nt" or not shutil.which("wsl.exe"):
        _WSL = {}
        return _WSL
    from .config import user_home
    cache = os.path.join(user_home(), "wsl-tools.json")
    c = util.read_json(cache, None)
    if isinstance(c, dict) and time.time() - float(c.get("time", 0)) < 86400:
        _WSL = dict(c.get("tools") or {})
        return _WSL
    names = sorted({t["bin"] for grp in load_all().values() for t in grp if t["bin"]})
    script = "for t in " + " ".join(names) + '; do p=$(command -v $t 2>/dev/null) && echo "$t=$p"; done'
    found: Dict[str, str] = {}
    try:
        out = subprocess.run(["wsl.exe", "-e", "bash", "-lc", script], capture_output=True, timeout=150).stdout
        for line in out.decode("utf-8", "replace").replace(chr(0), "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                found[k.strip()] = v.strip()
    except (OSError, subprocess.TimeoutExpired):
        _WSL = {}
        return _WSL
    util.write_json(cache, {"time": time.time(), "tools": found})
    _WSL = found
    return _WSL


VENV_MODULES = {"pwntools": "pwn", "angr": "angr"}


def venv_has(name: str) -> bool:
    """A Python library installed into Sieve's own venv (~/.sieve/venv), probed by its package directory."""
    mod = VENV_MODULES.get(name)
    if not mod:
        return False
    home = os.path.expanduser("~/.sieve/venv")
    for pat in (os.path.join(home, "Lib", "site-packages", mod), os.path.join(home, "lib", "python*", "site-packages", mod)):
        if glob.glob(pat):
            return True
    return False


def path_probe(name: str) -> Optional[str]:
    for pat in PATH_PROBES.get(name, []):
        for hit in glob.glob(os.path.expandvars(os.path.expanduser(pat))):
            return hit
    return None


# winget unpacks portable packages into versioned folders that never reach PATH; probe them by glob.
EXTRA_BIN_GLOBS = ["~/AppData/Local/Microsoft/WinGet/Packages/*/platform-tools", "~/AppData/Local/Microsoft/WinGet/Links",
                   "~/AppData/Local/Microsoft/WinGet/Packages/*"]
_EXES = ("", ".exe", ".cmd", ".bat")


# Names another program also uses: prefer the security tool's own install location over whatever PATH finds first.
PREFER_DIRS = {"httpx": ["~/go/bin"]}


def find_bin(name: str) -> Optional[str]:
    for d in PREFER_DIRS.get(name, []):
        for ext in (("", ".exe") if os.name == "nt" else ("",)):
            cand = os.path.join(os.path.expanduser(d), name + ext)
            if os.path.isfile(cand):
                return cand
    hit = shutil.which(name)
    if hit:
        return hit
    dirs = [os.path.expanduser(d) for d in EXTRA_BIN_DIRS]
    if os.name == "nt":
        for g in EXTRA_BIN_GLOBS:
            dirs += glob.glob(os.path.expanduser(g))
    for d in dirs:
        for ext in (_EXES if os.name == "nt" else ("",)):
            cand = os.path.join(d, name + ext)
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return None


def _cells(line: str) -> List[str]:
    parts = SPLIT.split(line.strip())
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [p.strip().replace("\\|", "|") for p in parts]


def load_all(path: str = "") -> Dict[str, List[Dict[str, str]]]:
    path = path or os.path.join(repo_root(), "references", "local-tooling.md")
    groups: Dict[str, List[Dict[str, str]]] = {}
    cur: Optional[str] = None
    for line in util.read_text(path).split("\n"):
        m = MARK.search(line)
        if m:
            cur = m.group(1)
            groups.setdefault(cur, [])
            continue
        if cur is None or not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) < 3 or set(cells[0]) <= set("-: ") or cells[0].lower() == "tool":
            continue
        t = TICKS.search(cells[0])
        install = cells[2]
        cmd = TICKS.match(install)
        groups[cur].append({
            "name": (t.group(1) if t else cells[0]),
            "bin": (t.group(1).split()[0] if t else ""),
            "job": cells[1],
            "command": (cmd.group(1) if cmd else ""),
            "install": install,
        })
    return groups


def load(pack: str) -> List[Dict[str, str]]:
    """Every tool for a `sieve install` group name (web, web3, binary, ...)."""
    allg = load_all()
    out: List[Dict[str, str]] = []
    for g in GROUPS.get(pack, [pack]):
        out += allg.get(g, [])
    if os.name == "nt":
        for t in out:
            if t["name"] in WINDOWS_INSTALL:
                t["command"] = WINDOWS_INSTALL[t["name"]]
    return out


def status(tool: Dict[str, str]) -> str:
    """'ok' | 'missing' | 'manual' (no binary to probe)."""
    cmd = tool.get("command", "")
    if cmd.startswith("pip install "):          # a Python package: probe the module, not an executable
        import importlib.util
        module = cmd.split()[2].split("[")[0].split("=")[0].replace("-", "_")
        return "ok" if importlib.util.find_spec(module) else "missing"
    name = tool["name"]
    if name in BURP_EXT:
        exts = burp_extensions()
        if exts is not None:
            return "ok" if any(e["loaded"] and BURP_EXT[name] in str(e["name"]).lower() for e in exts) else "missing"
    if name in PATH_PROBES and path_probe(name):
        return "ok"
    if venv_has(name):
        return "ok"
    if not tool["bin"]:
        return "manual"
    if find_bin(tool["bin"]):
        return "ok"
    if os.name == "nt" and tool["bin"] in wsl_tools():
        return "ok"          # present inside WSL: run it as `wsl -e bash -lc '<cmd>'`
    return "missing"
