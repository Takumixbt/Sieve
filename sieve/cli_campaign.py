"""`sieve campaign ...` — drive the topology-based static-analysis campaign (see `campaign.py`).

    init      copy the topology + prompts into .sieve/campaign/, expand it for the profile, write state
    status    every node, its status, what it waits on
    run       execute ready mechanical nodes; validate and accept finished agent artifacts; advance
    next      render prompts for ready agent nodes and print how to dispatch them
    submit    validate a node's artifact against its contract and mark it done (or send back the errors)
    retry / skip / reset      recover a failed node, waive one on the record, or re-run a node and what depends on it
    dashboard loopback web dashboard (or a static snapshot with --once)
    schema    print an artifact contract (what an agent must write)
    validate  lint a topology
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any, Dict, List

from . import campaign as C
from . import campaign_actions as A
from . import campaign_rules, campaign_schema as schema, dashboard, pipeline, util
from .cli_core import _waive
from .state import Engagement


class _StubEng:
    """Just enough of an Engagement to expand a topology for linting (`sieve lint`, `campaign validate`)."""

    def __init__(self, packs: List[str]):
        self._st = {"packs": packs, "mode": "deep", "id": "lint", "name": "lint"}
        self.root = "."
        self.dir = "."

    def load(self) -> Dict[str, Any]:
        return self._st

    def path(self, *parts: str) -> str:
        return os.path.join(self.dir, *parts)


def lint_default_topology() -> List[str]:
    """Used by `sieve lint`: the shipped topology expands and validates for every profile, every prompt exists,
    every rule compiles, and every contract's own example satisfies it."""
    errs: List[str] = []
    path = C.default_topology()
    if not os.path.isfile(path):
        return [f"missing {path}"]
    topo = C.load_topology(path)
    for prof in (topo.get("profiles") or {}):
        try:
            nodes = C.expand(topo, _StubEng(["web3", "web", "binary"]), prof)  # type: ignore[arg-type]
        except SystemExit as exc:
            errs.append(f"campaign.yml [{prof}]: {exc}")
            continue
        errs += [f"campaign.yml [{prof}]: {e}" for e in C.validate_topology(nodes)]
        for n in nodes:
            if n.get("prompt") and not os.path.isfile(os.path.join(os.path.dirname(path), "prompts", n["prompt"])):
                errs.append(f"campaign.yml [{prof}]: node {n['id']} needs prompt {n['prompt']}, which does not exist")
            if n["kind"] == "meta" and n.get("action") not in A.ACTIONS:
                errs.append(f"campaign.yml [{prof}]: node {n['id']} uses unknown meta action {n.get('action')!r}")
            if n["kind"] == "reference" and not os.path.isfile(os.path.join(os.path.dirname(path), os.pardir, n["file"])):
                errs.append(f"campaign.yml [{prof}]: reference {n['id']} points at missing {n['file']}")
    for name, c in schema.CONTRACTS.items():
        bad = schema.validate_json(name, c["example"])
        if bad:
            errs.append(f"campaign_schema {name}: its own example fails: {bad[0]}")
    rules = campaign_rules.load_rules(_StubEng([]))  # type: ignore[arg-type]
    errs += campaign_rules.lint_rules(rules)
    return errs


def _load(args: argparse.Namespace, allow_drift: bool = False):
    eng = Engagement.require()
    topo, nodes, st = C.load(eng, allow_drift=allow_drift)
    return eng, topo, nodes, st


def _next(eng: Engagement) -> None:
    head, detail = C.next_action(eng)
    print(f"NEXT: {head} — {detail}")


