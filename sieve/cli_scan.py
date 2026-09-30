"""`sieve scan` — the deterministic head of an engagement: x-ray, static analyzers, rules, precedents, frontier seed.

No model, no network traffic to a target. It works on a local source tree (or a downloaded binary/package),
and ends with a measured recommendation for how deep the campaign should go.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

from . import campaign as C
from . import scan as scanlib
from . import util
from .banner import print_banner
from .config import load_config
from .fence import CASE_TEMPLATE, Fence
from .state import Engagement


def _open_or_create(root: str, packs, name, lab: bool) -> Engagement:
    eng = Engagement(root)
    if os.path.isfile(eng.state_path):
        return eng
    cfg = load_config()
    eng = Engagement.create(root, packs, name=name, passes=int(cfg.get("audit.passes", 3)), mode="deep")
    card = CASE_TEMPLATE.format(name=eng.load()["name"], packs=json.dumps(packs))
    if lab:
        card = card.replace("lab: false", "lab: true")
    util.atomic_write(eng.case_path(), card)
    util.atomic_write(eng.path("assumptions.md"),
                      "# Assumptions\n\nEvery judgement call made without asking is recorded here.\n\n")
    util.atomic_write(eng.path("plan.md"), f"# Plan: {eng.load()['name']}\n\n")
    return eng


def _autoscope(eng: Engagement) -> bool:
    """A scan only reads the local tree, so an empty scope card is filled with that tree. Live hosts and
    contracts are never auto-scoped: those stay the operator's call."""
    f = Fence.load(eng)
    if f is not None and any(f.scope.get(k) for k in ("hosts", "urls", "contracts", "paths", "binaries")):
        return False
    text = util.read_text(eng.case_path())
    if "  paths: []" not in text:
        return False
    util.atomic_write(eng.case_path(), text.replace("  paths: []", '  paths: ["."]', 1))
    return True


def cmd_scan(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.target)
    if not os.path.isdir(root):
        raise SystemExit(f"sieve scan: {root} is not a directory (scan reads a local source tree)")
    os.chdir(root)      # several steps (the knowledge-base prime) locate the engagement from the working directory
    packs = [p.strip() for p in args.pack.split(",") if p.strip()] if args.pack else scanlib.detect_packs(root)
    if not packs:
        raise SystemExit("sieve scan: could not tell which pack this tree needs; pass --pack web3,web,binary")
    if not args.quiet:
        print_banner()
    eng = _open_or_create(root, packs, args.name, args.lab)
    packs = list(eng.load()["packs"])
    scoped = _autoscope(eng)
    print(f"engagement {eng.load()['id']}  packs: {', '.join(packs)}" + ("  (scope card: this source tree)" if scoped else ""))
    sc = scanlib.run(eng, refresh=args.refresh, offline=args.offline)
    for line in sc["log"]:
        print("  " + line)
    m = sc["metrics"]
    print(f"\nmeasured: {m['kloc']} kLOC, {m['entry_points']} entry point(s), {m['tool_leads']} analyzer lead(s), "
          f"{m['rule_hits']} rule hit(s), {m['frontier_rows']} frontier row(s)")
    if m["static_tools_ran"]:
        print("analyzers that ran: " + ", ".join(m["static_tools_ran"]))
    est = C.estimate(eng)
    print("\nprofiles (agent runs each would dispatch):")
    for prof, e in est.items():
        star = "  <- recommended" if prof == m["recommended"] else ""
        print(f"  {prof:<11} {e['agentic']:>3} agent runs, {e['meta']:>2} mechanical steps{star}")
    print(f"\n{m['recommended']}: {m['reason']}.")
    if args.json:
        print(json.dumps(sc, indent=2))
    print(f"NEXT: `sieve campaign init --profile {m['recommended']}`. Fill in .sieve/case.md first if the target also has "
          "live hosts or contracts in scope (the scan only read the source tree).")
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("scan", help="the mechanical head: x-ray, analyzers, rules, precedents, frontier seed, a depth recommendation")
    p.add_argument("target", nargs="?", default=".")
    p.add_argument("--pack", help="comma list of web3, web, binary (default: detected from the tree)")
    p.add_argument("--name")
    p.add_argument("--lab", action="store_true", help="a local/lab target you own")
    p.add_argument("--refresh", action="store_true", help="ignore a previous scan of this tree")
    p.add_argument("--offline", action="store_true", help="do not touch the network (knowledge-base lookups stay local)")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_scan)
