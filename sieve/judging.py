"""Recording a verifier's verdict — the one place `confirmed` is granted, and only against receipts.

Used by `sieve judge` (an orchestrator or a dispatched verifier) and by the campaign engine (a triage
panel, and the engine's own deterministic prover). Every refusal is a SystemExit with the exact next
step, so a caller can catch it and log it, or let it reach the terminal.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import util, validate
from .cli_core import _waive
from .config import load_config
from .state import Engagement

STAGE = {"cleared": "gates", "demoted": "gates", "rejected": "gates", "confirmed": "proof", "trace-only": "proof"}


def final(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the standing verdict from the votes. Complex findings need two distinct verifiers per stage
    (judging.md: Gates 1 and 6 get an independent second pass); disagreement demotes rather than averages."""
    complex_ = entry.get("complexity") == "complex"
    out: Dict[str, Any] = {}
    for stage in ("gates", "proof"):
        votes = [v for v in entry["votes"] if STAGE[v["verdict"]] == stage]
        verdicts = {v["verdict"] for v in votes}
        who = {v["verifier"] for v in votes}
        if not votes:
            out[stage] = None
        elif verdicts & {"demoted", "rejected"}:
            out[stage] = "rejected" if verdicts == {"rejected"} else "demoted"
        elif len(verdicts) > 1:
            out[stage] = "demoted"      # e.g. one verifier said confirmed, another trace-only
        elif complex_ and len(who) < 2:
            out[stage] = "pending-quorum"
        else:
            out[stage] = next(iter(verdicts))
    g, p = out["gates"], out["proof"]
    if g in ("demoted", "rejected"):
        verdict = g
    elif g == "pending-quorum":
        verdict = "pending-quorum"
    elif g == "cleared" and p in ("confirmed", "trace-only", "demoted", "rejected"):
        verdict = p
    elif g == "cleared" and p == "pending-quorum":
        verdict = "cleared"
    elif g == "cleared":
        verdict = "cleared"
    else:
        verdict = None
    return {"verdict": verdict, "gates": g, "proof": p}


def record_vote(eng: Engagement, fid: str, verdict: str, verifier: str, reason: str,
                confidence: Optional[int] = None, severity: Optional[str] = None,
                complexity: Optional[str] = None, gate_failed: Optional[str] = None) -> Dict[str, Any]:
    cfg = load_config(eng.root)
    meta, _ = validate.finding_meta(eng, fid)
    if meta.get("kind") != "FINDING":
        raise SystemExit(f"sieve judge: {fid} is a {meta.get('kind')}, not a FINDING candidate. Leads are promoted only "
                         f"when a later pass raises them again with proof (`sieve merge` re-keys by group_key).")
    verifier = verifier.strip()
    found_by = [str(x) for x in (meta.get("found_by") or [])]
    if verifier in found_by or any(verifier == x.split("/")[-1] for x in found_by):
        raise SystemExit(f"sieve judge: {verifier} discovered {fid} — discoverer != verifier (judging.md). "
                         f"Dispatch a fresh verifier with no memory of finding it.")
    complexity = complexity or meta.get("complexity") or "straightforward"
    prior = validate.load_judged(eng).get(fid) or {"votes": []}
    stage = STAGE[verdict]
    if stage == "proof":
        gates = final({"votes": prior.get("votes", []), "complexity": complexity})["gates"]
        if gates != "cleared":
            raise SystemExit(f"sieve judge: {fid} has not cleared Gates 0–5 (standing gates verdict: {gates or 'none'}). "
                             f"Run the gates first: `sieve judge {fid} --verdict cleared ...` by a verifier.")
    if verdict in ("confirmed", "trace-only"):
        rec = _ensure_cites(eng, fid)
        if not rec["ok"]:
            raise SystemExit(f"sieve judge: refused — citations do not check out for {fid}:\n  - "
                             + "\n  - ".join(rec.get("failures") or ["no citations verified"]))
        if confidence is None:
            raise SystemExit("sieve judge: --confidence N is required (judging.md's arithmetic: start at 100, deduct per rule)")
        thr = int(cfg.get("audit.confidence_threshold", 75))
        if confidence < thr:
            raise SystemExit(f"sieve judge: confidence {confidence} is below the {thr} threshold — a finding that "
                             f"cannot clear it is a lead: `--verdict demoted`.")
        sev = str(severity or meta.get("severity") or "").lower()
        est, ewhy, _best = validate._exec_state(validate.receipts(eng, fid))
        if verdict == "confirmed" and sev in validate.CONTROLLED_SEVERITIES and est != "pass":
            raise SystemExit(
                f"sieve judge: refused — {fid} ({sev}) has no machine-accepted proof (exec state: {est}"
                + (f", {ewhy}" if ewhy else "") + ").\n"
                f"  • run the PoC:  sieve prove run {fid} --oracle fork-test --cmd \"forge test --match-test testExploit\" "
                f"--expect \"\\[PASS\\]\" --control-patch fix.diff\n"
                f"  • or capture:   sieve prove add {fid} --oracle two-identity-diff --evidence hit.txt --expect ... --control miss.txt "
                f"(then `--verdict trace-only`)\n"
                f"  • or, with no way to execute it: `--verdict trace-only --reason \"why it cannot be run\"` — ships as "
                f"trace-verified, never confirmed.")
        if verdict == "trace-only":
            if len((reason or "").strip()) < 20:
                raise SystemExit("sieve judge: --verdict trace-only needs --reason (>= 20 chars): why can it not be executed?")
            _waive(eng, "prove", f"{fid}: trace-only, no executable proof — {reason.strip()}")
    elif confidence is not None and not (0 <= confidence <= 100):
        raise SystemExit("sieve judge: --confidence is 0-100")

    votes = [v for v in prior.get("votes", []) if not (v["verifier"] == verifier and STAGE[v["verdict"]] == stage)]
    votes.append({"verifier": verifier, "verdict": verdict, "reason": reason, "gate_failed": gate_failed,
                  "confidence": confidence, "severity": severity, "time": util.now_iso()})
    entry: Dict[str, Any] = {"votes": votes, "complexity": complexity, "verifiers": sorted({v["verifier"] for v in votes}),
                             "reason": reason,
                             "confidence": next((v["confidence"] for v in reversed(votes) if v.get("confidence") is not None), None),
                             "severity": next((v["severity"] for v in reversed(votes) if v.get("severity")), None) or meta.get("severity"),
                             "trace_reason": next((v["reason"] for v in reversed(votes) if v["verdict"] == "trace-only"), None)}
    entry.update(final(entry))
    entry["time"] = util.now_iso()
    validate.save_judgment(eng, fid, entry)
    upd: Dict[str, Any] = {"complexity": complexity, "verified_by": entry["verifiers"], "judged_at": entry["time"],
                           "confidence": entry["confidence"], "severity": entry["severity"]}
    upd["status"] = {"confirmed": "confirmed", "trace-only": "trace-verified", "cleared": "cleared", "demoted": "demoted",
                     "rejected": "rejected", "pending-quorum": "candidate"}.get(str(entry["verdict"]), "candidate")
    if entry["verdict"] == "demoted":
        upd["kind"] = "LEAD"
    validate.write_finding_meta(eng, fid, upd)
    validate.write_finding_meta(eng, fid, {"validation": validate.assess(eng, fid)["tier"]})
    return entry


def _ensure_cites(eng: Engagement, fid: str) -> Dict[str, Any]:
    """A fresh citation receipt at the moment of judgment (never a stale one)."""
    return validate.verify_cites(eng, fid)
