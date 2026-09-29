"""The hunt-pass commands: bundle, dispatch, rollcall, merge, absorb.

    sieve pass N -> bundle --all -> (spawn) -> dispatch -> (agents write) -> rollcall -> merge -> absorb

Each command records that it ran (`pass_step`), prints a receipt (a line count, a table, a list of
refusals), and ends by printing the next step, so the orchestrator never has to guess or narrate.
"""
from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict, List

from . import frontier, merge as mergelib, pipeline, seed as seedlib, util
from .cli_core import _waive
from .flow import next_action
from .state import Engagement


def _pass_no(eng: Engagement, args: argparse.Namespace) -> int:
    n = getattr(args, "pass_n", None) or int(eng.load().get("pass_current") or 0)
    if n < 1:
        raise SystemExit("sieve: no hunt pass is running (`sieve phase hunt`, then `sieve pass 1`)")
    return n


def _step(eng: Engagement, step: str, waiting: Any = "keep") -> None:
    def fn(st: Dict[str, Any]) -> None:
        st["pass_step"] = step
        if waiting != "keep":
            st["waiting"] = waiting
    eng.update(fn)


def _require_step(eng: Engagement, ok: List[str], cmd: str, force: bool = False) -> None:
    """The lifecycle is enforced, not narrated: each command needs its predecessor to have actually run."""
    have = eng.load().get("pass_step") or ""
    if have not in ok and not force:
        raise SystemExit(f"sieve {cmd}: the pass is at step {have or 'start'!r}; `sieve {cmd}` needs one of "
                         f"{', '.join(repr(x) for x in ok)} to have run first — run `sieve status` for the next step "
                         f"(`--force` overrides and is recorded).")


def _next(eng: Engagement) -> None:
    head, detail = next_action(eng)
    print(f"NEXT: {head} — {detail}")


