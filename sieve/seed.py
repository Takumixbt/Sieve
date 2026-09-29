"""`sieve frontier seed` — turn the x-ray into the audit's work queue.

The frontier is what the Stop hook drains, so it has to be filled from what the x-ray actually found
(files, entry points, static-analysis leads, invariants, unauthenticated endpoints, fix-scored
commits), not from whatever the orchestrator remembers to add. Seeding is idempotent
(`frontier.add` de-duplicates), so re-running it after a re-scan only adds what is new.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple

from . import frontier, util
from .state import Engagement

_FN = re.compile(r"\b(?:function|fn|def|func|fun|public\s+entry\s+fun)\s+([A-Za-z_][A-Za-z0-9_]*)")
_INV = re.compile(r"\b(INV-\d+)\b")


def _fn_name(text: str) -> str:
    m = _FN.search(text or "")
    return m.group(1) if m else ""


def _rows_web3(f: Dict[str, Any], max_entries: int) -> List[Tuple[str, str, str, str, int, str]]:
    rows: List[Tuple[str, str, str, str, int, str]] = []   # kind, component, pack, lens, prio, note
    files = sorted(f.get("files") or [], key=lambda x: -int(x.get("nsloc") or 0))
    top = max(1, len(files) // 5)
    for i, x in enumerate(files):
        if int(x.get("nsloc") or 0) <= 0:
            continue
        rows.append(("component", x["path"], "web3", "*", 4 if i < top else 3, f"{x.get('nsloc', 0)} nSLOC"))
    seen = set()
    for e in f.get("entry_candidates") or []:
        fn = _fn_name(str(e.get("text", "")))
        comp = f"{e['file']}:{fn}" if fn else f"{e['file']}:{e['line']}"
        if comp in seen:
            continue
        seen.add(comp)
        if len(seen) > max_entries:
            break
        rows.append(("entry", comp, "web3", "*", 4, f"line {e['line']}"))
    for l in f.get("tool_leads") or []:
        if not l.get("file"):
            continue
        strong = bool(l.get("corroborated")) or str(l.get("impact", "")).lower() in ("high", "critical")
        rows.append(("tool-lead", f"{l['file']}:{l.get('line', 0)} {l.get('check', '')}"[:120], "web3", "*",
                     5 if strong else 3, f"{l.get('source')} {l.get('impact')}"
                     + (" — corroborated by 2 tools" if l.get("corroborated") else "")))
    return rows


def _rows_invariants(eng: Engagement) -> List[Tuple[str, str, str, str, int, str]]:
    p = eng.path("xray", "invariants.md")
    if not os.path.isfile(p):
        return []
    text = util.read_text(p)
    out: List[Tuple[str, str, str, str, int, str]] = []
    chunks = re.split(r"(?m)^(?=(?:#{1,4}\s*|[-*]\s*|\*\*)?INV-\d+)", text)
    for ch in chunks:
        m = _INV.search(ch[:80])
        if not m:
            continue
        no_onchain = bool(re.search(r"on-?chain:\s*no", ch, re.I))
        first = re.sub(r"\s+", " ", ch.strip().split("\n")[0])
        first = re.sub(r"^[#*\-\s]*" + m.group(1) + r"[\s:.\-—*]*", "", first)[:100]
        out.append(("invariant", f"{m.group(1)} {first}"[:120], "web3", "invariant-agent",
                    5 if no_onchain else 4, "On-chain: No — an unguarded write site exists" if no_onchain else ""))
    return out


def _rows_review_required(eng: Engagement) -> List[Tuple[str, str, str, str, int, str]]:
    p = eng.path("xray", "entry-points.md")
    if not os.path.isfile(p):
        return []
    out = []
    for line in util.read_text(p).split("\n"):
        if re.search(r"review required", line, re.I) and len(line.strip()) > 20 and not line.lstrip().startswith("#") \
                and not re.search(r"review required\W*(?:[:\-—]\s*)?(none|n/?a|no\b|nothing|0\b)", line, re.I):
            out.append(("review-required", re.sub(r"\s+", " ", line.strip(" -*|"))[:120], "web3", "*", 5,
                        "runtime-computed check — trace what makes it true"))
    return out


def _rows_web(f: Dict[str, Any]) -> List[Tuple[str, str, str, str, int, str]]:
    rows = []
    for r in f.get("surface") or []:
        unauth = r.get("auth") != "yes"
        rows.append(("endpoint", f"{r['method']} {r['path']}", "web", "access-control-agent" if unauth else "*",
                     5 if unauth else 3, f"auth: {r.get('auth')}"))
    return rows


def _rows_binary(eng: Engagement) -> List[Tuple[str, str, str, str, int, str]]:
    p = eng.path("xray", "attack-surface.md")
    if not os.path.isfile(p):
        return []
    out = []
    for line in util.read_text(p).split("\n"):
        m = re.match(r"^#{2,4}\s+(.+?)\s*$", line) or re.match(r"^[-*]\s+\*\*(.+?)\*\*", line)
        if m and m.group(1).lower() not in ("attack surface", "summary", "overview"):
            out.append(("boundary", m.group(1)[:120], "binary", "*", 4, ""))
    return out


def _rows_history(eng: Engagement) -> List[Tuple[str, str, str, str, int, str]]:
    g = util.read_json(eng.path("xray", "git-security.json"), {}) or {}
    out = []
    for c in (g.get("fix_candidates") or [])[:10]:
        if int(c.get("score") or 0) >= 3:
            out.append(("history", f"{c['sha']} {c['subject']}"[:120], "", "*", 4,
                        "fix-scored commit: Five Whys it, then hunt the pattern elsewhere"))
    for h in (g.get("hotspots") or [])[:5]:
        out.append(("hotspot", f"{h['file']}", "", "*", 3, f"{h.get('modifications')} modifications"))
    return out


def seed(eng: Engagement, max_entries: int = 500, dry_run: bool = False) -> Dict[str, Any]:
    st = eng.load()
    facts = util.read_json(eng.path("xray", "facts.json"), {}) or {}
    rows: List[Tuple[str, str, str, str, int, str]] = []
    if "web3" in st["packs"]:
        if facts.get("web3"):
            rows += _rows_web3(facts["web3"], max_entries)
        rows += _rows_invariants(eng) + _rows_review_required(eng)
    if "web" in st["packs"] and facts.get("web"):
        rows += _rows_web(facts["web"])
    if "binary" in st["packs"]:
        rows += _rows_binary(eng)
    rows += _rows_history(eng)
    if len(st["packs"]) >= 2:
        rows.append(("seam", "cross-pack seams (crossover.md)", "", "crossover-agent", 3,
                     "runs once two packs have produced output"))
    rows.append(("roaming", "whole-system roaming pass", "", "*", 2,
                 "hypothesis-craft.md §5 — no lens, no cards; three hypothesis classes nobody on the roster owns"))
    by_kind: Dict[str, int] = {}
    for r in rows:
        by_kind[r[0]] = by_kind.get(r[0], 0) + 1
    added = 0
    if not dry_run:
        added = frontier.add_many(eng, [{"kind": k, "component": c, "pack": p, "lens": l, "prio": pr, "note": n,
                                         "source": "seed"} for k, c, p, l, pr, n in rows])
    return {"candidates": len(rows), "added": added, "by_kind": by_kind, "dry_run": dry_run,
            "total": len(frontier.load(eng))}
