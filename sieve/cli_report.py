"""`sieve report` and `sieve judge` — assemble the deliverable; record a gate verdict."""
from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from . import report, util
from .state import Engagement


def cmd_report(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    path = report.write(eng)
    _text, counts = report.build(eng)
    print(f"wrote {path}")
    print(json.dumps(counts, indent=2))
    if counts["broken"]:
        print(f"warning: {counts['broken']} finding file(s) failed to parse — see the report's warning block")
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    """Record a gate verdict against a candidate. This does not compute the verdict — the agent
    read judging.md, ran the four gates by hand, and this just files the result so `sieve phase
    gate` can tell what's left (`flow.py:_unjudged`). Never called by the same agent/pass that
    raised the candidate (judging.md §0: discoverer != verifier)."""
    eng = Engagement.require()
    judged = util.read_json(eng.path("findings", "judged.json"), {}) or {}
    judged[args.candidate] = {"verdict": args.verdict, "gate_failed": args.gate_failed, "reason": args.reason,
                              "time": util.now_iso(), "verifier": args.verifier or "orchestrator"}
    util.write_json(eng.path("findings", "judged.json"), judged)
    print(f"{args.candidate}: {args.verdict}" + (f" (failed at {args.gate_failed})" if args.gate_failed else ""))
    return 0


def cmd_prove(args: argparse.Namespace) -> int:
    """File a proof receipt: which oracle fired, and the evidence pointer (a file under
    .sieve/proofs/, a request/response pair, a fork-test name). This does not evaluate the
    evidence — `references/judging.md` Gate 1 and the self-audit in `methodology.md` do that;
    this only records that a receipt exists, so `flow.py` can tell a proven finding from an
    unproven one before the report ships."""
    eng = Engagement.require()
    util.write_json(eng.path("proofs", f"{args.finding}-{util.slug(args.oracle)}.json"),
                    {"finding": args.finding, "oracle": args.oracle, "evidence": args.evidence,
                     "time": util.now_iso()})
    print(f"recorded: {args.finding} proven via {args.oracle}")
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("report", help="assemble the deliverable from findings/*.md")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("judge", help="record a gate verdict (discoverer != verifier)")
    p.add_argument("candidate")
    p.add_argument("--verdict", required=True, choices=["confirmed", "demoted", "rejected"])
    p.add_argument("--gate-failed", choices=["0", "1", "2", "3", "4"])
    p.add_argument("--reason", required=True)
    p.add_argument("--verifier")
    p.set_defaults(func=cmd_judge)

    p = sub.add_parser("prove", help="proof receipts for findings")
    ps = p.add_subparsers(dest="pcmd", required=True)
    q = ps.add_parser("record")
    q.add_argument("finding")
    q.add_argument("--oracle", required=True,
                   help="oast-hit | two-identity-diff | fork-test | crash-repro | frida-repro | timing-diff | ...")
    q.add_argument("--evidence", required=True, help="path under .sieve/proofs/, or a short inline description")
    q.set_defaults(func=cmd_prove)