def cmd_init(args: argparse.Namespace) -> int:
    from . import scan as scanlib
    eng = Engagement.require()
    profile = args.profile
    if profile is None:
        profile = (scanlib.read_scan(eng).get("metrics") or {}).get("recommended") or "default"
        print(f"profile: {profile} ({'recommended by `sieve scan`' if scanlib.read_scan(eng) else 'the default'}; override with --profile)")
    nodes, st = C.init(eng, profile, args.topology, force=args.force, resume=args.resume)
    kinds: Dict[str, int] = {}
    for n in nodes:
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
    print(f"campaign initialised — profile {st['profile']}: {len(nodes)} node(s) "
          + "(" + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())) + ")")
    agentic = kinds.get("agentic", 0)
    print(f"cost: {agentic} agent run(s) to dispatch; the {kinds.get('meta', 0)} mechanical step(s) are run by the engine")
    print("topology: .sieve/campaign/topology.yml   prompts: .sieve/campaign/prompts/  (both editable)")
    _next(eng)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    if args.topology:
        topo = C.load_topology(args.topology)
        bad: List[str] = []
        for prof in (topo.get("profiles") or {}):
            try:
                nodes = C.expand(topo, _StubEng(["web3", "web", "binary"]), prof)  # type: ignore[arg-type]
                bad += [f"[{prof}] {e}" for e in C.validate_topology(nodes)]
            except SystemExit as exc:
                bad.append(f"[{prof}] {exc}")
    else:
        bad = lint_default_topology()
    for e in bad:
        print("✗ " + e)
    print("campaign topology: " + ("INVALID" if bad else "ok"))
    return 1 if bad else 0