def cmd_bundle(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    n = _pass_no(eng, args)
    manifest: Dict[str, Any] = util.read_json(eng.path("bundles", f"manifest-{n}.json"), {}) or {}
    print(f"pass {n} — building bundles")
    if args.roaming:
        path, lines, sha = pipeline.build_roaming_bundle(eng, n)
        manifest["roaming"] = {"lines": lines, "sha256": sha}
        util.write_json(eng.path("bundles", f"manifest-{n}.json"), manifest)
        print(f"  {'roaming':<44} {lines:>6} lines   {path}")
        print("\nSpawn ONE actor with:\n  " + pipeline.dispatch_prompt(path, lines, "roaming", n))
        print("\nThen: `sieve rollcall --roaming`, `sieve merge`, `sieve absorb`.")
        return 0
    agents = pipeline.roster(eng, n, only=[x for x in (args.only or "").split(",") if x])
    if not agents:
        raise SystemExit("sieve bundle: the roster is empty for this mode/packs")
    total = 0
    for a in agents:
        path, lines, sha = pipeline.build_bundle(eng, n, a)
        manifest[a["slug"]] = {"lines": lines, "sha256": sha}
        total += lines
        print(f"  {a['id']:<44} {lines:>6} lines   {'★' if a['tier'] == 'core' else ' '}")
    util.write_json(eng.path("bundles", f"manifest-{n}.json"), manifest)
    print(f"{len(agents)} bundle(s), {total} lines total → .sieve/bundles/pass-{n}/")
    _step(eng, "bundle")
    _next(eng)
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    n = _pass_no(eng, args)
    _require_step(eng, ["bundle", "dispatch"], "dispatch")
    only = [x for x in (args.only or "").split(",") if x]
    agents = pipeline.roster(eng, n, only=only)
    recs = pipeline.record_dispatch(eng, n, agents)
    if args.sequential:
        pending = [r for r in recs if not _finished(eng, n, r["slug"])]
        if not pending:
            print("every agent in this pass has finished. Next: `sieve rollcall`.")
            _step(eng, "dispatch", waiting=None)
            return 0
        r = pending[0]
        print(f"sequential mode — agent {len(recs) - len(pending) + 1} of {len(recs)}: {r['agent']}\n")
        print(pipeline.dispatch_prompt(r["bundle"], r["lines"], r["slug"], n))
        print(f"\nRun it in its own context, let it write {r['raw']}, then call `sieve dispatch --sequential` again.")
        _step(eng, "dispatch", waiting=None)
        return 0
    print(f"pass {n} — {len(recs)} agent(s) recorded. Spawn ALL of them now, in ONE message, as background calls.\n")
    for r in recs:
        print(f"── {r['agent']}  ({r['lines']} lines)")
        print(pipeline.dispatch_prompt(r["bundle"], r["lines"], r["slug"], n) + "\n")
    _step(eng, "dispatch", waiting={"since": time.time(), "pass": n, "agents": [r["slug"] for r in recs]})
    print("Waiting state set (the Stop hook will idle while they run). Do not poll. When every completion notice is in: "
          "`sieve rollcall`.")
    return 0


def _finished(eng: Engagement, n: int, slug: str) -> bool:
    from . import blocks as B
    a = next((x for x in pipeline.roster(eng, n) if x["slug"] == slug), None)
    if a is None:
        return True
    p = pipeline.raw_path(eng, n, a)
    try:
        d = B.done_marker(util.read_text(p))
    except OSError:
        return False
    return bool(d and d["agent"] == slug and d["pass"] == n)


def cmd_rollcall(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    n = _pass_no(eng, args)
    if not args.roaming:
        _require_step(eng, ["dispatch", "rollcall"], "rollcall")
    rep = pipeline.rollcall(eng, n, roaming=args.roaming)
    print(f"roll call — {'roaming pass' if args.roaming else f'pass {n}'}\n")
    print(f"{'AGENT':<44} {'STATUS':<6} {'BLOCKS F/L/H':<13} {'COVERAGE':<9} DETAIL")
    for r in rep["agents"]:
        b = r.get("blocks") or {}
        blk = f"{b.get('FINDING', 0)}/{b.get('LEAD', 0)}/{b.get('HYPOTHESIS', 0)}" if b else "-"
        detail = "; ".join(r["shortfalls"] + r["notes"])
        print(f"{r['agent']:<44} {r['status']:<6} {blk:<13} {r.get('coverage_rows', 0):<9} {detail}")
    st = eng.load()
    if rep["lost"]:
        for a in rep["lost"]:
            _waive(eng, "hunt", f"pass {n}: agent {a} produced no complete output (lost) — its ground is covered by the next pass")
        print(f"\nLOST: {', '.join(rep['lost'])} — recorded as coverage debt. Never respawn a dead agent mid-pass; the next pass covers its ground.")
    if rep["thin"] and not args.accept:
        _step(eng, "dispatch", waiting=None)
        print("\nTHIN: " + ", ".join(rep["thin"]))
        print("These agents wrote output but did not meet the completeness contract (methodology.md Part 0). "
              "Send each one back to finish (SendMessage / re-run it) with the exact shortfall above; then re-run "
              "`sieve rollcall`. Or accept the debt: `sieve rollcall --accept \"reason\"` (printed in the report).")
        return 1
    if rep["thin"] and args.accept:
        if len(args.accept.strip()) < 12:
            raise SystemExit("sieve rollcall: --accept needs a real reason (>= 12 chars)")
        for a in rep["thin"]:
            _waive(eng, "hunt", f"pass {n}: agent {a} below the completeness contract — {args.accept.strip()}")
    if not args.roaming:
        _step(eng, "rollcall", waiting=None)
    else:
        def fn(s: Dict[str, Any]) -> None:
            s["waiting"] = None
        eng.update(fn)
    print(f"\n{len(rep['ok'])} ok, {len(rep['thin'])} thin, {len(rep['lost'])} lost. → .sieve/logs/rollcall-{'roaming' if args.roaming else n}.json")
    _next(eng)
    return 1 if rep["lost"] and not rep["ok"] else 0


def cmd_merge(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    if not args.final:
        _require_step(eng, ["rollcall", "merge", "absorb", "done"], "merge")
    res = mergelib.merge(eng)
    print(f"merged {res['files']} raw file(s) → {res['items']} item(s) "
          f"({res['findings']} FINDING, {res['leads']} LEAD, {res['hypotheses']} hypotheses; {res['new']} new)\n")
    print(f"{'AGENT#PASS':<52} {'FINDING':>7} {'LEAD':>5} {'HYP':>5} {'DEMOTED':>8}")
    for k, v in sorted(res["per_agent"].items()):
        print(f"{k:<52} {v['FINDING']:>7} {v['LEAD']:>5} {v['HYPOTHESIS']:>5} {v['demoted']:>8}")
    if res["demotions"]:
        print("\nDemoted to LEAD by the merge checks (nothing was dropped):")
        for d in res["demotions"]:
            print(f"  {d['id']}  {d['component']}  ← {d['agent']} pass {d['pass']}: {', '.join(d['why'])}")
    print("\nledger: .sieve/findings/ledger.md")
    if not args.final:
        _step(eng, "merge")
    _next(eng)
    return 0


def cmd_absorb(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    n = _pass_no(eng, args)
    _require_step(eng, ["merge", "absorb"], "absorb")
    res = mergelib.absorb(eng, n)
    for line in res["applied"]:
        print("  ✓ " + line)
    for line in res["refused"]:
        print("  ✗ " + line)
    fs = res["frontier"]
    print(f"\n{len(res['applied'])} applied, {len(res['refused'])} refused, {res['already_closed']} already closed. "
          f"Frontier: {fs['open']} open of {fs['total']} ({fs['closed_pct']}% closed).")
    if fs["open_by_lens"]:
        print("Still open by lens: " + ", ".join(f"{k}={v}" for k, v in sorted(fs["open_by_lens"].items())))
    if res["refused"]:
        print("Refused rows stay open — an agent that wants them closed must supply the receipt the refusal names.")
    _step(eng, "absorb")
    _next(eng)
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    res = seedlib.seed(eng, max_entries=args.max_entries, dry_run=args.dry_run)
    print(("would seed" if args.dry_run else "seeded") + f" {res['candidates']} candidate row(s): "
          + ", ".join(f"{k}={v}" for k, v in sorted(res["by_kind"].items())))
    if not args.dry_run:
        print(f"added {res['added']} new; frontier now holds {res['total']} row(s).")
    _next(eng)
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("bundle", help="build every agent's bundle for the current pass (prints line counts)")
    p.add_argument("--all", action="store_true", help="the whole roster (default)")
    p.add_argument("--only", help="comma list of agent names")
    p.add_argument("--pass", dest="pass_n", type=int)
    p.add_argument("--roaming", action="store_true", help="build the lens-free roaming-pass bundle")
    p.set_defaults(func=cmd_bundle)

    p = sub.add_parser("dispatch", help="verify bundles, record the spawn, print each agent's prompt")
    p.add_argument("--only")
    p.add_argument("--pass", dest="pass_n", type=int)
    p.add_argument("--sequential", action="store_true", help="no parallel dispatch: hand out one agent at a time")
    p.set_defaults(func=cmd_dispatch)

    p = sub.add_parser("rollcall", help="did every agent finish, and meet the completeness contract?")
    p.add_argument("--pass", dest="pass_n", type=int)
    p.add_argument("--roaming", action="store_true")
    p.add_argument("--accept", help="accept thin agents as recorded coverage debt (reason)")
    p.set_defaults(func=cmd_rollcall)

    p = sub.add_parser("merge", help="parse raw agent output into findings/*.md (never promotes)")
    p.add_argument("--final", action="store_true", help="the closing merge before converge")
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("absorb", help="close frontier rows the agents covered — only with receipts")
    p.add_argument("--pass", dest="pass_n", type=int)
    p.set_defaults(func=cmd_absorb)
