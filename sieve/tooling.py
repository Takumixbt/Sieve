"""The tool roster, read straight from references/local-tooling.md.

That file is the single source of truth: each table row is `| tool | job | install |`, and an
`<!-- install:<group> -->` marker names the group every following table belongs to. `sieve doctor`
and `sieve install` both read it, so the roster, the install commands, and the health check can
never drift apart.
"""
from __future__ import annotations

import os
import re
import shutil
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
EXTRA_BIN_DIRS = ["~/.local/bin", "~/go/bin", "~/.cargo/bin", "~/.foundry/bin", "~/.sieve/venv/bin",
                  "~/.avm/bin", "~/.local/share/solana/install/active_release/bin", "~/.heimdall/bin",
                  "~/.bifrost/bin", "~/.aptos/bin"]


def find_bin(name: str) -> Optional[str]:
    hit = shutil.which(name)
    if hit:
        return hit
    for d in EXTRA_BIN_DIRS:
        cand = os.path.join(os.path.expanduser(d), name)
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
    return out


def status(tool: Dict[str, str]) -> str:
    """'ok' | 'missing' | 'manual' (no binary to probe)."""
    if not tool["bin"]:
        return "manual"
    return "ok" if find_bin(tool["bin"]) else "missing"
