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
    from . import campaign
    if campaign.active(eng):
        return campaign.next_action(eng)

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
            return "Write architecture.json", "Node/edge JSON for the map, then `sieve xray map`."
        if fs["total"] == 0:
            return "Seed the frontier", "`sieve frontier seed`, then `sieve phase prime`."
        return "Finish x-ray", "`sieve phase prime`."

    if phase == "prime":
        return ("Prime from the knowledge base",
                "`sieve kb prime` (local cards + online sources), write the ranked hit list to .sieve/plan.md, "
                "then `sieve phase hunt`.")

    if phase == "hunt":
        if st.get("waiting"):
            return "Agents are running", "Wait for their completion notices (do not poll), then `sieve rollcall`."
        if p == 0:
            return "Start pass 1", "`sieve pass 1` then `sieve bundle --all`."
        order = {"": "bundle", "bundle": "dispatch", "dispatch": "rollcall", "rollcall": "merge",
                 "merge": "absorb", "absorb": "next-pass"}
        nxt = order.get(step, "bundle")
        if nxt == "next-pass":
            if p < planned:
                return f"Start pass {p + 1}", f"`sieve pass {p + 1}` then `sieve bundle --all`."
            if not _roaming_done(eng):
                return ("Roaming pass",
                        "Last pass before convergence (hypothesis-craft.md §5): `sieve bundle --roaming`, spawn ONE actor "
                        "with the printed prompt, then `sieve rollcall --roaming`, `sieve merge`, `sieve absorb`.")
            if fs["open"] > 0 and p < int(_max_passes(eng)):
                return (f"Start pass {p + 1}",
                        f"{fs['open']} frontier row(s) still open — `sieve pass {p + 1}` then `sieve bundle --all`.")
            return "Hunt finished", "`sieve phase converge`."
        detail = {
            "bundle": f"`sieve bundle --all` (pass {p}); it prints every bundle's line count — that number is the receipt.",
            "dispatch": f"Spawn every agent in ONE message, then `sieve dispatch` to record them (pass {p}); "
                        "no fan-out available? `sieve dispatch --sequential`.",
            "rollcall": f"`sieve rollcall` — verifies every agent finished and met the completeness contract (pass {p}).",
            "merge": f"`sieve merge` — parse raw output, run the deterministic checks, write findings/*.md (pass {p}).",
            "absorb": f"`sieve absorb` — close the rows the agents covered, only where a receipt exists (pass {p}).",
        }[nxt]
        return f"Pass {p}: {nxt}", detail

    if phase == "converge":
        return ("Converge",
                f"Frontier has {fs['open']} open row(s). Drain them (another `sieve pass N`) or close each with a receipt "
                "(`sieve frontier dead/done`). Then `sieve merge --final` and `sieve phase gate`.")

    if phase == "gate":
        cands = _unjudged(eng)
        if cands:
            return ("Gate the candidates",
                    "A fresh verifier runs Gates 0–5 (references/judging.md) on each of: " + ", ".join(cands[:8]) +
                    " — then `sieve judge <id> --verdict cleared|demoted|rejected --verifier <name> --reason ...` "
                    "(discoverer != verifier; complex findings need two verifiers).")
        return "Gate complete", "`sieve phase prove`."

    if phase == "prove":
        need = _unproven(eng)
        if need:
            return ("Prove the cleared findings",
                    "No machine-accepted proof yet for: " + ", ".join(need[:8]) + ". For each: write the PoC and a negative "
                    "control, `sieve prove run <id> --oracle ... --cmd ... --expect ... --control-cmd ...`, then "
                    "`sieve judge <id> --verdict confirmed --confidence N ...` (or `--verdict trace-only` with a reason).")
        return "Proofs complete", "`sieve verify --all`, then `sieve phase report`."

    if phase == "report":
        return ("Assemble the deliverables",
                "`sieve xray map`, `sieve report`, `sieve kb writeback`, `sieve vault export` (if you use Obsidian), "
                "then `sieve finish`.")

    if phase == "learn":
        return "Write back and finish", "`sieve kb writeback`, then `sieve finish`."

    return "Unknown phase", phase


def _max_passes(eng: Engagement) -> int:
    from .config import load_config
    return int(load_config(eng.root).get("audit.max_passes", 10))


def _roaming_done(eng: Engagement) -> bool:
    from . import blocks
    p = eng.path("raw", "roaming.md")
    if not os.path.isfile(p):
        return False
    d = blocks.done_marker(util.read_text(p))
    if not (d and d["agent"] == "roaming"):
        return False
    # the roaming row must also have been absorbed (closed with a receipt), not merely written
    return not any(r["kind"] == "roaming" and r["status"] in frontier.OPEN for r in frontier.load(eng))


def _unjudged(eng: Engagement) -> List[str]:
    """Candidates without a standing verdict from the gates stage (no vote, or a complex finding still
    waiting for its second verifier)."""
    from . import validate
    cand = util.read_json(eng.path("findings", "candidates.json"), {}) or {}
    judged = validate.load_judged(eng)
    return [k for k in cand if (judged.get(k) or {}).get("verdict") in (None, "pending-quorum")]


def _unproven(eng: Engagement) -> List[str]:
    """Findings that cleared the gates and still lack a machine-accepted proof."""
    from . import validate
    return validate.pending_proof(eng)


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
