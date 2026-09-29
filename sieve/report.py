"""The assembler — mechanical only, no judgment: dedupe, sort, count, and print what the machine confirmed.

Findings are written by agents as markdown files with YAML frontmatter (`references/report-formatting.md`).
This module never computes a confidence score, a severity, or a verdict — those come from the verifier's
sealed judgment (`judging.md`). What it does decide is *what is allowed to be called confirmed*: the tier of
every finding is recomputed here from the receipts (`validate.assess`) and the finding file's own
`status:` line is ignored. A finding an agent labelled confirmed but the machine cannot stand behind is
printed under "Unvalidated candidates", with the reason, and counted separately.
"""
from __future__ import annotations

import glob
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import util, validate, yamlish
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
        if base in ("candidates.json", "judged.json", "ledger.md", "index.json", "hypotheses.json"):
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


def render_finding(f: Dict[str, Any], n: int, a: Optional[Dict[str, Any]] = None) -> str:
    conf = (a or {}).get("confidence") if a and a.get("confidence") is not None else f.get("confidence")
    head = f"### {n}. {f.get('title', f['id'])} (`{f['id']}`)"
    if conf is not None:
        head = f"### {n}. **[{conf}]** {f.get('title', f['id'])} (`{f['id']}`)"
    meta_line = f"`{f.get('pack', '')}/{f.get('component', f.get('class', ''))}` · {f.get('class', '')}"
    if f.get("severity"):
        meta_line += f" · {str(f['severity']).capitalize()}"
    if f.get("cwe"):
        meta_line += f" · {f['cwe']}"
    if conf is not None:
        meta_line += f" · Confidence: {conf}"
    if f.get("gate"):
        meta_line += f" · Gate: {f['gate']}"
    body = re.sub(r"(?m)^## ", "#### ", f.get("_body", "").strip())
    out = [head, "", meta_line, ""]
    if a:
        out += [_validation_line(a), ""]
    if body:
        out += [body, ""]
    return "\n".join(out)


