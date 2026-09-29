"""Web3 x-ray: mechanical facts only — discovery, nSLOC, test inventory, and a grep-only
entry-point scan across VMs.

This deliberately does NOT parse or classify code. Pashov's x-ray proved the right split:
grep is the source of truth for *which lines are candidate entry points* (cheap, exact,
language-agnostic), and the agent reads the source to classify each one (permissionless /
role-gated / admin), verified by re-reading the exact `file:line` this scan names. A Python
parser that tried to do the classification would be re-implementing Slither/Aderyn worse than
they do it — run those instead (see references/local-tooling.md) and treat their findings as
corroborating leads, the same way a Solodit precedent is a lead: real, but gated before it ships.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from . import util

EXCLUDE_DIRS = {"node_modules", "lib", "artifacts", "cache", "out", "broadcast", "coverage", "typechain",
                "typechain-types", "interfaces", "interface", "mocks", "mock", "test", "tests", ".git", "target",
                "build", "dist", ".sieve", "forge-cache", "cache_hardhat", ".venv", "venv", "__pycache__"}
LANG_BY_EXT = {".sol": "solidity", ".vy": "vyper", ".move": "move", ".cairo": "cairo", ".rs": "rust"}
RUST_FRAMEWORKS = [("anchor", r"anchor_lang|#\[program\]"), ("cosmwasm", r"cosmwasm_std|#\[entry_point\]"),
                   ("near", r"near_sdk|#\[near_bindgen\]|#\[near\("), ("soroban", r"soroban_sdk|#\[contractimpl\]"),
                   ("ink", r"\bink!|#\[ink::contract\]"), ("solana-native", r"solana_program|entrypoint!\s*\(")]
COMMENT_LINE = {"solidity": r"^\s*(//|/\*|\*|\*/)", "rust": r"^\s*(//|/\*|\*|\*/)",
                "vyper": r"^\s*#", "move": r"^\s*(//|/\*|\*|\*/)", "cairo": r"^\s*(//|/\*|\*|\*/)"}

# One POSIX-portable pattern per language, in pashov's spirit: cheap, exact, verified by re-reading
# the line, never trusted as a classification. Multi-line Solidity signatures need the second pass
# pashov's x-ray also runs (closing-paren-on-its-own-line); the other languages here don't commonly
# wrap a visibility/decorator across lines, so one pattern each is enough.
ENTRY_PATTERNS: Dict[str, List["re.Pattern[str]"]] = {
    "solidity": [
        re.compile(r"function\s+\w+\s*\([^)]*\)\s+(external|public)"),
        re.compile(r"^\s*\)\s*(external|public)", re.M),
    ],
    "vyper": [re.compile(r"^@external", re.M)],
    "move": [re.compile(r"\b(public\s+entry\s+fun|entry\s+fun)\s+\w+")],
    "cairo": [re.compile(r"#\[(external\(v0\)|abi\(embed_v0\)|l1_handler|constructor)\]")],
    "anchor": [re.compile(r"pub\s+fn\s+\w+\s*\(\s*ctx\s*:\s*Context")],
}


def _excluded_file(name: str) -> bool:
    return name.endswith(".t.sol") or ("Test" in name and name.endswith(".sol")) or \
        ("Mock" in name and name.endswith(".sol"))


def detect_src_dirs(root: str) -> List[str]:
    dirs: List[str] = []
    ft = os.path.join(root, "foundry.toml")
    if os.path.isfile(ft):
        m = re.search(r'^\s*src\s*=\s*"([^"]+)"', util.read_text(ft), re.M)
        if m:
            dirs.append(m.group(1))
    for name in ("hardhat.config.js", "hardhat.config.ts", "hardhat.config.cjs", "hardhat.config.mjs"):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            m = re.search(r'sources\s*:\s*["\']([^"\']+)["\']', util.read_text(p))
            if m:
                dirs.append(m.group(1).lstrip("./"))
    for cand in ("src", "contracts", "programs", "sources", "move"):
        if os.path.isdir(os.path.join(root, cand)) and cand not in dirs:
            dirs.append(cand)
    return [d for d in dirs if os.path.isdir(os.path.join(root, d))] or ["."]


def discover(root: str, src_dirs: List[str]) -> Tuple[List[Dict[str, str]], List[str]]:
    files: List[Dict[str, str]] = []
    skipped: List[str] = []
    seen = set()
    for sd in src_dirs:
        base = os.path.join(root, sd)
        for cur, dirs, names in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for n in sorted(names):
                ext = os.path.splitext(n)[1].lower()
                if ext not in LANG_BY_EXT or _excluded_file(n):
                    continue
                rel = os.path.relpath(os.path.join(cur, n), root)
                if rel in seen:
                    continue
                seen.add(rel)
                lang = LANG_BY_EXT[ext]
                framework = ""
                if lang == "rust":
                    text = util.read_text(os.path.join(root, rel))
                    framework = next((name for name, pat in RUST_FRAMEWORKS if re.search(pat, text)), "")
                    if not framework:
                        skipped.append(f"{rel} (rust file with no recognised on-chain framework)")
                        continue
                files.append({"path": rel, "lang": lang, "framework": framework})
    return files, skipped


def nsloc(text: str, lang: str) -> int:
    """Non-blank lines minus lines that START with a comment marker. Deliberately crude — the
    same heuristic pashov's enumerate.sh uses (a real comment-stripper is not worth the weight
    for a number that only orders review priority)."""
    marker = COMMENT_LINE.get(lang, r"^\s*(//|#)")
    n = 0
    for ln in text.split("\n"):
        if ln.strip() and not re.match(marker, ln):
            n += 1
    return n


def grep_entries(root: str, files: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Raw candidate entry points: file, line, the matched line's own text. Nothing classified.
    The agent reads each one and records permissionless / role-gated / admin from the real code —
    the discipline `references/xray.md` (Entry Point Scan) describes."""
    out: List[Dict[str, Any]] = []
    for f in files:
        lang = "anchor" if f.get("framework") == "anchor" else f["lang"]
        pats = ENTRY_PATTERNS.get(lang)
        if not pats:
            continue
        text = util.read_text(os.path.join(root, f["path"]))
        lines = text.split("\n")
        hit_lines = set()
        for pat in pats:
            for m in pat.finditer(text):
                hit_lines.add(text.count("\n", 0, m.start()) + 1)
        for ln in sorted(hit_lines):
            out.append({"file": f["path"], "line": ln, "lang": lang, "text": lines[ln - 1].strip()[:160]})
    return out


