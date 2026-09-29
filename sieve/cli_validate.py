"""`sieve verify`, `sieve prove run|add|record`, `sieve judge` — where "confirmed" is decided by machine.

    sieve verify [F-id|--all] [--rerun]        re-read every citation, re-execute proofs, check every seal
    sieve prove run F-id --oracle ... --cmd ... --expect ... --control-cmd ...
                                               run the PoC N times + a negative control; write a sealed receipt
    sieve prove add F-id --oracle ... --evidence f --expect re --control f
                                               evaluate captured artifacts (weaker: caps at trace-verified)
    sieve judge F-id --verdict cleared|confirmed|demoted|rejected ...
                                               file a verifier's verdict; `confirmed` is refused without receipts

The point of every refusal below is the same: an agent cannot talk its way to CONFIRMED.
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from . import util, validate
from .cli_core import _waive
from .config import load_config
from .state import Engagement

STAGE = {"cleared": "gates", "demoted": "gates", "rejected": "gates", "confirmed": "proof", "trace-only": "proof"}


# ---------------------------------------------------------------------------- verify

def _ensure_cites(eng: Engagement, fid: str, force: bool = False) -> Dict[str, Any]:
    meta, _ = validate.finding_meta(eng, fid)
    rs = validate.receipts(eng, fid)
    state, why = validate._cites_state(eng, meta, rs)
    if state == "pass" and not force:
        return {"ok": True, "unchanged": True, "failures": []}
    return validate.verify_cites(eng, fid)


def cmd_verify(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    ids = args.ids or validate.all_finding_ids(eng)
    if not ids:
        print("no findings to verify (`sieve merge` first).")
        return 0
    rc = 0
    for fid in ids:
        meta, _ = validate.finding_meta(eng, fid)
        if meta.get("kind") == "FINDING":
            rec = _ensure_cites(eng, fid, force=args.force)
            if not rec["ok"]:
                rc = 1
        if args.rerun:
            latest: Dict[str, Dict[str, Any]] = {}
            for r in sorted([r for r in validate.receipts(eng, fid) if r.get("kind") == "exec"], key=lambda r: r.get("time", "")):
                latest[str(r.get("oracle"))] = r
            for oracle, r in latest.items():
                if not r["_seal_ok"]:
                    print(f"{fid}: {oracle}: receipt seal invalid — not re-running")
                    rc = 1
                    continue
                print(f"{fid}: re-running {oracle} ({r.get('repeat')}× + control) …")
                try:
                    new = validate.rerun_proof(eng, fid, r)
                except SystemExit as exc:
                    print(f"  refused: {exc}")
                    rc = 1
                    continue
                print(f"  {r.get('verdict')} → {new['verdict']}" + (f"  ({'; '.join(new['reasons'])})" if new["reasons"] else ""))
                if new["verdict"] != "pass" and r.get("verdict") == "pass":
                    rc = 1
    results = [validate.assess(eng, fid) for fid in ids]
    probs = validate.ledger_problems(eng)
    if args.json:
        print(json.dumps({"findings": results, "ledger_problems": probs}, indent=2))
    else:
        print(f"\n{'ID':<7} {'SEV':<9} {'KIND':<8} {'JUDGED':<15} {'CITES':<8} {'EXEC':<18} {'TIER':<15} WHY")
        for a in results:
            print(f"{a['id']:<7} {str(a.get('severity') or '-'):<9} {str(a.get('kind') or '-'):<8} "
                  f"{str(a.get('judged') or '-'):<15} {a['cites']:<8} {a['exec']:<18} {a['tier']:<15} {'; '.join(a['why'])[:80]}")
        for p in probs:
            print("TAMPER: " + p)
        if not probs:
            print("\nledger: chain and seals intact.")
    claimed_bad = [a for a in results if a["claimed"] in ("confirmed", "trace-verified") and a["tier"] not in ("confirmed", "trace-verified")]
    for a in claimed_bad:
        print(f"MISMATCH: {a['id']} says `status: {a['claimed']}` but the machine computes `{a['tier']}` — the report prints the machine's answer.")
    return 1 if (probs or claimed_bad or rc) else 0


# ---------------------------------------------------------------------------- prove

def cmd_prove_run(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    rec = validate.run_proof(eng, args.finding, args.oracle, args.cmd, args.expect, args.control_cmd,
                             args.control_waiver, repeat=args.repeat, timeout=args.timeout, cwd=args.cwd,
                             env_names=args.env, captures=args.capture, expect_rc=args.expect_rc,
                             targets=args.target, infra=args.infra_host, control_patch=args.control_patch)
    ok = sum(1 for r in rec["runs"] if r["matched"] and r["rc_ok"])
    print(f"{args.finding} · {args.oracle} · {ok}/{rec['repeat']} runs showed the signature")
    if rec["control"]["runs"]:
        hit = sum(1 for r in rec["control"]["runs"] if r["matched"])
        print(f"negative control (command): {hit}/{len(rec['control']['runs'])} runs showed the signature "
              f"({'as required: none' if not hit else 'VACUOUS'})")
    if rec["control"].get("patch"):
        pr = rec["control"]["patch"]["runs"]
        hit = sum(1 for r in pr if r["matched"])
        print(f"negative control (fix applied to {', '.join(rec['control']['patch']['files_changed'][:3])}): "
              f"{hit}/{len(pr)} runs showed the signature ({'as required: none' if not hit else 'VACUOUS'})")
    if not rec["control"]["runs"] and not rec["control"].get("patch") and rec["control"]["waiver"]:
        print(f"negative control WAIVED: {rec['control']['waiver']}")
    if rec["measured"]:
        print("measured: " + ", ".join(f"{k}={v}" for k, v in rec["measured"].items()))
    for r in rec["reasons"]:
        print("  ✗ " + r)
    print(f"VERDICT: {rec['verdict']}  → {rec['_path']}")
    if rec["verdict"] == "fail":
        print("A failed proof is information: either the finding is wrong (`sieve judge … --verdict demoted`) or the "
              "PoC is. Fix one, then run this again — the failure stays in the ledger.")
        return 1
    if rec["verdict"] == "pass-uncontrolled":
        print("Uncontrolled: this can reach trace-verified, never confirmed.")
    print(f"NEXT: `sieve judge {args.finding} --verdict confirmed --confidence N --reason ...` (Gate 6).")
    return 0


def cmd_prove_add(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    rec = validate.add_evidence(eng, args.finding, args.oracle, args.evidence, args.expect, args.control)
    for r in rec["reasons"]:
        print("  ✗ " + r)
    print(f"{args.finding} · {args.oracle} · VERDICT {rec['verdict']}  → {rec['_path']}")
    if rec["verdict"] == "pass":
        print("Captured evidence caps at trace-verified — it was evaluated, not re-executed. For `confirmed`, "
              "`sieve prove run` a replay command.")
    return 0 if rec["verdict"] == "pass" else 1


def cmd_prove_record(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    validate.finding_meta(eng, args.finding)
    validate.write_receipt(eng, args.finding, f"asserted-{args.oracle}",
                           {"kind": "asserted", "oracle": args.oracle, "evidence": args.evidence})
    print(f"recorded (ASSERTED): {args.finding} via {args.oracle}")
    print("note: an asserted receipt is a note, not a proof — nothing evaluated it, so it does not count toward "
          "`confirmed`. Use `sieve prove run` (re-executed, with a negative control) or `sieve prove add`.")
    return 0


# ---------------------------------------------------------------------------- judge

def _final(entry: Dict[str, Any]) -> Dict[str, Any]:
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
        final = g
    elif g == "pending-quorum":
        final = "pending-quorum"
    elif g == "cleared" and p in ("confirmed", "trace-only", "demoted", "rejected"):
        final = p
    elif g == "cleared" and p == "pending-quorum":
        final = "cleared"
    elif g == "cleared":
        final = "cleared"
    else:
        final = None
    return {"verdict": final, "gates": g, "proof": p}


def cmd_judge(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    cfg = load_config(eng.root)
    fid = args.candidate
    meta, _ = validate.finding_meta(eng, fid)
    if meta.get("kind") != "FINDING":
        raise SystemExit(f"sieve judge: {fid} is a {meta.get('kind')}, not a FINDING candidate. Leads are promoted only "
                         f"when a later pass raises them again with proof (`sieve merge` re-keys by group_key).")
    verifier = (args.verifier or "orchestrator").strip()
    found_by = [str(x) for x in (meta.get("found_by") or [])]
    if verifier in found_by or any(verifier == x.split("/")[-1] for x in found_by):
        raise SystemExit(f"sieve judge: {verifier} discovered {fid} — discoverer != verifier (judging.md). "
                         f"Dispatch a fresh verifier with no memory of finding it.")
    verdict = args.verdict
    complexity = args.complexity or meta.get("complexity") or "straightforward"
    prior = validate.load_judged(eng).get(fid) or {"votes": []}
    stage = STAGE[verdict]
    if stage == "proof":
        gates = _final({"votes": prior.get("votes", []), "complexity": complexity})["gates"]
        if gates != "cleared":
            raise SystemExit(f"sieve judge: {fid} has not cleared Gates 0–5 (standing gates verdict: {gates or 'none'}). "
                             f"Run the gates first: `sieve judge {fid} --verdict cleared ...` by a verifier.")
    if verdict in ("confirmed", "trace-only"):
        rec = _ensure_cites(eng, fid, force=True)
        if not rec["ok"]:
            raise SystemExit(f"sieve judge: refused — citations do not check out for {fid}:\n  - "
                             + "\n  - ".join(rec.get("failures") or ["no citations verified"]))
        if args.confidence is None:
            raise SystemExit("sieve judge: --confidence N is required (judging.md's arithmetic: start at 100, deduct per rule)")
        thr = int(cfg.get("audit.confidence_threshold", 75))
        if args.confidence < thr:
            raise SystemExit(f"sieve judge: confidence {args.confidence} is below the {thr} threshold — a finding that "
                             f"cannot clear it is a lead: `--verdict demoted`.")
        sev = str(args.severity or meta.get("severity") or "").lower()
        est, ewhy, _best = validate._exec_state(validate.receipts(eng, fid))
        if verdict == "confirmed" and sev in validate.CONTROLLED_SEVERITIES and est != "pass":
            raise SystemExit(
                f"sieve judge: refused — {fid} ({sev}) has no machine-accepted proof (exec state: {est}"
                + (f", {ewhy}" if ewhy else "") + ").\n"
                f"  • run the PoC:  sieve prove run {fid} --oracle fork-test --cmd \"forge test --match-test testExploit\" "
                f"--expect \"\\[PASS\\]\" --control-cmd \"forge test --match-test testNoExploit\"\n"
                f"  • or capture:   sieve prove add {fid} --oracle two-identity-diff --evidence hit.txt --expect ... --control miss.txt "
                f"(then `--verdict trace-only`)\n"
                f"  • or, with no way to execute it: `--verdict trace-only --reason \"why it cannot be run\"` — ships as "
                f"trace-verified, never confirmed.")
        if verdict == "trace-only":
            if len((args.reason or "").strip()) < 20:
                raise SystemExit("sieve judge: --verdict trace-only needs --reason (>= 20 chars): why can it not be executed?")
            _waive(eng, "prove", f"{fid}: trace-only, no executable proof — {args.reason.strip()}")
    elif args.confidence is not None and not (0 <= args.confidence <= 100):
        raise SystemExit("sieve judge: --confidence is 0-100")

    votes = [v for v in prior.get("votes", []) if not (v["verifier"] == verifier and STAGE[v["verdict"]] == stage)]
    votes.append({"verifier": verifier, "verdict": verdict, "reason": args.reason, "gate_failed": args.gate_failed,
                  "confidence": args.confidence, "severity": args.severity, "time": util.now_iso()})
    entry: Dict[str, Any] = {"votes": votes, "complexity": complexity, "verifiers": sorted({v["verifier"] for v in votes}),
                             "reason": args.reason,
                             "confidence": next((v["confidence"] for v in reversed(votes) if v.get("confidence") is not None), None),
                             "severity": next((v["severity"] for v in reversed(votes) if v.get("severity")), None) or meta.get("severity"),
                             "trace_reason": next((v["reason"] for v in reversed(votes) if v["verdict"] == "trace-only"), None)}
    entry.update(_final(entry))
    entry["time"] = util.now_iso()
    validate.save_judgment(eng, fid, entry)
    final = entry["verdict"]
    upd: Dict[str, Any] = {"complexity": complexity, "verified_by": entry["verifiers"], "judged_at": entry["time"],
                           "confidence": entry["confidence"], "severity": entry["severity"]}
    upd["status"] = {"confirmed": "confirmed", "trace-only": "trace-verified", "cleared": "cleared", "demoted": "demoted",
                     "rejected": "rejected", "pending-quorum": "candidate"}.get(str(final), "candidate")
    if final == "demoted":
        upd["kind"] = "LEAD"
    validate.write_finding_meta(eng, fid, upd)
    tier = validate.assess(eng, fid)["tier"]
    validate.write_finding_meta(eng, fid, {"validation": tier})
    print(f"{fid}: {verdict} recorded by {verifier} → standing verdict: {final} · tier: {tier}"
          + (f" (failed at gate {args.gate_failed})" if args.gate_failed else ""))
    if final == "pending-quorum":
        print(f"complex finding: a second, independent verifier must file the same stage (`--verifier <another>`); "
              f"a disagreement demotes it.")
    if final == "cleared":
        print(f"NEXT: prove it — `sieve prove run {fid} …` — then `sieve judge {fid} --verdict confirmed …`.")
    return 0


# ---------------------------------------------------------------------------- registration

def register(sub: Any) -> None:
    p = sub.add_parser("verify", help="machine re-check: citations, sealed receipts, proofs (`--rerun`), hash drift")
    p.add_argument("ids", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--rerun", action="store_true", help="re-execute every stored proof command")
    p.add_argument("--force", action="store_true", help="write fresh citation receipts even if the old ones still hold")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("judge", help="file a verifier's verdict (discoverer != verifier; `confirmed` needs receipts)")
    p.add_argument("candidate")
    p.add_argument("--verdict", required=True, choices=["cleared", "confirmed", "trace-only", "demoted", "rejected"],
                   help="cleared = Gates 0-5 passed; confirmed/trace-only = Gate 6; demoted -> lead; rejected -> dropped")
    p.add_argument("--gate-failed", choices=["0", "1", "2", "3", "4", "5", "6"])
    p.add_argument("--reason", required=True)
    p.add_argument("--verifier")
    p.add_argument("--confidence", type=int, help="judging.md arithmetic, 0-100 (required for confirmed)")
    p.add_argument("--severity", choices=["critical", "high", "medium", "low", "informational"],
                   help="the verifier's severity (overrides the discoverer's)")
    p.add_argument("--complexity", choices=["straightforward", "complex"], help="triage routing (judging.md)")
    p.set_defaults(func=cmd_judge)

    p = sub.add_parser("prove", help="machine-checked proofs")
    ps = p.add_subparsers(dest="pcmd", required=True)
    q = ps.add_parser("run", help="execute the PoC N times + a negative control; write a sealed receipt")
    q.add_argument("finding")
    q.add_argument("--oracle", required=True,
                   help="fork-test | crash-repro | http-replay | two-identity-diff | oast-hit | timing-diff | unit-test | ...")
    q.add_argument("--cmd", required=True, help="the PoC command (runs under /bin/sh; secrets go in --env NAME)")
    q.add_argument("--expect", required=True, help="regex the output must match on EVERY run (the exploit signature)")
    q.add_argument("--control-patch", help="a diff that fixes the bug: the SAME command is re-run against a patched copy "
                   "of the target and the signature must vanish (mutation control — the strongest)")
    q.add_argument("--control-cmd", help="same PoC with the precondition removed; the signature must NOT appear")
    q.add_argument("--control-waiver", help="no control is possible (reason) — proof is then uncontrolled")
    q.add_argument("--repeat", type=int, default=3)
    q.add_argument("--timeout", type=int, default=300)
    q.add_argument("--cwd")
    q.add_argument("--env", action="append", default=[], help="pass an environment variable NAME through (repeatable)")
    q.add_argument("--capture", action="append", default=[], help="NAME=REGEX; a number measured by the run, never typed")
    q.add_argument("--expect-rc", default="0", help="expected exit code | nonzero | any")
    q.add_argument("--target", action="append", default=[], help="a host/URL the PoC talks to (scope-fenced)")
    q.add_argument("--infra-host", action="append", default=[], help="an RPC/infra host that is not a target")
    q.set_defaults(func=cmd_prove_run)
    q = ps.add_parser("add", help="evaluate captured evidence + a control artifact (caps at trace-verified)")
    q.add_argument("finding")
    q.add_argument("--oracle", required=True)
    q.add_argument("--evidence", required=True)
    q.add_argument("--expect", required=True)
    q.add_argument("--control", required=True)
    q.set_defaults(func=cmd_prove_add)
    q = ps.add_parser("record", help="(deprecated) file a note — asserted, never counts toward confirmed")
    q.add_argument("finding")
    q.add_argument("--oracle", required=True)
    q.add_argument("--evidence", required=True)
    q.set_defaults(func=cmd_prove_record)