def _validation_line(a: Dict[str, Any]) -> str:
    bits = []
    if a["tier"] == "confirmed":
        bits.append(f"executed {a.get('repeat') or '?'}× with a negative control ({a.get('oracle', 'oracle')})")
    elif a["tier"] == "trace-verified":
        bits.append("trace-verified — " + ("; ".join(a["why"]) or "no executable proof"))
    bits.append("citations re-read by code" if a["cites"] == "pass" else f"citations: {a['cites']}")
    if a.get("measured"):
        bits.append("measured: " + ", ".join(f"{k}={v}" for k, v in a["measured"].items() if v is not None))
    if a.get("verifiers"):
        bits.append("verified by " + ", ".join(a["verifiers"]))
    bits.append("sealed receipts")
    return "> **Validation:** " + " · ".join(bits)


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
    tiers = {a["id"]: a for a in validate.assess_all(eng)}
    deduped = dedup(items)
    for f in deduped:
        a = tiers.get(f["id"])
        if a and a.get("severity"):
            f["severity"] = a["severity"]
    conf_list, trace_list, unval_list, lead_list = [], [], [], []
    rejected = 0
    mismatched = []
    for f in deduped:
        a = tiers.get(f["id"]) or {"tier": "unvalidated", "why": ["no assessment"], "cites": "missing", "exec": "missing"}
        t = a["tier"]
        if f.get("status") in ("confirmed", "trace-verified") and t not in ("confirmed", "trace-verified"):
            mismatched.append(f["id"])
        if t == "confirmed":
            conf_list.append((f, a))
        elif t == "trace-verified":
            trace_list.append((f, a))
        elif t == "rejected":
            rejected += 1
        elif t == "lead" or f.get("kind") != "FINDING":
            lead_list.append(f)
        else:
            unval_list.append((f, a))
    key = lambda fa: (_sev_key(fa[0].get("severity", "")), -int(fa[1].get("confidence") or 0))  # noqa: E731
    conf_list.sort(key=key)
    trace_list.sort(key=key)
    unval_list.sort(key=key)
    counts: Dict[str, Any] = {"findings": len(conf_list), "trace_verified": len(trace_list),
                              "unvalidated": sum(1 for _f, a in unval_list if a["tier"] == "unvalidated"),
                              "stale": sum(1 for _f, a in unval_list if a["tier"] == "stale"),
                              "tampered": sum(1 for _f, a in unval_list if a["tier"] == "tampered"),
                              "leads": len(lead_list), "rejected": rejected, "broken": len(broken)}
    for s in SEVERITY_ORDER:
        counts[s] = sum(1 for f, _a in conf_list if (f.get("severity") or "").lower() == s)

    st = eng.load()
    lines = ["# Sieve Security Assessment", "", f"**Engagement:** {st['name']} (`{st['id']}`)",
             f"**Packs:** {', '.join(st['packs'])}   **Passes:** {st.get('pass_current', 0)}/{st.get('passes_planned', 1)}",
             f"**Generated:** {util.now_iso()}", "", "---", "", "## Summary", "",
             "| Severity (confirmed only) | Count |", "|---|---|"]
    for s in SEVERITY_ORDER:
        if counts[s]:
            lines.append(f"| {s.capitalize()} | {counts[s]} |")
    lines += ["", f"_{counts['findings']} confirmed · {counts['trace_verified']} trace-verified · "
              f"{len(unval_list)} unvalidated candidate(s) · {counts['leads']} lead(s) · {rejected} rejected._",
              "", "> **How to read this:** *Confirmed* means a machine re-executed the proof several times with a "
              "negative control, re-read every citation, and a verifier who did not find it signed off "
              "(`references/validation.md`). Nothing else is printed as a finding.", ""]
    if mismatched:
        lines += [f"> ⚠️ {len(mismatched)} finding file(s) ({', '.join(mismatched[:8])}) carry `status: confirmed` but the "
                  f"machine computes a lower tier — this report prints the machine's answer, not the file's claim.", ""]
    if broken:
        lines += ["> ⚠️ **{} finding file(s) could not be read and are excluded above** — "
                  "this report prints less than the scan found, never more:".format(len(broken))]
        lines += [f"> - {b}" for b in broken]
        lines.append("")
    probs = validate.ledger_problems(eng)
    if probs:
        lines += ["> 🚨 **TAMPER DETECTED in the proof ledger — findings below that depend on it are not trusted:**"]
        lines += [f"> - {p}" for p in probs[:10]] + [""]
    lines += ["---", "", "## Findings", ""]
    if not conf_list:
        lines.append("_None — this engagement produced no machine-confirmed findings._")
        lines.append("")
    elif len(conf_list) > SIZE_TRIGGER:
        lines.append(f"**{len(conf_list)} findings — showing the top 3 by severity/confidence. "
                     f"Full list: `.sieve/report/report.md`.**")
        lines.append("")
        for i, (f, a) in enumerate(conf_list[:3], 1):
            lines.append(render_finding(f, i, a))
    else:
        for i, (f, a) in enumerate(conf_list, 1):
            lines.append(render_finding(f, i, a))
    if trace_list:
        lines += ["---", "", "## Trace-verified findings", "",
                  "_Cleared the gates and every citation re-reads correctly, but there is no controlled executable proof "
                  "(low-severity static findings, or a proof that cannot be run here). Severity is unproven until it is "
                  "reproduced._", ""]
        for i, (f, a) in enumerate(trace_list, 1):
            lines.append(render_finding(f, i, a))
    if unval_list:
        lines += ["---", "", "## Unvalidated candidates — not confirmed", "",
                  "_Raised as findings but not machine-confirmed. Real leads for a human or the next pass; do not "
                  "report them as vulnerabilities._", ""]
        for f, a in unval_list:
            lines.append(f"- **{f.get('title', f['id'])}** (`{f['id']}`, {f.get('severity', '?')}) — "
                         f"{a['tier']}: {'; '.join(a['why']) or 'no validation'}")
        lines.append("")
    lines += ["---", "", "## Leads", "",
              "_Real code smells with an incomplete path — not false positives, high-signal trails "
              "for the next pass or a human reviewer._", "", render_leads(lead_list), "", "---", "",
              "## Coverage", ""]
    fs = frontier_stats(eng)
    lines += [f"- Frontier: {fs['closed_pct']}% closed ({fs['by_status']['done']} done, "
              f"{fs['by_status']['dead']} dead, {fs['by_status']['blocked']} blocked, {fs['open']} open)"]
    receipts_n = len(glob.glob(eng.path("proofs", "F-*--*.json")))
    lines.append(f"- Validation: {receipts_n} sealed receipt(s); ledger {'INTACT' if not probs else 'TAMPERED'}; "
                 f"{counts['findings']} confirmed, {counts['trace_verified']} trace-verified, "
                 f"{len(unval_list)} unvalidated, {rejected} rejected.")
    waivers = eng.path("waivers.tsv")
    if os.path.isfile(waivers):
        _h, wrows = util.read_tsv(waivers)
        lines.append(f"- {len(wrows)} coverage waiver(s) recorded (`.sieve/waivers.tsv`) — phases entered "
                     f"before their normal gate, agents lost or below contract, proofs accepted as trace-only, "
                     f"each with its stated reason:")
        lines += [f"  - `{r.get('phase', '')}` — {r.get('reason', '')}" for r in wrows[:25]]
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