def _tests(root: str) -> Dict[str, Any]:
    t = {"test_files": 0, "test_functions": 0, "stateless_fuzz": 0, "foundry_invariant": 0, "echidna": 0,
         "medusa": 0, "halmos": 0, "certora_specs": 0, "fork": 0, "hardhat_tests": 0}
    for cur, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "lib", ".git", "out", "cache", "artifacts", "target", ".sieve")]
        for n in names:
            p = os.path.join(cur, n)
            rel = os.path.relpath(p, root)
            if n.endswith(".t.sol") or (n.endswith(".sol") and re.search(r"(^|/)tests?/", rel)):
                t["test_files"] += 1
                text = util.read_text(p)
                t["test_functions"] += len(re.findall(r"function\s+test\w*\s*\(", text))
                t["stateless_fuzz"] += len(re.findall(r"function\s+testFuzz\w*\s*\(", text))
                t["foundry_invariant"] += len(re.findall(r"function\s+invariant\w*\s*\(", text))
                t["echidna"] += len(re.findall(r"function\s+echidna_\w*\s*\(", text))
                t["medusa"] += len(re.findall(r"function\s+property_\w*\s*\(", text))
                t["halmos"] += len(re.findall(r"function\s+check_\w*\s*\(", text))
                if re.search(r"createFork|createSelectFork|vm\.rollFork", text):
                    t["fork"] += 1
            elif n.endswith(".spec"):
                t["certora_specs"] += 1
            elif re.search(r"\.(test|spec)\.(js|ts)$", n) and re.search(r"(^|/)tests?/", rel):
                t["hardhat_tests"] += 1
                t["test_functions"] += len(re.findall(r"\bit\s*\(", util.read_text(p)))
    return t


def _subsystem(path: str, src_dirs: List[str]) -> str:
    parts = path.split(os.sep)
    for sd in src_dirs:
        sdp = sd.strip("./").split("/") if sd not in (".", "") else []
        if sdp and parts[:len(sdp)] == sdp:
            parts = parts[len(sdp):]
            break
    return parts[0] if len(parts) > 1 else "(root)"


def run(root: str, src_dirs: Optional[List[str]] = None) -> Dict[str, Any]:
    root = os.path.abspath(root)
    dirs = src_dirs or detect_src_dirs(root)
    files, skipped = discover(root, dirs)
    by_sub: Dict[str, int] = defaultdict(int)
    total = 0
    for f in files:
        f["nsloc"] = nsloc(util.read_text(os.path.join(root, f["path"])), f["lang"])
        total += f["nsloc"]
        by_sub[_subsystem(f["path"], dirs)] += f["nsloc"]
    return {"pack": "web3", "root": root, "generated": util.now_iso(), "src_dirs": dirs,
            "languages": sorted({f["lang"] for f in files}), "files": files, "skipped": skipped,
            "nsloc_total": total, "by_subsystem": dict(by_sub),
            "entry_candidates": grep_entries(root, files), "tests": _tests(root)}
