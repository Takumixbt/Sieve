"""Core commands: banner, init, phase, pass, status, frontier, ladder, halt, continue, fence, hook."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

from . import __version__, frontier, hook as hooklib, repo_root, util
from .banner import print_banner
from .config import load_config
from .fence import CASE_TEMPLATE, Fence
from .flow import next_action, status_dict
from .state import PHASES, Engagement


# ------------------------------------------------------------------ helpers

def _print_table(rows: List[Dict[str, str]], cols: List[str]) -> None:
    if not rows:
        print("(none)")
        return
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    widths = {c: min(w, 60) for c, w in widths.items()}
    print("  ".join(c.upper().ljust(widths[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r.get(c, ""))[:widths[c]].ljust(widths[c]) for c in cols))


def _waive(eng: Engagement, phase: str, reason: str) -> None:
    path = eng.path("waivers.tsv")
    new = not os.path.isfile(path)
    with open(path, "a", encoding="utf-8") as fh:
        if new:
            fh.write("time\tphase\treason\n")
        fh.write(f"{util.now_iso()}\t{phase}\t{util.tsv_escape(reason)}\n")


# ------------------------------------------------------------------ commands

def cmd_banner(args: argparse.Namespace) -> int:
    print_banner(force_color=args.color)
    return 0


def cmd_home(args: argparse.Namespace) -> int:
    print(repo_root())
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.target)
    if not os.path.isdir(root):
        raise SystemExit(f"sieve init: {root} is not a directory")
    packs = [p.strip() for p in args.pack.split(",") if p.strip()]
    for p in packs:
        if not os.path.isdir(os.path.join(repo_root(), "packs", p)):
            raise SystemExit(f"sieve init: unknown pack {p!r} (available: web3, web, binary)")
    cfg = load_config()
    passes = args.passes or int(cfg.get("audit.passes", 3))
    eng = Engagement.create(root, packs, name=args.name, passes=passes, mode=args.mode)
    card = CASE_TEMPLATE.format(name=eng.load()["name"], packs=json.dumps(packs))
    if args.lab:
        card = card.replace("lab: false", "lab: true")
    util.atomic_write(eng.case_path(), card)
    util.atomic_write(eng.path("assumptions.md"),
                      "# Assumptions\n\nEvery judgement call made without asking is recorded here.\n\n")
    util.atomic_write(eng.path("plan.md"), f"# Plan — {eng.load()['name']}\n\n")
    if not args.quiet:
        print_banner()
    print(f"engagement {eng.load()['id']} created in {eng.dir}")
    print(f"packs: {', '.join(packs)}   passes: {passes}   mode: {args.mode}")
    head, detail = next_action(eng)
    print(f"NEXT: {head} — {detail}")
    return 0


def _phase_gate(eng: Engagement, target: str, force: bool, reason: str) -> None:
    """Refuse phase jumps that skip mandatory work. --force records a waiver instead."""
    st = eng.load()
    problems: List[str] = []
    fs = frontier.stats(eng)
    if target == "xray":
        f = Fence.load(eng)
        if f is None or not any((f.scope.get(k) for k in ("hosts", "urls", "contracts", "paths", "binaries"))):
            problems.append("scope card (.sieve/case.md) lists nothing in scope")
    elif target == "prime":
        for n in ("x-ray.md", "entry-points.md", "invariants.md", "architecture.json"):
            if not os.path.isfile(eng.path("xray", n)):
                problems.append(f"xray/{n} is missing")
        if fs["total"] == 0:
            problems.append("frontier is empty (`sieve frontier seed`)")
    elif target == "hunt":
        try:
            if os.path.getsize(eng.path("plan.md")) < 200:
                problems.append("plan.md is empty: write the ranked hit list first")
        except OSError:
            problems.append("plan.md is missing")
    elif target == "converge":
        if int(st.get("pass_current") or 0) < 1:
            problems.append("no hunt pass has run")
        if st.get("pass_step") not in ("merge", "done"):
            problems.append(f"pass {st.get('pass_current')} is not merged (step: {st.get('pass_step') or 'start'})")
    elif target == "gate":
        if fs["open"] > 0:
            problems.append(f"{fs['open']} frontier row(s) still open")
    elif target == "prove":
        from .flow import _unjudged
        if _unjudged(eng):
            problems.append("candidates not yet judged: " + ", ".join(_unjudged(eng)[:6]))
    elif target == "report":
        from .flow import _unproven
        if _unproven(eng):
            problems.append("C/H/M findings without a proof receipt: " + ", ".join(_unproven(eng)[:6]))
    if problems and not force:
        raise SystemExit("sieve phase: cannot enter %r yet:\n  - %s\n(`--force --reason \"...\"` records a waiver "
                         "that the report prints as coverage debt)" % (target, "\n  - ".join(problems)))
    if problems and force:
        if len(reason.strip()) < 12:
            raise SystemExit("sieve phase: --force needs --reason (>= 12 chars) explaining the waiver")
        _waive(eng, target, "; ".join(problems) + " — " + reason.strip())
        print("WAIVED: " + "; ".join(problems))


def cmd_phase(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    if args.name == "done":
        raise SystemExit("sieve phase: use `sieve finish` to complete an engagement")
    if args.name not in PHASES:
        raise SystemExit(f"sieve phase: valid phases: {', '.join(PHASES)}")
    _phase_gate(eng, args.name, args.force, args.reason or "")
    eng.set_phase(args.name)
    head, detail = next_action(eng)
    print(f"phase -> {args.name}\nNEXT: {head} — {detail}")
    return 0


def cmd_pass(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    cfg = load_config(eng.root)
    cur = int(eng.load().get("pass_current") or 0)
    if args.n != cur + 1:
        raise SystemExit(f"sieve pass: passes are sequential; the next pass is {cur + 1}")
    if args.n > int(cfg.get("audit.max_passes", 10)):
        raise SystemExit("sieve pass: max_passes reached")
    if eng.load().get("phase") != "hunt":
        raise SystemExit("sieve pass: enter the hunt phase first (`sieve phase hunt`)")

    def fn(st: Dict[str, Any]) -> None:
        st["pass_current"] = args.n
        st["pass_step"] = "bundle"
        st["passes_planned"] = max(int(st.get("passes_planned") or 1), args.n)
    eng.update(fn)
    os.makedirs(eng.path("raw", f"pass-{args.n}"), exist_ok=True)
    print(f"pass {args.n} started. NEXT: `sieve bundle --all`")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    d = status_dict(eng)
    if args.json:
        print(json.dumps(d, indent=2))
        return 0
    fs = d["frontier"]
    print(f"{d['id']}  {d['name']}  packs={','.join(d['packs'])}")
    print(f"phase={d['phase']}  pass={d['pass']}  step={d['pass_step'] or '-'}  elapsed={d['elapsed_min']}m")
    print(f"frontier: {fs['open']} open / {fs['total']} total ({fs['closed_pct']}% closed)  "
          f"done={fs['by_status']['done']} dead={fs['by_status']['dead']} blocked={fs['by_status']['blocked']}")
    print(f"findings files: {d['findings_files']}")
    hk = d["hook"]
    print(f"stop hook: {hk['calls']} call(s), {hk['blocks']} block(s), {hk['no_progress']} no-progress"
          + ("   (never fired: run `sieve hooks status`)" if hk["calls"] == 0 else ""))
    if d["halt_reason"]:
        print(f"HALTED: {d['halt_reason']}")
    print(f"NEXT: {d['next']} — {d['next_detail']}")
    return 0


def cmd_ladder(args: argparse.Namespace) -> int:
    print("The stuck ladder — climb before you close anything:\n")
    for i, (k, v) in enumerate(frontier.LADDER.items(), 1):
        print(f"  {i}. {k:<13} {v}")
    print("\nA dead end needs >=3 logged attempts on >=3 different rungs. "
          "A clean claim needs >=2 attempts including `inversion`.")
    return 0


def cmd_frontier(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    cfg = load_config(eng.root)
    a = args.fcmd
    if a == "add":
        rid = frontier.add(eng, args.kind, args.component, pack=args.pack, lens=args.lens,
                           source=args.source, prio=args.prio, note=args.note)
        print(rid)
    elif a == "list":
        rows = frontier.load(eng)
        if args.status:
            rows = [r for r in rows if r["status"] == args.status]
        if args.lens:
            rows = [r for r in rows if r["lens"] in ("*", args.lens)]
        _print_table(rows, ["id", "kind", "component", "lens", "status", "prio", "attempts"])
    elif a == "next":
        _print_table(frontier.next_rows(eng, lens=args.lens, n=args.n),
                     ["id", "kind", "component", "lens", "prio", "attempts", "note"])
    elif a == "attempt":
        n = frontier.attempt(eng, args.id, args.rung, args.note)
        print(f"{args.id}: {n} attempt(s) logged")
    elif a == "done":
        if args.finding:
            frontier.done_finding(eng, args.id, args.finding)
        elif args.clean:
            frontier.done_clean(eng, args.id, args.clean, cfg)
        else:
            raise SystemExit("sieve frontier done: pass --finding <id> or --clean \"why it holds\"")
        print(f"{args.id}: done")
    elif a == "dead":
        tries: List[Tuple[str, str]] = []
        for t in args.try_ or []:
            if ":" not in t:
                raise SystemExit("sieve frontier dead: --try RUNG:\"what you tried\"")
            r, n = t.split(":", 1)
            tries.append((r.strip(), n.strip()))
        frontier.dead(eng, args.id, tries, cfg)
        print(f"{args.id}: dead (receipt recorded)")
    elif a == "block":
        frontier.block(eng, args.id, args.reason, args.note)
        print(f"{args.id}: blocked ({args.reason})")
    elif a == "reopen":
        frontier.reopen(eng, args.id, args.note or "reopened")
        print(f"{args.id}: reopened")
    elif a == "stats":
        print(json.dumps(frontier.stats(eng), indent=2))
    return 0


def cmd_halt(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    if args.reason not in ("scope", "credentials", "irreversible"):
        raise SystemExit("sieve halt: only scope | credentials | irreversible justify stopping to ask a human")
    if len(args.note.strip()) < 20:
        raise SystemExit("sieve halt: --note must state the exact question or missing item (>= 20 chars)")

    def fn(st: Dict[str, Any]) -> None:
        st["halt_reason"] = f"needs human ({args.reason}): {args.note.strip()}"
    eng.update(fn)
    print("halted. State the question to the user, then wait. Resume with `sieve continue`.")
    return 0


def cmd_continue(args: argparse.Namespace) -> int:
    eng = Engagement.require()

    def fn(st: Dict[str, Any]) -> None:
        st["halt_reason"] = None
        st["counters"]["blocks_no_progress"] = 0
        st["counters"]["blocks_total"] = 0
        st["started_epoch"] = time.time() - min(60 * 30, (time.time() - float(st["started_epoch"])))
    eng.update(fn)
    head, detail = next_action(eng)
    print(f"resumed.\nNEXT: {head} — {detail}")
    return 0


def cmd_fence(args: argparse.Namespace) -> int:
    fence = Fence.load()
    if fence is None:
        print("BLOCKED: no scope card (.sieve/case.md)")
        return 2
    t = args.what
    if args.kind == "host":
        ok, why = fence.check_url(t)
    elif args.kind == "contract":
        ok, why = fence.check_contract(args.chain or "", t)
    else:
        ok, why = fence.check_path(t, Engagement.require().root)
    print(("IN SCOPE: " if ok else "BLOCKED: ") + why)
    if ok and args.kind == "host" and not fence.active_testing and not fence.lab:
        print("note: rules.active_testing is false — passive observation only")
    return 0 if ok else 2


def cmd_hook(args: argparse.Namespace) -> int:
    if args.event == "stop":
        return hooklib.main_stop()
    return 0


def cmd_hooks(args: argparse.Namespace) -> int:
    if args.hcmd == "install":
        sieve_bin = os.path.join(repo_root(), "bin", "sieve")
        print(hooklib.install(args.scope, sieve_bin, dry_run=args.dry_run))
    else:
        found = hooklib.installed()
        print(f"Stop hook registered — user: {found['user']}  project: {found['project']}")
        eng = Engagement.find()
        if eng:
            c = eng.load()["counters"]
            print(f"heartbeat in this engagement: {c.get('hook_calls', 0)} call(s)"
                  + (" (the hook has never fired here)" if not c.get("hook_calls") else ""))
        if not any(found.values()):
            print("Install with: sieve hooks install --scope user   (skill frontmatter also registers it while the skill is active)")
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    fs = frontier.stats(eng)
    problems: List[str] = []
    if fs["open"] > 0:
        problems.append(f"{fs['open']} frontier row(s) still open")
    if not os.path.isfile(eng.path("report", "report.md")):
        problems.append("no report assembled (`sieve report`)")
    if not os.path.isfile(eng.path("xray", "architecture.svg")):
        problems.append("no map (`sieve map`)")
    if problems and not args.force:
        raise SystemExit("sieve finish: not finished:\n  - " + "\n  - ".join(problems))
    if problems and args.force:
        if len((args.reason or "").strip()) < 12:
            raise SystemExit("sieve finish: --force needs --reason")
        _waive(eng, "done", "; ".join(problems) + " — " + args.reason)
    eng.set_phase("done")
    print("engagement finished.")
    return 0


# ------------------------------------------------------------------ registration

def register(sub: Any) -> None:
    p = sub.add_parser("banner", help="print the SIEVE banner")
    p.add_argument("--color", action="store_true")
    p.set_defaults(func=cmd_banner)

    p = sub.add_parser("home", help="print the skill home directory")
    p.set_defaults(func=cmd_home)

    p = sub.add_parser("init", help="create an engagement in a target directory")
    p.add_argument("target", nargs="?", default=".")
    p.add_argument("--pack", required=True, help="comma list of: web3, web, binary")
    p.add_argument("--name")
    p.add_argument("--passes", type=int)
    p.add_argument("--mode", choices=["deep", "quick", "focus"], default="deep")
    p.add_argument("--lab", action="store_true", help="local/lab target you own (allows localhost)")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("phase", help="advance the engagement phase (gated)")
    p.add_argument("name")
    p.add_argument("--force", action="store_true")
    p.add_argument("--reason")
    p.set_defaults(func=cmd_phase)

    p = sub.add_parser("pass", help="start hunt pass N")
    p.add_argument("n", type=int)
    p.set_defaults(func=cmd_pass)

    p = sub.add_parser("status", help="where are we, and what is the next step")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("ladder", help="print the stuck ladder")
    p.set_defaults(func=cmd_ladder)

    p = sub.add_parser("frontier", help="the work queue")
    fs = p.add_subparsers(dest="fcmd", required=True)
    q = fs.add_parser("add")
    q.add_argument("kind")
    q.add_argument("component")
    q.add_argument("--pack", default="")
    q.add_argument("--lens", default="*")
    q.add_argument("--source", default="manual")
    q.add_argument("--prio", type=int, default=3)
    q.add_argument("--note", default="")
    q = fs.add_parser("list")
    q.add_argument("--status")
    q.add_argument("--lens")
    q = fs.add_parser("next")
    q.add_argument("--lens")
    q.add_argument("-n", type=int, default=5)
    q = fs.add_parser("attempt")
    q.add_argument("id")
    q.add_argument("--rung", required=True, choices=list(frontier.LADDER))
    q.add_argument("--note", required=True)
    q = fs.add_parser("done")
    q.add_argument("id")
    q.add_argument("--finding")
    q.add_argument("--clean")
    q = fs.add_parser("dead")
    q.add_argument("id")
    q.add_argument("--try", dest="try_", action="append", help='RUNG:"what you tried" (repeatable)')
    q = fs.add_parser("block")
    q.add_argument("id")
    q.add_argument("--reason", required=True)
    q.add_argument("--note", required=True)
    q = fs.add_parser("reopen")
    q.add_argument("id")
    q.add_argument("--note")
    fs.add_parser("stats")
    p.set_defaults(func=cmd_frontier)

    p = sub.add_parser("halt", help="stop honestly to ask a human (scope|credentials|irreversible)")
    p.add_argument("--reason", required=True)
    p.add_argument("--note", required=True)
    p.set_defaults(func=cmd_halt)

    p = sub.add_parser("continue", help="resume after a halt")
    p.set_defaults(func=cmd_continue)

    p = sub.add_parser("fence", help="is this in scope?")
    p.add_argument("kind", choices=["host", "contract", "path"])
    p.add_argument("what")
    p.add_argument("--chain")
    p.set_defaults(func=cmd_fence)

    p = sub.add_parser("hook", help="harness hook entry points")
    p.add_argument("event", choices=["stop"])
    p.set_defaults(func=cmd_hook)

    p = sub.add_parser("hooks", help="install / inspect the Stop hook")
    hs = p.add_subparsers(dest="hcmd", required=True)
    q = hs.add_parser("install")
    q.add_argument("--scope", choices=["user", "project"], default="user")
    q.add_argument("--dry-run", action="store_true")
    hs.add_parser("status")
    p.set_defaults(func=cmd_hooks)

    p = sub.add_parser("finish", help="complete the engagement (requires drained frontier + report)")
    p.add_argument("--force", action="store_true")
    p.add_argument("--reason")
    p.set_defaults(func=cmd_finish)
