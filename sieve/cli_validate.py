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

from . import judging, util, validate
from .state import Engagement

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

def cmd_judge(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    fid = args.candidate
    entry = judging.record_vote(eng, fid, args.verdict, (args.verifier or "orchestrator").strip(), args.reason,
                                confidence=args.confidence, severity=args.severity, complexity=args.complexity,
                                gate_failed=args.gate_failed)
    final = entry["verdict"]
    tier = validate.assess(eng, fid)["tier"]
    print(f"{fid}: {args.verdict} recorded by {args.verifier or 'orchestrator'} → standing verdict: {final} · tier: {tier}"
          + (f" (failed at gate {args.gate_failed})" if args.gate_failed else ""))
    if final == "pending-quorum":
        print("complex finding: a second, independent verifier must file the same stage (`--verifier <another>`); "
              "a disagreement demotes it.")
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
