"""External leads: what other tools found, folded into the work queue as leads and never as findings.

V12, Burp's scanner, nuclei, a colleague's notes: anything that is not this engagement's own proven work arrives here.
Each lead is stored in `.sieve/inputs/external-leads.json` (so a re-run of the campaign re-applies it) and becomes an
open frontier row that the drain must close with a receipt. A lead from an outside tool carries no weight at the gate:
it is only ever a place to look, and a finding still needs this engagement's own proof.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from . import frontier, util
from .state import Engagement

SEV_PRIO = {"critical": 5, "high": 5, "medium": 4, "low": 3, "informational": 2, "info": 2}


def path(eng: Engagement) -> str:
    return eng.path("inputs", "external-leads.json")


def load(eng: Engagement) -> List[Dict[str, Any]]:
    data = util.read_json(path(eng), []) or []
    out: List[Dict[str, Any]] = []
    for raw in data if isinstance(data, list) else []:
        try:
            out.append(normalise(raw))          # a hand-written or tool-written file may omit fields; never trust its shape
        except (ValueError, TypeError, AttributeError):
            continue
    return out


def normalise(raw: Dict[str, Any]) -> Dict[str, Any]:
    title = str(raw.get("title") or "").strip()
    if len(title) < 6:
        raise ValueError("a lead needs a title of at least 6 characters")
    sev = str(raw.get("severity") or "medium").strip().lower()
    return {"source": re.sub(r"[^a-z0-9._-]+", "-", str(raw.get("source") or "external").lower()).strip("-") or "external",
            "title": title[:200], "file": str(raw.get("file") or "").strip(), "line": int(raw.get("line") or 0),
            "severity": sev if sev in SEV_PRIO else "medium", "detail": str(raw.get("detail") or "").strip()[:600],
            "ref": str(raw.get("ref") or "").strip()[:200], "pack": str(raw.get("pack") or "").strip()}


def component(lead: Dict[str, Any]) -> str:
    where = f"{lead['file']}:{lead['line']} " if lead["file"] and lead["line"] else (f"{lead['file']} " if lead["file"] else "")
    return f"{where}{lead['title']}"[:120]


def apply(eng: Engagement) -> Dict[str, int]:
    """Turn every stored lead into a frontier row (idempotent) and render `xray/external-leads.md` for the bundles."""
    leads = load(eng)
    packs = list(eng.load().get("packs") or [])
    rows = [{"kind": "external-lead", "component": component(l), "pack": l["pack"] or (packs[0] if len(packs) == 1 else ""),
             "lens": "*", "prio": SEV_PRIO[l["severity"]], "source": l["source"],
             "note": f"{l['source']} {l['severity']}" + (f": {l['detail'][:70]}" if l["detail"] else "")} for l in leads]
    added = frontier.add_many(eng, rows)
    if leads:
        md = ["# External leads", "",
              "_Reported by tools and services outside this engagement. Each is a place to look, never a finding: the gates and a proof "
              "of this engagement's own decide._", ""]
        for l in sorted(leads, key=lambda x: -SEV_PRIO[x["severity"]]):
            md.append(f"- **[{l['severity']}] {component(l)}** ({l['source']})" + (f": {l['detail']}" if l["detail"] else "")
                      + (f" {l['ref']}" if l["ref"] else ""))
        util.atomic_write(eng.path("xray", "external-leads.md"), "\n".join(md) + "\n")
    return {"leads": len(leads), "added": added}


def add(eng: Engagement, raw: Dict[str, Any]) -> Dict[str, int]:
    lead = normalise(raw)
    leads = load(eng)
    key = (lead["source"], component(lead))
    if not any((l["source"], component(l)) == key for l in leads):
        leads.append(lead)
        os.makedirs(os.path.dirname(path(eng)), exist_ok=True)
        util.write_json(path(eng), leads)
    return apply(eng)
