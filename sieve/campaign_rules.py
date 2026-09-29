"""Static rule pass — the campaign's own first-look detectors.

`campaigns/rules/*.yml` holds anti-pattern rules (a regex per line, a reason, a priority); the vector cards'
`tell:` regexes ride along. This is deliberately *not* a scanner competing with Slither, Semgrep or CodeQL —
those run first and their output is folded in (`xray.md` Phase 0). It is the cheap, always-available layer
that guarantees a dangerous construct (`tx.origin`, `delegatecall`, `strcpy`, `android:exported="true"`,
string-built SQL) is on the frontier as a row somebody must close with a receipt, even on a host with no
analysis tools installed. A hit is a LEAD; the gates decide.
"""
from __future__ import annotations

import glob
import os
import re
from typing import Any, Dict, List

from . import frontier, repo_root, util, vectors, yamlish
from .state import Engagement

SKIP_DIRS = {"node_modules", ".git", "lib", "test", "tests", "mocks", "mock", "script", "scripts", "build", "dist", "out",
             "cache", "artifacts", ".sieve", "Pods", "__pycache__", "venv", ".venv", "target", "coverage", "forge-std"}
PACK_EXT = {
    "web3": ["sol", "vy", "yul", "rs", "move", "cairo", "func", "fc", "tolk", "go"],
    "web": ["js", "mjs", "ts", "tsx", "jsx", "py", "rb", "php", "java", "go", "cs", "vue", "html"],
    "binary": ["java", "kt", "smali", "xml", "plist", "swift", "m", "mm", "c", "cc", "cpp", "h", "hpp", "gradle"],
}
MAX_PER_RULE = 30


def load_rules(eng: Engagement) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    paths = sorted(glob.glob(os.path.join(repo_root(), "campaigns", "rules", "*.yml")))
    paths += sorted(glob.glob(eng.path("campaign", "rules", "*.yml")))
    for p in paths:
        data = yamlish.load_file(p)
        if isinstance(data, list):
            for r in data:
                if isinstance(r, dict) and r.get("id") and r.get("pattern"):
                    r["_src"] = os.path.relpath(p, repo_root()) if p.startswith(repo_root()) else p
                    rules.append(r)
    return rules


def lint_rules(rules: List[Dict[str, Any]]) -> List[str]:
    errs: List[str] = []
    seen = set()
    for r in rules:
        rid = str(r.get("id"))
        if rid in seen:
            errs.append(f"{r.get('_src')}: duplicate rule id {rid}")
        seen.add(rid)
        for k in ("title", "pack", "ext", "why", "prio"):
            if r.get(k) in (None, "", []):
                errs.append(f"{r.get('_src')}: {rid} is missing `{k}`")
        try:
            re.compile(str(r["pattern"]), re.I if "i" in str(r.get("flags", "")) else 0)
        except re.error as exc:
            errs.append(f"{r.get('_src')}: {rid} pattern does not compile: {exc}")
    return errs


def _files(eng: Engagement, packs: List[str]) -> List[str]:
    facts = util.read_json(eng.path("xray", "facts.json"), {}) or {}
    rel: List[str] = []
    if "web3" in packs and facts.get("web3"):
        rel += [f["path"] for f in facts["web3"].get("files", [])]
    exts = {e for p in packs for e in PACK_EXT.get(p, [])}
    have = set(rel)
    for base, dirs, files in os.walk(eng.root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.rsplit(".", 1)[-1].lower() in exts:
                p = os.path.relpath(os.path.join(base, f), eng.root)
                if p not in have:
                    rel.append(p)
                    have.add(p)
        if len(rel) > 40000:
            break
    return rel


def run(eng: Engagement) -> Dict[str, Any]:
    st = eng.load()
    packs = list(st["packs"])
    rules = [r for r in load_rules(eng) if str(r.get("pack")) in packs]
    for c in vectors.load_all():
        if c.get("tell") and c["pack"] in packs:
            rules.append({"id": c["id"], "title": c["title"], "pack": c["pack"], "ext": PACK_EXT.get(c["pack"], []),
                          "pattern": c["tell"].strip("`"), "why": c.get("attack", "")[:160], "prio": 4, "vector": c["id"]})
    files = _files(eng, packs)
    compiled = []
    for r in rules:
        try:
            compiled.append((r, re.compile(str(r["pattern"]), re.I if "i" in str(r.get("flags", "")) else 0),
                             {str(e).lower() for e in (r.get("ext") or [])}))
        except re.error:
            continue
    hits: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    scanned = 0
    for rel in files:
        ext = rel.rsplit(".", 1)[-1].lower()
        active = [(r, rx) for r, rx, exts in compiled if ext in exts and counts.get(str(r["id"]), 0) < MAX_PER_RULE]
        if not active:
            continue
        try:
            lines = util.read_text(os.path.join(eng.root, rel)).split("\n")
        except OSError:
            continue
        scanned += 1
        for n, line in enumerate(lines, 1):
            s = line.strip()
            if not s or s.startswith(("//", "/*", "*", "#", "<!--")) and not rel.endswith((".xml", ".plist")):
                continue
            for r, rx in active:
                if counts.get(str(r["id"]), 0) >= MAX_PER_RULE:
                    continue
                if rx.search(line):
                    counts[str(r["id"])] = counts.get(str(r["id"]), 0) + 1
                    hits.append({"rule": r["id"], "title": r["title"], "why": r.get("why", ""), "file": rel, "line": n,
                                 "text": s[:140], "prio": int(r.get("prio") or 3), "vector": r.get("vector")})
    util.write_json(eng.path("xray", "rule-hits.json"), hits)
    by_rule: Dict[str, List[Dict[str, Any]]] = {}
    for h in hits:
        by_rule.setdefault(h["rule"], []).append(h)
    md = ["# Static rule hits", "",
          "_Cheap first-look detectors (`campaigns/rules`, vector `tell:` regexes). A hit is a LEAD: read the line, then "
          "decide — the gates do not care that a regex matched._", ""]
    for rid, hs in sorted(by_rule.items(), key=lambda kv: -kv[1][0]["prio"]):
        md += [f"## {rid} — {hs[0]['title']} ({len(hs)} hit(s), prio {hs[0]['prio']})", f"_{hs[0]['why']}_", ""]
        md += [f"- {h['file']}:{h['line']}  `{h['text']}`" for h in hs[:12]]
        if len(hs) > 12:
            md.append(f"- … {len(hs) - 12} more in `.sieve/xray/rule-hits.json`")
        md.append("")
    util.atomic_write(eng.path("xray", "rule-hits.md"), "\n".join(md) + "\n")
    rows: List[Dict[str, Any]] = []
    grouped: Dict[Any, List[Dict[str, Any]]] = {}
    for h in hits:
        grouped.setdefault((h["rule"], h["file"]), []).append(h)
    for (rid, f), hs in grouped.items():
        first = hs[0]
        rows.append({"kind": "rule-hit", "component": f"{f}:{first['line']} {first['title']}"[:120], "lens": "*",
                     "prio": first["prio"], "source": "rules",
                     "note": f"{len(hs)} hit(s) of {rid}" + (f" ({first['vector']})" if first.get("vector") else "")})
    frontier.add_many(eng, rows)
    return {"hits": len(hits), "files": scanned, "rules": len(compiled), "rows": len(rows)}
