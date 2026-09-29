"""The assembler — pashov's `assemble.sh`, in Python: mechanical only, no judgment.

Findings are written BY THE AGENT as markdown files with YAML frontmatter, following the format
`references/report-formatting.md` defines. This module never computes a confidence score, a
severity, or a verdict — it reads what the agent already decided (per `judging.md`), then dedupes,
sorts, counts, and prints. If this file starts making a judgment call, that call belongs in
`judging.md` instead, and a human should read this docstring as the reason to revert it.
"""
from __future__ import annotations

import glob
import os
from typing import Any, Dict, List, Tuple

from . import util, yamlish
from .frontier import stats as frontier_stats
from .state import Engagement

SEVERITY_ORDER = ["critical", "high", "medium", "low", "informational"]
SIZE_TRIGGER = 20


def load_findings(eng: Engagement) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Every well-formed finding/lead, plus a list of files that failed to parse (never dropped
    silently — `report-formatting.md`'s one rule: never claim to have printed more than you did)."""
    items: List[Dict[str, Any]] = []
    broken: List[str] = []
    for f in sorted(glob.glob(eng.path("findings", "*.md"))):
        base = os.path.basename(f)
        if base == "candidates.json" or base == "judged.json":
            continue
        try:
            meta, body = yamlish.split_frontmatter(util.read_text(f))
        except yamlish.YamlError as exc:
            broken.append(f"{base}: {exc}")
            continue
        if not meta:
            broken.append(f"{base}: no YAML frontmatter")
            continue
        required = ("id", "kind", "pack", "class", "status")
        missing = [k for k in required if not meta.get(k)]
        if missing:
            broken.append(f"{base}: missing {', '.join(missing)}")
            continue
        meta["_file"] = base
        meta["_body"] = body
        items.append(meta)
    return items, broken


def dedup(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One winner per group_key (pack|component|class): strongest kind, then highest confidence.
    A finding always outranks a lead regardless of confidence — a lead has none to compare."""
    kind_rank = {"FINDING": 2, "LEAD": 1, "HYPOTHESIS": 0}
    best: Dict[str, Dict[str, Any]] = {}
    for it in items:
        key = it.get("group_key") or f"{it.get('component', '')}|{it['class']}"
        cur = best.get(key)
        if cur is None:
            best[key] = it
            continue
        a, b = kind_rank.get(it.get("kind", ""), 0), kind_rank.get(cur.get("kind", ""), 0)
        if a > b or (a == b and int(it.get("confidence") or 0) > int(cur.get("confidence") or 0)):
            best[key] = it
    return list(best.values())


def _sev_key(sev: str) -> int:
    sev = (sev or "").lower()
    return SEVERITY_ORDER.index(sev) if sev in SEVERITY_ORDER else len(SEVERITY_ORDER)


def sort_findings(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda x: (_sev_key(x.get("severity", "")), -int(x.get("confidence") or 0)))


def render_finding(f: Dict[str, Any], n: int) -> str:
    conf = f.get("confidence")
    head = f"### {n}. {f.get('title', f['id'])}"
    if conf is not None:
        head = f"**[{conf}]** {head}"
    meta_line = f"`{f.get('pack', '')}/{f.get('component', f.get('class', ''))}` · {f.get('class', '')}"
    if f.get("cwe"):
        meta_line += f" · {f['cwe']}"
    if conf is not None:
        meta_line += f" · Confidence: {conf}"
    if f.get("gate"):
        meta_line += f" · Gate: {f['gate']}"
    body = f.get("_body", "").strip()
    out = [head, "", meta_line, ""]
    if body:
        out += [body, ""]
    return "\n".join(out)


def render_leads(leads: List[Dict[str, Any]]) -> str:
    if not leads:
        return "_None._"
    out = []
    for l in leads:
        smells = l.get("code_smells", "")
        out.append(f"- **{l.get('title', l['id'])}** — `{l.get('component', '')}` · {l.get('class', '')}"
                   + (f" — {smells}" if smells else ""))
    return "\n".join(out)


def build(eng: Engagement) -> Tuple[str, Dict[str, Any]]:
    items, broken = load_findings(eng)
    deduped = dedup(items)
    findings = sort_findings([f for f in deduped if f.get("kind") == "FINDING"])
    leads = [f for f in deduped if f.get("kind") == "LEAD"]
    counts = {"findings": len(findings), "leads": len(leads), "broken": len(broken)}
    for s in SEVERITY_ORDER:
        counts[s] = sum(1 for f in findings if (f.get("severity") or "").lower() == s)

    st = eng.load()
    lines = ["# Sieve Security Assessment", "", f"**Engagement:** {st['name']} (`{st['id']}`)",
             f"**Packs:** {', '.join(st['packs'])}   **Passes:** {st.get('pass_current', 0)}/{st.get('passes_planned', 1)}",
             f"**Generated:** {util.now_iso()}", "", "---", "", "## Summary", "",
             "| Severity | Count |", "|---|---|"]
    for s in SEVERITY_ORDER:
        if counts[s]:
            lines.append(f"| {s.capitalize()} | {counts[s]} |")
    lines += ["", f"_{counts['findings']} finding(s), {counts['leads']} lead(s)._", ""]
    if broken:
        lines += ["> ⚠️ **{} finding file(s) could not be read and are excluded above** — "
                  "this report prints less than the scan found, never more:".format(len(broken))]
        lines += [f"> - {b}" for b in broken]
        lines.append("")
    lines += ["---", "", "## Findings", ""]
    if not findings:
        lines.append("_None — this engagement raised no gate-confirmed findings._")
    elif len(findings) > SIZE_TRIGGER:
        lines.append(f"**{len(findings)} findings — showing the top 3 by severity/confidence. "
                     f"Full list: `.sieve/report/report.md`.**")
        lines.append("")
        for i, f in enumerate(findings[:3], 1):
            lines.append(render_finding(f, i))
    else:
        for i, f in enumerate(findings, 1):
            lines.append(render_finding(f, i))
    lines += ["---", "", "## Leads", "",
             "_Real code smells with an incomplete path — not false positives, high-signal trails "
             "for the next pass or a human reviewer._", "", render_leads(leads), "", "---", "",
             "## Coverage", ""]
    fs = frontier_stats(eng)
    lines += [f"- Frontier: {fs['closed_pct']}% closed ({fs['by_status']['done']} done, "
             f"{fs['by_status']['dead']} dead, {fs['by_status']['blocked']} blocked, {fs['open']} open)"]
    waivers = eng.path("waivers.tsv")
    if os.path.isfile(waivers):
        _h, wrows = util.read_tsv(waivers)
        lines.append(f"- {len(wrows)} coverage waiver(s) recorded (`.sieve/waivers.tsv`) — phases entered "
                     f"before their normal gate, with the operator's stated reason.")
    lines += ["", "---", "",
             "> This assessment was produced with AI assistance (Sieve). AI analysis cannot verify the "
             "complete absence of vulnerabilities, and no guarantee of security is given. A human security "
             "review, an independent audit, and ongoing monitoring remain recommended.", ""]
    return "\n".join(lines), counts


def write(eng: Engagement) -> str:
    text, counts = build(eng)
    path = eng.path("report", "report.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    util.atomic_write(path, text)
    return path
