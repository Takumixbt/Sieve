"""The engagement state machine: what must happen next. One source of truth for `sieve status`
and for the Stop hook's reason text, so the agent is never left to guess the next step."""
from __future__ import annotations

import glob
import os
from typing import Any, Dict, List, Tuple

from . import frontier, util
from .fence import Fence
from .state import Engagement


def _findings(eng: Engagement) -> List[str]:
    return sorted(glob.glob(eng.path("findings", "F-*.md")))


def _card_filled(eng: Engagement) -> bool:
    f = Fence.load(eng)
    if f is None:
        return False
    s = f.scope
    return bool(s.get("hosts") or s.get("urls") or s.get("contracts") or s.get("paths") or s.get("binaries"))


def next_action(eng: Engagement) -> Tuple[str, str]:
    """Returns (headline, detail)."""
    st = eng.load()
    phase = st.get("phase", "init")
    packs = ",".join(st.get("packs", []))
    fs = frontier.stats(eng)
    p = int(st.get("pass_current") or 0)
    planned = int(st.get("passes_planned") or 1)
    step = st.get("pass_step") or ""

    if st.get("done"):
        return "DONE", "Engagement finished. Report is in .sieve/report/."
    if st.get("halt_reason"):
        return "HALTED", f"Halted: {st['halt_reason']}. Resolve it, then `sieve continue`."

    if phase == "init":
        if not _card_filled(eng):
            return ("Fill in the scope card",
                    "Edit .sieve/case.md: list every in-scope host/contract/path and the program's rules. "
                    "Then `sieve phase xray`.")
        return "Start x-ray", "`sieve phase xray`, then `sieve xray`."

    if phase == "xray":
        if not os.path.isfile(eng.path("xray", "facts.json")):
            return "Run the mechanical x-ray", f"`sieve xray` (packs: {packs})."
        missing = [n for n in ("x-ray.md", "entry-points.md", "invariants.md")
                   if not os.path.isfile(eng.path("xray", n))]
        if missing:
            return ("Write the x-ray narrative",
                    f"Missing {', '.join(missing)}. Follow packs/<pack>/xray.md; every claim must cite file:line.")
        if not os.path.isfile(eng.path("xray", "architecture.json")):
            return "Write architecture.json", "Node/edge JSON for the map, then `sieve map`."
        if fs["total"] == 0:
            return "Seed the frontier", "`sieve frontier seed`, then `sieve phase prime`."
        return "Finish x-ray", "`sieve phase prime`."

    if phase == "prime":
        return ("Prime from the knowledge base",
                "`sieve kb prime` (local cards + online sources), write the ranked hit list to .sieve/plan.md, "
                "then `sieve phase hunt`.")

    if phase == "hunt":
        if fs["open"] == 0 and p >= planned and step in ("merge", "done"):
            return "Hunt finished", "`sieve phase converge`."
        if st.get("waiting"):
            return "Agents are running", "Wait for their completion notices, then `sieve rollcall`."
        order = {"": "bundle", "bundle": "dispatch", "dispatch": "rollcall", "rollcall": "absorb",
                 "absorb": "merge", "merge": "next-pass"}
        nxt = order.get(step, "bundle")
        if nxt == "next-pass":
            if p >= planned and fs["open"] == 0:
                return "Hunt finished", "`sieve phase converge`."
            return f"Start pass {p + 1}", f"`sieve pass {p + 1}` then `sieve bundle --all`."
        if p == 0:
            return "Start pass 1", "`sieve pass 1` then `sieve bundle --all`."
        detail = {
            "bundle": f"`sieve bundle --all` (pass {p}); print each bundle's line count.",
            "dispatch": f"Spawn every agent in ONE message, then `sieve dispatch` to record them (pass {p}).",
            "rollcall": f"`sieve rollcall` — verify every agent returned and covered its rows (pass {p}).",
            "absorb": f"`sieve absorb` — close rows the agents covered; redispatch the rest (pass {p}).",
            "merge": f"`sieve merge` — parse, dedup, ledger (pass {p}).",
        }[nxt]
        return f"Pass {p}: {nxt}", detail

    if phase == "converge":
        return ("Converge",
                f"Frontier has {fs['open']} open row(s). Drain them (new pass) or `sieve frontier` each closed with "
                "a receipt. Then `sieve merge --final` and `sieve phase gate`.")

    if phase == "gate":
        cands = _unjudged(eng)
        if cands:
            return ("Gate the candidates",
                    "`sieve judge` each of: " + ", ".join(cands[:8]) + " (discoverer != verifier: use the verifier agent).")
        return "Gate complete", "`sieve phase prove`."

    if phase == "prove":
        need = _unproven(eng)
        if need:
            return ("Prove the C/H/M findings",
                    "Receipts missing for: " + ", ".join(need[:8]) + ". `sieve prove record <id> --oracle ...`")
        return "Proofs complete", "`sieve phase report`."

    if phase == "report":
        return ("Assemble the deliverables",
                "`sieve map`, `sieve report`, `sieve kb writeback`, then `sieve finish`.")

    if phase == "learn":
        return "Write back and finish", "`sieve kb writeback`, then `sieve finish`."

    return "Unknown phase", phase


def _unjudged(eng: Engagement) -> List[str]:
    cand = util.read_json(eng.path("findings", "candidates.json"), {}) or {}
    judged = util.read_json(eng.path("findings", "judged.json"), {}) or {}
    return [k for k in cand if k not in judged]


def _unproven(eng: Engagement) -> List[str]:
    out: List[str] = []
    for f in _findings(eng):
        fid = os.path.basename(f)[:-3]
        text = util.read_text(f)
        if "severity: critical" in text or "severity: high" in text or "severity: medium" in text:
            if not glob.glob(eng.path("proofs", f"{fid}-*.json")):
                out.append(fid)
    return out


def status_dict(eng: Engagement) -> Dict[str, Any]:
    st = eng.load()
    head, detail = next_action(eng)
    return {"id": st["id"], "name": st["name"], "phase": st["phase"], "packs": st["packs"],
            "pass": f"{st.get('pass_current', 0)}/{st.get('passes_planned', 1)}",
            "pass_step": st.get("pass_step", ""), "frontier": frontier.stats(eng),
            "findings_files": len(_findings(eng)), "elapsed_min": round(eng.elapsed_minutes(st), 1),
            "waiting": st.get("waiting"), "halt_reason": st.get("halt_reason"),
            "hook": {"calls": st["counters"].get("hook_calls", 0),
                     "blocks": st["counters"].get("blocks_total", 0),
                     "no_progress": st["counters"].get("blocks_no_progress", 0)},
            "next": head, "next_detail": detail}