def cmd_status(args: argparse.Namespace) -> int:
    eng, _topo, nodes, st = _load(args, allow_drift=True)
    sts = C.statuses(eng, nodes, st)
    if args.json:
        print(json.dumps({"profile": st["profile"], "nodes": {n["id"]: {"status": sts[n["id"]], "deps": n["depends_on"],
                                                                         "attempts": st["nodes"][n["id"]]["attempts"]} for n in nodes}}, indent=2))
        return 0
    counts: Dict[str, int] = {}
    for v in sts.values():
        counts[v] = counts.get(v, 0) + 1
    print(f"campaign · profile {st['profile']} · " + " · ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    show = [n for n in nodes if args.all or sts[n["id"]] not in ("done", "skipped")]
    print(f"\n{'NODE':<46} {'KIND':<9} {'STATUS':<8} TRY  DETAIL")
    for n in show:
        ns = st["nodes"][n["id"]]
        detail = ns.get("error") or ns.get("note") or ""
        waits = [d for d in n["depends_on"] if sts[d] not in ("done", "skipped")]
        if sts[n["id"]] == "pending" and waits:
            detail = "waits on " + ", ".join(waits[:3]) + ("…" if len(waits) > 3 else "")
        print(f"{n['id']:<46} {n['kind']:<9} {sts[n['id']]:<8} {ns.get('attempts', 0):<4} {str(detail)[:90]}")
    hidden = len(nodes) - len(show)
    if hidden:
        print(f"({hidden} done node(s) hidden — `sieve campaign status --all`)")
    print()
    _next(eng)
    return 0


def _save_waiting(eng: Engagement, ids: List[str]) -> None:
    def fn(s: Dict[str, Any]) -> None:
        s["waiting"] = {"since": time.time(), "nodes": ids} if ids else None
    eng.update(fn)


def cmd_next(args: argparse.Namespace) -> int:
    eng, _topo, nodes, st = _load(args)
    by = {n["id"]: n for n in nodes}
    sts = C.statuses(eng, nodes, st)
    ready = [n for n in nodes if sts[n["id"]] == "ready" and n["kind"] == "agentic"]
    if args.only:
        ready = [n for n in ready if n["id"] in args.only]
    if not ready:
        running = [n["id"] for n in nodes if sts[n["id"]] == "running"]
        print("no agent node is ready." + (f" Running: {', '.join(running)}." if running else ""))
        _next(eng)
        return 0
    print(f"{len(ready)} agent node(s) ready — spawn ALL of them now, in ONE message, as background calls:\n")
    for n in ready:
        if n.get("builder") == "bundle":
            A._ensure_pass(eng, int(n["vars"].get("loop", 1)))
        path, lines = C.render_prompt(eng, n, nodes, st["profile"])
        C.mark_running(eng, st, n, by)
        rel = os.path.relpath(path, eng.root)
        outs = ", ".join(o["path"] for o in n["outputs"])
        print(f"── {n['id']}   prompt: {rel} ({lines} lines)   writes: .sieve/{outs}")
        if n.get("builder"):
            print("   " + util.read_text(path).split("\n", 3)[-1].strip().split("\n")[0])
        else:
            print(f"   Read `{rel}` ({lines} lines) in full and do exactly what it says. Write the artifact(s) it names, "
                  f"then run `sieve campaign submit {n['id']}`.")
        print()
    C.save(eng, st)
    _save_waiting(eng, [n["id"] for n in ready])
    print("Waiting state set (the Stop hook idles while they run). Do not poll. When they return: `sieve campaign run`.")
    return 0


def _try_accept(eng: Engagement, node: Dict[str, Any], st: Dict[str, Any], accept: str = "", explicit: bool = False) -> bool:
    ok, errs = A.submit(eng, node, accept=accept or None)
    ns = st["nodes"][node["id"]]
    if ok:
        C.mark_done(eng, st, node, "artifact validated")
        return True
    ns["error"] = "; ".join(errs)[:1500]
    if explicit:
        ns["submit_failures"] = int(ns.get("submit_failures", 0)) + 1
        C.event(eng, node["id"], "rejected", "; ".join(errs)[:300])
        if ns["submit_failures"] >= 3:
            C.mark_failed(eng, st, node, "artifact rejected 3 times: " + ns["error"])
    return False


def cmd_submit(args: argparse.Namespace) -> int:
    eng, _topo, nodes, st = _load(args)
    node = next((n for n in nodes if n["id"] == args.node), None)
    if node is None:
        raise SystemExit(f"sieve campaign: no node {args.node!r} (`sieve campaign status --all`)")
    if node["kind"] != "agentic":
        raise SystemExit(f"sieve campaign: {node['id']} is a {node['kind']} node — the engine runs it (`sieve campaign run`)")
    sts = C.statuses(eng, nodes, st)
    if sts[node["id"]] in ("pending", "blocked"):
        raise SystemExit(f"sieve campaign: {node['id']} is not ready — it waits on its dependencies (`sieve campaign status`)")
    if sts[node["id"]] == "ready":
        C.mark_running(eng, st, node, {n["id"]: n for n in nodes})
    if _try_accept(eng, node, st, accept=args.accept or "", explicit=True):
        print(f"{node['id']}: accepted — artifact satisfies its contract.")
        if not any(v == "running" for k, v in C.statuses(eng, nodes, st).items()):
            _save_waiting(eng, [])
        C.save(eng, st)
        _next(eng)
        return 0
    C.save(eng, st)
    print(f"{node['id']}: REJECTED ({st['nodes'][node['id']].get('submit_failures', 0)}/3) — fix these and submit again:")
    for e in st["nodes"][node["id"]]["error"].split("; "):
        print("  ✗ " + e)
    if st["nodes"][node["id"]]["status"] == "failed":
        print("Rejected three times: the node is now failed. Fix the cause, then `sieve campaign retry " + node["id"] + "`.")
    return 1


def cmd_run(args: argparse.Namespace) -> int:
    eng, _topo, nodes, st = _load(args)
    by = {n["id"]: n for n in nodes}
    order = {n["id"]: i for i, n in enumerate(nodes)}
    ran = 0
    for _ in range(1000):
        sts = C.statuses(eng, nodes, st)
        if args.rerun_stale:
            stale = [n["id"] for n in nodes if sts[n["id"]] == "stale"]
            if stale:
                for s in stale:
                    C.reset_node(eng, st, nodes, s, cascade=True)
                print(f"re-opened {len(stale)} stale node(s) and everything downstream of them")
                C.save(eng, st)
                continue
        progressed = False
        for n in nodes:                                   # accept finished agent artifacts
            if sts[n["id"]] == "running" and n["kind"] == "agentic":
                if n.get("check") in ("rollcall", "rollcall-roaming"):
                    from . import blocks as B
                    p = eng.path(n["outputs"][0]["path"])
                    loop = int(n["vars"].get("loop") or eng.load().get("pass_current") or 1)
                    slug = "roaming" if n.get("check") == "rollcall-roaming" else n["vars"].get("slug")
                    done = os.path.isfile(p) and B.done_marker(util.read_text(p))
                    if not (done and done["agent"] == slug and done["pass"] == loop):
                        if os.path.isfile(p):
                            print(f"  … {n['id']}: output file exists but has no `SIEVE-AGENT-DONE {slug} pass {loop}` line — "
                                  f"still being written, or the agent crashed (a wrong pass number in that line counts as missing)")
                        continue                          # still writing (no DONE line yet)
                elif not all(os.path.exists(eng.path(o["path"])) for o in n["outputs"]) and n.get("check") != "frontier-drained":
                    continue
                if _try_accept(eng, n, st):
                    print(f"  ✓ {n['id']}: artifact validated")
                    progressed = True
                else:
                    print(f"  … {n['id']}: artifact present but not acceptable yet — {st['nodes'][n['id']]['error'][:200]}")
        if progressed:
            C.save(eng, st)
            continue
        sts = C.statuses(eng, nodes, st)
        ready_meta = sorted([n for n in nodes if sts[n["id"]] == "ready" and n["kind"] == "meta"], key=lambda n: order[n["id"]])
        if not ready_meta:
            break
        n = ready_meta[0]
        C.mark_running(eng, st, n, by)
        ok, msg = A.run_meta(eng, n, nodes)
        if ok and n["outputs"] and not all(os.path.exists(eng.path(o["path"])) for o in n["outputs"]):
            ok, msg = False, msg + " — but its declared output is missing"
        if ok:
            C.mark_done(eng, st, n, msg)
            print(f"  ✓ {n['id']}: {msg[:220]}")
        else:
            C.mark_failed(eng, st, n, msg)
            print(f"  ✗ {n['id']}: {msg[:400]}")
        C.save(eng, st)
        ran += 1
    if not any(v == "running" for v in C.statuses(eng, nodes, st).values()):
        _save_waiting(eng, [])
    C.save(eng, st)
    print()
    _next(eng)
    return 1 if any(v == "failed" for v in C.statuses(eng, nodes, st).values()) else 0


def cmd_retry(args: argparse.Namespace) -> int:
    eng, _topo, nodes, st = _load(args)
    if args.node not in st["nodes"]:
        raise SystemExit(f"sieve campaign: no node {args.node!r}")
    ns = st["nodes"][args.node]
    ns.update(status="pending", error=None, submit_failures=0)
    C.event(eng, args.node, "retry")
    C.save(eng, st)
    print(f"{args.node}: reset to pending")
    _next(eng)
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    eng, _topo, nodes, st = _load(args)
    if args.node not in st["nodes"]:
        raise SystemExit(f"sieve campaign: no node {args.node!r}")
    ids = C.reset_node(eng, st, nodes, args.node, cascade=not args.only_this)
    C.save(eng, st)
    print(f"reset {len(ids)} node(s): {', '.join(ids[:6])}{'…' if len(ids) > 6 else ''}")
    _next(eng)
    return 0


def cmd_skip(args: argparse.Namespace) -> int:
    eng, _topo, nodes, st = _load(args)
    if args.node not in st["nodes"]:
        raise SystemExit(f"sieve campaign: no node {args.node!r}")
    if len((args.reason or "").strip()) < 12:
        raise SystemExit("sieve campaign skip: --reason needs a real explanation (>= 12 chars); it is printed in the report")
    st["nodes"][args.node].update(status="skipped", error=None, finished=util.now_iso(), note="skipped: " + args.reason.strip())
    _waive(eng, "campaign", f"node {args.node} skipped — {args.reason.strip()}")
    C.event(eng, args.node, "skipped", args.reason)
    C.save(eng, st)
    print(f"{args.node}: skipped (recorded as coverage debt)")
    _next(eng)
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    if args.once:
        out = C.cdir(eng, "dashboard.html")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        util.atomic_write(out, dashboard.static_html(dashboard.snapshot(eng)))
        print(f"wrote {out} (static snapshot; open it in a browser)")
        return 0
    dashboard.run_forever(eng, args.port)
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    if not args.name:
        for n in schema.known():
            doc = schema.CONTRACTS.get(n, schema.MARKDOWN.get(n, {})).get("doc", "")
            print(f"{n:<26} {doc}")
        return 0
    if args.name not in schema.known():
        raise SystemExit(f"sieve campaign schema: unknown contract; known: {', '.join(schema.known())}")
    print(schema.describe(args.name))
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("campaign", help="topology-driven static-analysis campaign (ultrafuzz-shaped)")
    cs = p.add_subparsers(dest="ccmd", required=True)
    q = cs.add_parser("init", help="create the campaign for this engagement")
    q.add_argument("--profile", default=None, type=lambda v: {"smoke": "lite"}.get(v, v),
                   choices=["lite", "default", "exhaustive"],
                   help="depth: lite | default | exhaustive (default: what `sieve scan` recommended, else default)")
    q.add_argument("--topology", help="use this topology file instead of the shipped one")
    q.add_argument("--resume", action="store_true", help="adopt an edited topology, keeping finished nodes")
    q.add_argument("--force", action="store_true", help="start over")
    q.set_defaults(func=cmd_init)
    q = cs.add_parser("validate", help="lint a topology (default: the shipped one, every profile)")
    q.add_argument("--topology")
    q.set_defaults(func=cmd_validate)
    q = cs.add_parser("status", help="nodes, statuses, what each waits on")
    q.add_argument("--all", action="store_true")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_status)
    q = cs.add_parser("run", help="execute ready mechanical nodes, accept finished agent artifacts, advance")
    q.add_argument("--rerun-stale", action="store_true", help="re-open nodes whose upstream artifacts changed")
    q.set_defaults(func=cmd_run)
    q = cs.add_parser("next", help="render prompts for ready agent nodes and print how to dispatch them")
    q.add_argument("--only", action="append", help="restrict to this node id (repeatable)")
    q.set_defaults(func=cmd_next)
    q = cs.add_parser("submit", help="validate a node's artifact against its contract")
    q.add_argument("node")
    q.add_argument("--accept", help="accept a below-contract hunt agent as recorded coverage debt (reason)")
    q.set_defaults(func=cmd_submit)
    q = cs.add_parser("retry")
    q.add_argument("node")
    q.set_defaults(func=cmd_retry)
    q = cs.add_parser("reset", help="re-run a node and everything downstream of it")
    q.add_argument("node")
    q.add_argument("--only-this", action="store_true")
    q.set_defaults(func=cmd_reset)
    q = cs.add_parser("skip", help="waive a node on the record (printed as coverage debt)")
    q.add_argument("node")
    q.add_argument("--reason", required=True)
    q.set_defaults(func=cmd_skip)
    q = cs.add_parser("dashboard", help="loopback web dashboard (127.0.0.1 only)")
    q.add_argument("--port", type=int, default=8787)
    q.add_argument("--once", action="store_true", help="write a static snapshot instead of serving")
    q.set_defaults(func=cmd_dashboard)
    q = cs.add_parser("schema", help="print an artifact contract")
    q.add_argument("name", nargs="?")
    q.set_defaults(func=cmd_schema)
