"""`sieve scan` mechanics: the deterministic head of every engagement.

Everything here is mechanical: no model, no network, no traffic to a target. It detects which packs a tree
needs, runs the x-ray (static analyzers included), the static rules, the knowledge-base prime and the
frontier seed, then measures the result and recommends how deep the campaign should go. The output is a
`.sieve/scan.json` that later campaign nodes reuse instead of recomputing, so a scan is never wasted work.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Optional, Tuple

from . import util
from .state import Engagement

SKIP_DIRS = {"node_modules", ".git", "lib", "test", "tests", "mocks", "mock", "script", "scripts", "build", "dist",
             "out", "cache", "artifacts", ".sieve", "Pods", "__pycache__", "venv", ".venv", "target", "coverage",
             "forge-std", ".idea", ".vscode", "vendor", "third_party"}
WEB3_EXT = {".sol", ".vy", ".move", ".cairo", ".fc", ".func", ".tolk", ".yul"}
WEB_EXT = {".js", ".mjs", ".ts", ".tsx", ".jsx", ".py", ".rb", ".php", ".java", ".cs", ".vue", ".html", ".go"}
NATIVE_EXT = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".swift", ".m", ".mm", ".smali", ".kt"}
BINARY_FILES = {".apk", ".ipa", ".aab", ".elf", ".exe", ".dll", ".so", ".dylib", ".bin", ".sys", ".ko"}
WEB_DEPS = ("express", "fastify", "koa", "next", "nuxt", "hono", "@nestjs", "django", "flask", "fastapi", "rails",
            "laravel", "spring-boot", "sinatra", "gin-gonic", "echo", "graphql", "apollo")
CHAIN_MARKERS = ("foundry.toml", "hardhat.config.js", "hardhat.config.ts", "Anchor.toml", "Move.toml", "Scarb.toml",
                 "truffle-config.js", "brownie-config.yaml", "ape-config.yaml")


def _walk(root: str, max_files: int = 60000):
    n = 0
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            n += 1
            if n > max_files:
                return
            yield os.path.join(base, f)


def detect_packs(root: str) -> List[str]:
    """Which packs a tree needs, from what is actually in it. Empty when nothing is recognisable."""
    counts = {"web3": 0, "web": 0, "native": 0, "binary": 0}
    web_marker = False
    for path in _walk(root):
        ext = os.path.splitext(path)[1].lower()
        name = os.path.basename(path)
        if ext in WEB3_EXT:
            counts["web3"] += 1
        elif ext in BINARY_FILES:
            counts["binary"] += 1
        elif ext in NATIVE_EXT:
            counts["native"] += 1
        elif ext in WEB_EXT:
            counts["web"] += 1
        if name == "Cargo.toml" and os.path.isfile(os.path.join(os.path.dirname(path), "Anchor.toml")):
            counts["web3"] += 3
        if name in ("package.json", "requirements.txt", "pyproject.toml", "Gemfile", "composer.json", "pom.xml",
                    "build.gradle", "go.mod"):
            try:
                text = util.read_text(path).lower()
            except OSError:
                text = ""
            if any(dep in text for dep in WEB_DEPS):
                web_marker = True
        if name in CHAIN_MARKERS:
            counts["web3"] += 2
    packs: List[str] = []
    if counts["web3"] >= 1:
        packs.append("web3")
    # A JS/TS tree next to contracts is usually tooling and tests; it only counts as a web target when a web
    # framework is actually a dependency.
    if web_marker or (counts["web"] >= 8 and counts["web3"] == 0):
        packs.append("web")
    if counts["binary"] >= 1 or counts["native"] >= 3:
        packs.append("binary")
    return packs


def tree_fingerprint(root: str) -> str:
    """Cheap identity of the source tree (path, size, mtime), so `sieve scan` output is reused only while unchanged."""
    h = hashlib.sha256()
    for path in sorted(_walk(root)):
        ext = os.path.splitext(path)[1].lower()
        if ext not in WEB3_EXT | WEB_EXT | NATIVE_EXT | BINARY_FILES | {".toml", ".json", ".xml", ".plist", ".yml", ".yaml"}:
            continue
        try:
            st = os.stat(path)
        except OSError:
            continue
        h.update(f"{os.path.relpath(path, root)}|{st.st_size}|{int(st.st_mtime)}\n".encode())
    return h.hexdigest()[:20]


def source_lines(root: str, packs: List[str]) -> Dict[str, int]:
    exts = {"web3": WEB3_EXT | {".rs", ".go"}, "web": WEB_EXT, "binary": NATIVE_EXT | BINARY_FILES}
    out = {p: 0 for p in packs}
    for path in _walk(root):
        ext = os.path.splitext(path)[1].lower()
        for p in packs:
            if ext in exts[p]:
                if ext in BINARY_FILES:
                    out[p] += 2000          # a binary has no lines; weigh it as a mid-sized target
                    continue
                try:
                    with open(path, "rb") as fh:
                        out[p] += sum(1 for _ in fh)
                except OSError:
                    pass
    return out


def read_scan(eng: Engagement) -> Dict[str, Any]:
    return util.read_json(eng.path("scan.json"), {}) or {}


def fresh(eng: Engagement, stage: str) -> bool:
    """True when `sieve scan` already ran this stage on the tree as it is now."""
    sc = read_scan(eng)
    return bool(sc.get(stage)) and sc.get("tree") == tree_fingerprint(eng.root)


def recommend(metrics: Dict[str, Any]) -> Tuple[str, str]:
    """(profile, reason). A suggestion, never an override: the operator picks the depth."""
    kloc = float(metrics.get("kloc", 0))
    packs = list(metrics.get("packs") or [])
    entries = int(metrics.get("entry_points", 0))
    if kloc >= 15 or len(packs) >= 3 or (len(packs) >= 2 and kloc >= 8):
        return "exhaustive", f"{kloc:.1f} kLOC across {len(packs)} pack(s): large enough that depth pays for itself"
    if kloc < 1.5 and entries < 15 and len(packs) == 1:
        return "lite", f"{kloc:.1f} kLOC and {entries} entry point(s): small enough for the lean profile"
    return "default", f"{kloc:.1f} kLOC, {entries} entry point(s), {len(packs)} pack(s): a normal engagement"


def measure(eng: Engagement) -> Dict[str, Any]:
    from . import frontier
    st = eng.load()
    facts = util.read_json(eng.path("xray", "facts.json"), {}) or {}
    hits = util.read_json(eng.path("xray", "rule-hits.json"), []) or []
    lines = source_lines(eng.root, list(st["packs"]))
    web3 = facts.get("web3") or {}
    web = facts.get("web") or {}
    entries = len(web3.get("entry_candidates") or []) + int((web.get("counts") or {}).get("endpoints", 0))
    fs = frontier.stats(eng)
    m = {"packs": list(st["packs"]), "lines": lines, "kloc": round(sum(lines.values()) / 1000.0, 2),
         "web3_nsloc": int(web3.get("nsloc_total") or 0), "entry_points": entries,
         "tool_leads": len(web3.get("tool_leads") or []), "rule_hits": len(hits),
         "static_tools_ran": list(web3.get("auto_ran") or []), "frontier_rows": fs["total"]}
    m["recommended"], m["reason"] = recommend(m)
    return m


def run(eng: Engagement, refresh: bool = False, offline: bool = False) -> Dict[str, Any]:
    """The mechanical head. Idempotent: re-running adds only what is new."""
    from . import campaign_actions as A
    from . import seed as seedlib
    log: List[str] = []
    sc = {} if refresh else read_scan(eng)
    tree = tree_fingerprint(eng.root)
    if sc.get("tree") != tree:
        sc = {}
    ok, msg = A.act_xray(eng, {}, [], reuse=False)
    log.append("x-ray: " + msg)
    sc.update(tree=tree, xray=ok)
    ok, msg = A.act_rules(eng, {}, [], reuse=False)
    log.append("rules: " + msg)
    sc["rules"] = ok
    seeded = seedlib.seed(eng)
    log.append(f"frontier: +{seeded['added']} row(s) seeded from the x-ray")
    old = os.environ.get("SIEVE_OFFLINE")
    if offline:
        os.environ["SIEVE_OFFLINE"] = "1"
    try:
        ok, msg = A.act_prime(eng, {}, [])
    finally:
        if offline:
            if old is None:
                os.environ.pop("SIEVE_OFFLINE", None)
            else:
                os.environ["SIEVE_OFFLINE"] = old
    log.append("precedents: " + msg)
    metrics = measure(eng)
    sc.update(time=util.now_iso(), metrics=metrics, log=log)
    util.write_json(eng.path("scan.json"), sc)
    return sc
