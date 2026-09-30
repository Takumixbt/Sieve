"""Meta-node actions and artifact submission for the campaign engine.

Meta actions are the mechanical work a campaign does itself: run the x-ray and the static rules, render
upstream artifacts into the files the classic bundles read, seed the frontier, merge and absorb a hunt loop,
run the deterministic reportability gate, execute proofs, assemble the report. Every one is a thin call into
code that already exists (`pipeline`, `merge`, `validate`, `judging`, `report`) — the campaign adds ordering
and refusal, not a second implementation.

`submit()` is the acceptance test for an agentic node: its output must exist, pass its contract
(`campaign_schema`) and any semantic check the topology names, before the node counts as done.
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import os
import re
import statistics
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import blocks as B
from . import campaign as C
from . import campaign_rules
from . import campaign_schema as schema
from . import cites as citelib
from . import frontier, judging, pipeline, report, repo_root, util, validate, xray_git, xray_web, xray_web3
from . import merge as mergelib
from .cli_core import _phase_gate, _waive
from .fence import Fence
from .state import Engagement

Result = Tuple[bool, str]
_OBS = "# Live-browser observation\n\n"


def _cli(*argv: str) -> Tuple[int, str]:
    """Run a `sieve` subcommand in-process and capture what it printed."""
    from .main import main
    buf = io.StringIO()
    rc = 0
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rc = main(list(argv))
        except SystemExit as exc:
            rc = 1
            if exc.code not in (None, 0):
                print(str(exc.code))
    return int(rc or 0), buf.getvalue().strip()


def _artifact(eng: Engagement, nodes: List[Dict[str, Any]], spec: str) -> List[str]:
    """Paths of every primary artifact produced by all nodes of a spec."""
    out: List[str] = []
    for n in nodes:
        if n["spec"] == spec:
            for o in n["outputs"]:
                if o["primary"] and os.path.isfile(eng.path(o["path"])):
                    out.append(eng.path(o["path"]))
    return out


def _json(path: str) -> Any:
    return util.read_json(path, None)


# ---------------------------------------------------------------------------- meta actions

def act_phase(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    target = str(node.get("arg") or "")
    if eng.load().get("phase") == target:
        return True, f"already in phase {target}"
    if target == "report":
        # Unvalidated candidates ship in the report's own "Unvalidated" section — they never print as confirmed —
        # so they must not stall the campaign. Tampering and stale proofs still stop it: those need a human.
        blockers = validate.blockers(eng)
        hard = [b for b in blockers if b.startswith("TAMPER") or "STALE" in b or "tampered" in b]
        if hard:
            return False, "cannot enter report:\n  - " + "\n  - ".join(hard)
        if blockers:
            _waive(eng, "report", "; ".join(blockers)[:600] + " — shipped in the report's Unvalidated section, not as findings")
        eng.set_phase(target)
        return True, f"phase -> report ({len(blockers)} unvalidated candidate(s) recorded as coverage debt)"
    try:
        _phase_gate(eng, target, False, "")
    except SystemExit as exc:
        return False, str(exc)
    eng.set_phase(target)
    return True, f"phase -> {target}"


def act_xray(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]], reuse: bool = True) -> Result:
    from . import scan as scanlib
    if reuse and scanlib.fresh(eng, "xray") and os.path.isfile(eng.path("xray", "facts.json")):
        return True, "reused the `sieve scan` x-ray (source tree unchanged since the scan)"
    st = eng.load()
    msgs: List[str] = []
    facts_path = eng.path("xray", "facts.json")
    os.makedirs(eng.path("xray"), exist_ok=True)
    facts = util.read_json(facts_path, {}) or {}
    if "web3" in st["packs"]:
        f = xray_web3.run(eng.root, auto_static=True)
        facts["web3"] = f
        msgs.append(f"web3: {len(f['files'])} file(s), {f['nsloc_total']} nSLOC, {len(f['entry_candidates'])} entry candidate(s), "
                    f"{len(f['tool_leads'])} tool lead(s); static tools auto-ran: {', '.join(f['auto_ran']) or 'none'}")
    if "web" in st["packs"]:
        inp = eng.path("inputs")
        openapi = [p for p in glob.glob(os.path.join(inp, "openapi*")) + glob.glob(os.path.join(inp, "swagger*"))]
        har = glob.glob(os.path.join(inp, "*.har"))
        urls = glob.glob(os.path.join(inp, "urls*.txt"))
        f = xray_web.run(openapi=openapi, har=har, url_lists=urls)
        facts["web"] = f
        h, rows = xray_web.surface_tsv(f)
        util.write_tsv(eng.path("xray", "surface.tsv"), h, rows)
        msgs.append(f"web: {f['counts']['endpoints']} endpoint(s) from {len(openapi) + len(har) + len(urls)} recon input(s) "
                    f"in .sieve/inputs/" + ("" if rows else " — none supplied; the recon agent maps the surface in the hunt"))
    util.write_json(facts_path, facts)
    if os.path.isdir(os.path.join(eng.root, ".git")):
        util.write_json(eng.path("xray", "git-security.json"), xray_git.analyze(eng.root, src_dirs=None))
        msgs.append("git-history security pass written")
    return True, "; ".join(msgs) or "nothing to enumerate mechanically (binary targets are triaged by hand)"


def act_rules(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]], reuse: bool = True) -> Result:
    from . import scan as scanlib
    if reuse and scanlib.fresh(eng, "rules") and os.path.isfile(eng.path("xray", "rule-hits.json")):
        return True, "reused the `sieve scan` rule pass (source tree unchanged since the scan)"
    res = campaign_rules.run(eng)
    return True, f"{res['hits']} static rule hit(s) across {res['files']} file(s) from {res['rules']} rule(s) + vector tells"


def act_external_leads(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    from . import leads as leadslib
    res = leadslib.apply(eng)
    if not res["leads"]:
        util.atomic_write(eng.path("xray", "external-leads.md"),
                          "# External leads\n\n_None supplied (no V12 run, no scanner import)._\n")
        return True, "no external leads supplied"
    return True, f"{res['leads']} external lead(s) on record; frontier +{res['added']}"


def act_prime(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    argv = ["kb", "prime"] + (["--offline"] if os.environ.get("SIEVE_OFFLINE") else [])
    rc, out = _cli(*argv)
    if rc != 0:  # precedents are an accelerant; a KB outage must not stall the campaign
        util.atomic_write(eng.path("xray", "precedents.md"), "# Precedents\n\n_(knowledge base unavailable: " + out[:200] + ")_\n")
        return True, "knowledge base unavailable — continuing without precedents (recorded)"
    return True, out.split("\n")[-1][:200]


def act_fuzz_absorb(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    """A broken invariant is a lead and a vacuous one is a harness gap: both become frontier rows the drain must
    close with a receipt. A fuzz run that could not happen is coverage debt on the record, never silence."""
    path = next(iter(_artifact(eng, nodes, "fuzz")), None)
    d = _json(path) or {} if path else {}
    rows: List[Dict[str, Any]] = []
    broken = vacuous = held = 0
    for r in d.get("runs", []):
        res = r.get("result")
        if res == "broken":
            broken += 1
            rows.append({"kind": "fuzz-break", "component": f"{r['invariant_id']} broken by the fuzzer"[:120], "lens": "invariant-agent",
                         "prio": 5, "source": "fuzz", "note": f"replay: {str(r.get('sequence') or r.get('cmd'))[:80]}"})
        elif res == "vacuous":
            vacuous += 1
            rows.append({"kind": "fuzz-gap", "component": f"{r['invariant_id']} harness never reached the code it guards"[:120],
                         "lens": "invariant-agent", "prio": 4, "source": "fuzz", "note": str(r.get("evidence"))[:80]})
        elif res == "held":
            held += 1
        elif res == "error":
            _waive(eng, "fuzz", f"{r['invariant_id']}: fuzz run errored — {str(r.get('evidence'))[:160]}")
    if d.get("status") != "ran":
        if d.get("status") == "tooling-missing":
            _waive(eng, "fuzz", "property fuzzing skipped: " + str(d.get("reason"))[:200])
        return True, f"fuzzing {d.get('status', 'not run')}: {str(d.get('reason', ''))[:120]}"
    added = frontier.add_many(eng, rows)
    return True, f"{held} invariant(s) held, {broken} broken, {vacuous} vacuous; frontier +{added}"


def act_browser(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    """CloakBrowser recon of every in-scope URL. Every URL passes the fence in code before a browser opens; the
    fence's host list is handed to the script so a click cannot navigate the main frame off-scope."""
    import importlib.util
    import subprocess
    import sys
    out = eng.path("xray", "browser-observations.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fence = Fence.load(eng)
    if fence is None:
        return False, "no scope card: refusing to open a browser"
    cfg_path = eng.path("inputs", "browser.json")
    extra = util.read_json(cfg_path, {}) or {}
    urls = [str(u) for u in (fence.scope.get("urls") or [])] + [str(u) for u in extra.get("urls", [])]
    urls += [f"https://{h}" for h in (fence.scope.get("hosts") or []) if "*" not in str(h)]
    urls = list(dict.fromkeys(urls))
    if not urls:
        util.atomic_write(out, _OBS + "_No live URL is in scope (source-only engagement): nothing to observe._\n")
        return True, "no live URL in scope; nothing to observe"
    if not (fence.active_testing or fence.lab):
        util.atomic_write(out, _OBS + "_rules.active_testing is false on the scope card: a browser is active "
                                      "interaction, so none was opened._\n")
        return True, "active_testing is false; no browser opened (passive engagement)"
    if importlib.util.find_spec("cloakbrowser") is None:
        _waive(eng, "web", "browser recon skipped: CloakBrowser is not installed (pip install cloakbrowser)")
        util.atomic_write(out, _OBS + "_CloakBrowser is not installed: live-client recon is coverage debt._\n")
        return True, "CloakBrowser not installed; recorded as coverage debt"
    allow = [str(h) for h in (fence.scope.get("hosts") or [])]
    if fence.lab:
        allow += ["localhost", "127.0.0.1"]
    script = os.path.join(repo_root(), "scripts", "browser-recon.py")
    parts: List[str] = []
    notes: List[str] = []
    for i, url in enumerate(urls, 1):
        ok, why = fence.check_url(url)
        if not ok:
            notes.append(f"{url}: refused by the fence ({why})")
            continue
        dst = eng.path("xray", "browser", f"obs-{i}.md")
        cmd = [sys.executable, script, url, "--out", dst]
        for h in allow:
            cmd += ["--allow-host", h]
        for sel in (extra.get("click") or {}).get(url, []):
            cmd += ["--click", str(sel)]
        proxy = extra.get("proxy")
        if proxy:
            cmd += ["--proxy", str(proxy)]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=int(extra.get("timeout", 240)))
        except subprocess.TimeoutExpired:
            notes.append(f"{url}: timed out")
            continue
        if res.returncode != 0 or not os.path.isfile(dst):
            lines = (res.stderr or res.stdout).strip().splitlines()
            why = next((l.strip() for l in lines if "Error" in l), lines[-1].strip() if lines else "no output")
            notes.append(f"{url}: browser run failed ({why[:200]})")
            continue
        parts.append(util.read_text(dst))
    if not parts:
        _waive(eng, "web", "browser recon produced no observation: " + "; ".join(notes)[:300])
        util.atomic_write(out, _OBS + "_No page could be observed: " + "; ".join(notes) + "_\n")
        return True, "no page observed (" + "; ".join(notes)[:160] + "); recorded as coverage debt"
    sep = "\n\n---\n\n"
    tail = ""
    if notes:
        tail = "\n\n## Not observed\n" + "\n".join(f"- {n}" for n in notes) + "\n"
    util.atomic_write(out, sep.join(parts) + tail)
    return True, f"observed {len(parts)} page(s) through CloakBrowser" + (f"; {len(notes)} skipped" if notes else "")


def _md_list(items: List[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "_(none)_"


def render_artifacts(eng: Engagement, nodes: List[Dict[str, Any]]) -> List[str]:
    """Turn the campaign's JSON artifacts into the markdown files classic bundles inline."""
    wrote: List[str] = []
    tm = next(iter(_artifact(eng, nodes, "threat-model")), None)
    if tm:
        d = _json(tm) or {}
        text = ["# Threat model", "", "## Assets"] + [f"- **{a['name']}** — {a['why_it_matters']}" for a in d.get("assets", [])]
        text += ["", "## Actors"] + [f"- **{a['name']}** ({a['privilege']}) — {a['goal']}" for a in d.get("actors", [])]
        text += ["", "## Trust boundaries"] + [f"- **{b['name']}** ({b['between']}) — {b['controls']}" for b in d.get("trust_boundaries", [])]
        text += ["", "## Attack goals"] + [f"- **{g['id']}** {g['goal']} — actor: {g['actor']}, asset: {g['asset']}" for g in d.get("attack_goals", [])]
        text += ["", "## Assumptions", _md_list(d.get("assumptions", []))]
        util.atomic_write(eng.path("xray", "threat-model.md"), "\n".join(text) + "\n")
        wrote.append("threat-model.md")
    gp = next(iter(_artifact(eng, nodes, "goal-plan")), None)
    if gp:
        d = _json(gp) or {}
        text = ["# Goal plan", ""] + [f"- **{g['id']}** (priority {g['priority']}) {g['statement']} — components: {', '.join(g['components'])}; "
                                     f"first checks: {'; '.join(g['first_checks'])}" for g in sorted(d.get("goals", []), key=lambda g: -g["priority"])]
        text += ["", "## Excluded", _md_list([f"{e['what']} — {e['why']}" for e in d.get("excluded", [])])]
        util.atomic_write(eng.path("xray", "goal-plan.md"), "\n".join(text) + "\n")
        wrote.append("goal-plan.md")
    im = next(iter(_artifact(eng, nodes, "invariants-merge")), None)
    if im:
        d = _json(im) or {}
        text = ["# Merged invariants (eight-lens design, fanned in)", "",
                "_Each invariant names the lenses that found it independently — more sources, more trust. "
                "`references/hypothesis-craft.md` §2._", ""]
        for i in sorted(d.get("invariants", []), key=lambda i: i["rank"]):
            oc = {True: "On-chain: Yes", False: "On-chain: No", None: ""}[i.get("on_chain")]
            text.append(f"- **{i['id']}** {i['statement']} — derived from {i['derived_from']}; lenses: {', '.join(i['sources'])}; "
                        f"violators: {', '.join(i['violators']) or 'none known'}; test: {i['test']}. {oc}")
        util.atomic_write(eng.path("xray", "invariants-merged.md"), "\n".join(text) + "\n")
        wrote.append("invariants-merged.md")
    sg = next(iter(_artifact(eng, nodes, "strategy")), None)
    if sg:
        d = _json(sg) or {}
        text = ["# Strategy — hypotheses no roster lens owns", ""]
        for s in d.get("strategies", []):
            text.append(f"- **{s['id']}**{' (moonshot)' if s['moonshot'] else ''} [{s['technique']}] {s['hypothesis']} — targets: "
                        f"{', '.join(s['targets'])}; why unseen: {s['why_unseen']}; cheapest test: {s['cheapest_test']}")
        util.atomic_write(eng.path("xray", "strategy.md"), "\n".join(text) + "\n")
        wrote.append("strategy.md")
    return wrote


def act_seed(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    wrote = render_artifacts(eng, nodes)
    from . import seed as seedlib
    res = seedlib.seed(eng)
    extra: List[Dict[str, Any]] = []
    gp = next(iter(_artifact(eng, nodes, "goal-plan")), None)
    for g in (_json(gp) or {}).get("goals", []) if gp else []:
        extra.append({"kind": "goal", "component": f"{g['id']} {g['statement']}"[:120], "lens": "*", "prio": int(g["priority"]),
                      "note": "goal-plan: " + "; ".join(g["first_checks"])[:80], "source": "campaign"})
    im = next(iter(_artifact(eng, nodes, "invariants-merge")), None)
    for i in (_json(im) or {}).get("invariants", []) if im else []:
        extra.append({"kind": "invariant", "component": f"{i['id']} {i['statement']}"[:120], "lens": "invariant-agent",
                      "prio": 5 if i.get("on_chain") is False else 4, "note": f"lenses: {', '.join(i['sources'])}", "source": "campaign"})
    sg = next(iter(_artifact(eng, nodes, "strategy")), None)
    for s in (_json(sg) or {}).get("strategies", []) if sg else []:
        extra.append({"kind": "strategy", "component": f"{s['id']} {s['hypothesis']}"[:120], "lens": "*",
                      "prio": 5 if s["moonshot"] else 4, "note": f"{s['technique']}; test: {s['cheapest_test']}"[:100], "source": "campaign"})
    added = frontier.add_many(eng, extra)
    return True, f"rendered {', '.join(wrote) or 'no artifacts'}; frontier +{res['added']} from the x-ray, +{added} from the campaign"


def act_plan(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    rows = frontier.load(eng)
    top = sorted([r for r in rows if r["status"] in frontier.OPEN], key=lambda r: (-int(r.get("prio") or 3), r["id"]))[:25]
    hits = util.read_json(eng.path("xray", "rule-hits.json"), []) or []
    lines = ["# Plan — ranked hit list (rendered by the campaign from goal-plan, invariants, strategy, rules, x-ray)", ""]
    gp = next(iter(_artifact(eng, nodes, "goal-plan")), None)
    if gp:
        lines += ["## Goals, by priority", ""] + [f"{n}. **{g['id']}** {g['statement']} (priority {g['priority']}) — start with: {g['first_checks'][0]}"
                                                 for n, g in enumerate(sorted((_json(gp) or {}).get("goals", []), key=lambda g: -g["priority"]), 1)] + [""]
    lines += ["## Highest-priority open frontier rows", ""] + [f"- {r['id']} [{r['kind']}] {r['component']} (prio {r['prio']}, lens {r['lens']})" for r in top] + [""]
    if hits:
        lines += ["## Static rule hits worth reading first", ""] + [f"- {h['file']}:{h['line']} — {h['title']}" for h in hits[:20]] + [""]
    lines += ["## Exclusions", "", "Nothing hunts a class the scope card excludes (`.sieve/case.md` → out_of_scope) and nothing ships a finding that "
              "matches a known, already-reported issue (case.md → Known issues).", ""]
    text = "\n".join(lines)
    if len(text) < 260:
        text += "\n" + "The plan is thin because the x-ray produced few rows; the roaming pass exists for exactly this case. " * 2
    util.atomic_write(eng.path("plan.md"), text)
    return True, f"plan.md written ({len(text.splitlines())} lines, {len(top)} top rows)"


def _ensure_pass(eng: Engagement, loop: int) -> None:
    cur = int(eng.load().get("pass_current") or 0)
    if cur >= loop:
        return

    def fn(st: Dict[str, Any]) -> None:
        st["pass_current"] = loop
        st["pass_step"] = ""
        st["waiting"] = None
        st["passes_planned"] = max(int(st.get("passes_planned") or 1), loop)
    eng.update(fn)
    os.makedirs(eng.path("raw", f"pass-{loop}"), exist_ok=True)


def act_pass_merge(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    roaming = node.get("arg") == "roaming"
    n = int(node["vars"].get("loop") or eng.load().get("pass_current") or 1)
    if not roaming:
        rep = pipeline.rollcall(eng, n)
        for a in rep["lost"]:
            _waive(eng, "hunt", f"pass {n}: agent {a} produced no complete output (lost) — its ground is covered by the next pass")
    res = mergelib.merge(eng)
    ab = mergelib.absorb(eng, n)

    def fn(st: Dict[str, Any]) -> None:
        st["pass_step"] = "absorb"
        st["waiting"] = None
    eng.update(fn)
    return True, (f"{'roaming' if roaming else f'pass {n}'}: {res['findings']} FINDING, {res['leads']} LEAD merged "
                  f"({len(res['demotions'])} demoted by machine checks); absorb applied {len(ab['applied'])}, refused {len(ab['refused'])}; "
                  f"frontier {ab['frontier']['open']} open")


def act_merge_final(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    res = mergelib.merge(eng)
    return True, f"final merge: {res['findings']} FINDING candidate(s), {res['leads']} lead(s)"


def _panel(eng: Engagement, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [d for d in (_json(p) for p in _artifact(eng, nodes, "triage")) if isinstance(d, dict)]


def _gate_failed(gates: Dict[str, str]) -> Optional[str]:
    for k in ("g0", "g1", "g2", "g3", "g4", "g5"):
        if gates.get(k) == "fail":
            return k[1]
    return None


def act_reportability(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    """Reportability before severity: hard, checkable gates first (scope, excluded classes), then the panel's
    independent verdicts recorded as votes — the quorum and disagreement rules live in `judging.final`."""
    fence = Fence.load(eng)
    cands = list((util.read_json(eng.path("findings", "candidates.json"), {}) or {}).keys())
    panel = _panel(eng, nodes)
    oos = {re.sub(r"[^a-z0-9]+", "", str(x).lower()) for x in ((fence.oos.get("vulns") if fence else None) or [])}
    out: Dict[str, Any] = {}
    for fid in cands:
        meta, body = validate.finding_meta(eng, fid)
        prior = validate.load_judged(eng).get(fid) or {}
        if prior.get("verdict") in ("cleared", "confirmed", "trace-only", "demoted", "rejected"):
            continue
        reasons: List[str] = []
        if fence:
            for c in citelib.extract(body):
                ok, why = fence.check_path(os.path.join(eng.root, c["path"]), eng.root)
                if not ok:
                    reasons.append(why)
                    break
        if re.sub(r"[^a-z0-9]+", "", str(meta.get("class", "")).lower()) in oos:
            reasons.append(f"class {meta.get('class')} is listed under out_of_scope.vulns")
        votes = [(p.get("panelist", "panel"), v) for p in panel for v in p.get("verdicts", []) if v.get("finding_id") == fid]
        entry: Dict[str, Any] = {"gate_reasons": reasons, "votes": len(votes)}
        try:
            if reasons:
                judging.record_vote(eng, fid, "rejected", "reportability-gate", "; ".join(reasons), gate_failed="3")
                entry["result"] = "rejected"
            elif not votes:
                entry["result"] = "no panel votes"
            else:
                cx = "complex" if any(v["complexity"] == "complex" for _p, v in votes) else "straightforward"
                sevs = [v.get("severity") for _p, v in votes if v.get("severity") and v["verdict"] == "cleared"]
                order = ["informational", "low", "medium", "high", "critical"]
                sev = min(sevs, key=order.index) if sevs else None       # the panel's most conservative severity
                for name, v in votes:
                    judging.record_vote(eng, fid, v["verdict"], str(name), v["reasoning"][:400], confidence=v["confidence"],
                                        severity=sev, complexity=cx, gate_failed=_gate_failed(v["gates"]))
                entry["result"] = (validate.load_judged(eng).get(fid) or {}).get("verdict")
                entry["complexity"], entry["severity"] = cx, sev
        except SystemExit as exc:
            entry["result"] = "refused: " + str(exc)[:200]
        out[fid] = entry
    util.write_json(C.cdir(eng, "reportability.json"), out)
    cleared = sum(1 for e in out.values() if e.get("result") == "cleared")
    return True, (f"{len(out)} candidate(s) gated: {cleared} cleared, "
                  f"{sum(1 for e in out.values() if e.get('result') in ('demoted', 'rejected'))} demoted/rejected")


def _resolve_file(eng: Engagement, p: str) -> str:
    for cand in (p, os.path.join(eng.root, p), os.path.join(eng.dir, p)):
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    return p


def act_prove_run(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    results: Dict[str, Any] = {}
    for path in _artifact(eng, nodes, "prove"):
        for p in (_json(path) or {}).get("proofs", []):
            fid = p["finding_id"]
            judged = validate.load_judged(eng).get(fid) or {}
            if judged.get("gates") != "cleared":
                results[fid] = {"result": "skipped — gates not cleared"}
                continue
            conf = int(statistics.median([v["confidence"] for v in judged.get("votes", [])
                                          if v["verdict"] == "cleared" and v.get("confidence") is not None] or [80]))
            try:
                if p.get("trace_only"):
                    judging.record_vote(eng, fid, "trace-only", "engine-prover", p["rationale"], confidence=conf)
                    results[fid] = {"result": "trace-only"}
                    continue
                ctl = p.get("control") or {"kind": "waived"}
                rec = validate.run_proof(
                    eng, fid, p["oracle"], p["cmd"], p["expect"],
                    control_cmd=ctl.get("cmd") if ctl.get("kind") == "command" else None,
                    control_waiver=ctl.get("waiver") if ctl.get("kind") == "waived" else None,
                    control_patch=_resolve_file(eng, ctl["patch_file"]) if ctl.get("kind") == "patch" else None,
                    repeat=int(p.get("repeat") or 3), cwd=(os.path.join(eng.root, p["cwd"]) if p.get("cwd") else None),
                    env_names=p.get("env") or [], captures=p.get("capture") or [], targets=p.get("target") or [])
                results[fid] = {"result": rec["verdict"], "reasons": rec["reasons"]}
                if rec["verdict"] == "pass":
                    judging.record_vote(eng, fid, "confirmed", "engine-prover",
                                        f"machine-run proof: {rec['repeat']} repeats with a negative control", confidence=conf)
                elif rec["verdict"] == "pass-uncontrolled":
                    judging.record_vote(eng, fid, "trace-only", "engine-prover",
                                        "executed but no negative control was possible: " + str((ctl or {}).get("waiver", "waived"))[:120],
                                        confidence=conf)
            except SystemExit as exc:
                results[fid] = {"result": "refused", "reasons": [str(exc)[:300]]}
    util.write_json(C.cdir(eng, "prove-results.json"), results)
    good = sum(1 for r in results.values() if r["result"] in ("pass", "trace-only", "pass-uncontrolled"))
    return True, f"{len(results)} proof(s) processed, {good} accepted, {len(results) - good} failed/refused/skipped"


def act_audit_gate(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    failures: Dict[str, str] = util.read_json(eng.path("findings", "independence-failures.json"), {}) or {}
    n_ok = 0
    for path in _artifact(eng, nodes, "independence-audit"):
        for a in (_json(path) or {}).get("audits", []):
            fid = a["finding_id"]
            if not a["oracle_independent"] or a["shares_code_with_target"]:
                failures[fid] = a["reason"]
                continue
            j = validate.load_judged(eng).get(fid) or {}
            if j.get("complexity") == "complex" and j.get("gates") == "cleared":
                try:
                    judging.record_vote(eng, fid, "confirmed", "independence-auditor", a["reason"][:300],
                                        confidence=int(j.get("confidence") or 80))
                    n_ok += 1
                except SystemExit:
                    pass
    util.write_json(eng.path("findings", "independence-failures.json"), failures)
    return True, f"independence audit: {len(failures)} proof(s) capped at trace-verified, {n_ok} second-verifier confirmation(s)"


def act_verify(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    rc, out = _cli("verify")
    util.atomic_write(C.cdir(eng, "verify.txt"), out + "\n")
    return True, out.split("\n")[-1][:160] if out else "verified"


def act_report(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    path = report.write(eng)
    _t, counts = report.build(eng)
    return True, (f"{os.path.relpath(path, eng.root)}: {counts['findings']} confirmed, {counts['trace_verified']} trace-verified, "
                  f"{counts['unvalidated'] + counts['stale'] + counts['tampered']} unvalidated, {counts['leads']} lead(s)")


def act_writeback(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    rc, out = _cli("kb", "writeback")
    return True, (out.split("\n")[-1][:160] if out else "write-back done") if rc == 0 else f"write-back skipped: {out[:120]}"


def act_map(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    rc, out = _cli("xray", "map")
    return (rc == 0), out[:200]


def act_finish(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    rc, out = _cli("finish")
    return (rc == 0), out[:400]


ACTIONS: Dict[str, Callable[[Engagement, Dict[str, Any], List[Dict[str, Any]]], Result]] = {
    "phase": act_phase, "xray": act_xray, "rules": act_rules, "prime": act_prime, "seed": act_seed, "plan": act_plan,
    "pass-merge": act_pass_merge, "merge-final": act_merge_final, "reportability": act_reportability,
    "prove-run": act_prove_run, "audit-gate": act_audit_gate, "verify": act_verify, "report": act_report,
    "writeback": act_writeback, "map": act_map, "finish": act_finish,
    "fuzz-absorb": act_fuzz_absorb, "browser": act_browser, "external-leads": act_external_leads,
}


def run_meta(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Result:
    fn = ACTIONS.get(str(node.get("action")))
    if fn is None:
        return False, f"unknown meta action {node.get('action')!r} (known: {', '.join(sorted(ACTIONS))})"
    try:
        return fn(eng, node, nodes)
    except SystemExit as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 — a crashing action must fail the node, not the engine
        return False, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------- submission

def _semantic_checks(eng: Engagement, node: Dict[str, Any], data: Any, errs: List[str]) -> None:
    check = node.get("check")
    if check == "triage-complete":
        from .flow import _unjudged
        want = f"triage-{node['vars'].get('panelist')}"
        if (data or {}).get("panelist") != want:
            errs.append(f"$.panelist: must be exactly {want!r} — distinct panelist names are what make the quorum count")
        cand = set(_unjudged(eng))
        seen = {v.get("finding_id") for v in (data or {}).get("verdicts", [])}
        for miss in sorted(cand - seen):
            errs.append(f"$.verdicts: no verdict for candidate {miss} — every candidate needs a verdict from every panelist")
        for extra in sorted(seen - set((util.read_json(eng.path("findings", "candidates.json"), {}) or {}).keys())):
            errs.append(f"$.verdicts: {extra} is not a candidate finding")
    elif check == "fuzz-valid":
        d = data or {}
        if d.get("status") == "ran" and not d.get("runs"):
            errs.append("$.runs: status is `ran` but no run is recorded: list every invariant you fuzzed, with its result")
        for i, r in enumerate(d.get("runs", [])):
            if r.get("result") == "broken" and not r.get("sequence"):
                errs.append(f"$.runs[{i}]: a broken invariant needs `sequence`, the shrunk call sequence that replays the break")
    elif check == "proofs-valid":
        from . import validate as V
        cleared = {fid for fid, j in V.load_judged(eng).items() if j.get("gates") == "cleared" and j.get("verdict") in ("cleared",)}
        have = set()
        for i, p in enumerate((data or {}).get("proofs", [])):
            have.add(p.get("finding_id"))
            if not p.get("trace_only"):
                for k in ("cmd", "expect", "control"):
                    if not p.get(k):
                        errs.append(f"$.proofs[{i}]: `{k}` is required unless `trace_only` is true")
                c = p.get("control") or {}
                if c.get("kind") == "patch" and not os.path.isfile(_resolve_file(eng, str(c.get("patch_file", "")))):
                    errs.append(f"$.proofs[{i}].control.patch_file: {c.get('patch_file')} does not exist")
                if c.get("kind") == "command" and not c.get("cmd"):
                    errs.append(f"$.proofs[{i}].control: kind command needs `cmd`")
                if c.get("kind") == "waived" and not c.get("waiver"):
                    errs.append(f"$.proofs[{i}].control: kind waived needs `waiver` (why no control is possible)")
        for miss in sorted(cleared - have):
            errs.append(f"$.proofs: no entry for cleared finding {miss} — prove it, or list it with `trace_only: true` and a rationale")


def submit(eng: Engagement, node: Dict[str, Any], accept: Optional[str] = None) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    check = node.get("check")
    if check in ("rollcall", "rollcall-roaming"):
        loop = int(node["vars"].get("loop") or eng.load().get("pass_current") or 1)
        agent = pipeline.ROAMING if check == "rollcall-roaming" else next(
            (a for a in pipeline.roster(eng, loop) if a["id"] == node["vars"].get("agent_id")), None)
        if agent is None:
            return False, ["cannot resolve this node's agent from the roster"]
        res = pipeline.check_agent(eng, loop, agent)
        if res["status"] == "lost":
            return False, res["shortfalls"]
        if res["status"] == "thin":
            if accept and len(accept.strip()) >= 12:
                _waive(eng, "hunt", f"pass {loop}: {agent['id']} below the completeness contract — {accept.strip()}")
            else:
                return False, ["below the completeness contract (methodology.md Part 0) — send the agent back to finish:"] + \
                       ["  - " + s for s in res["shortfalls"]] + ["or accept the debt: `sieve campaign submit <node> --accept \"reason\"`"]
        return True, []
    if check == "frontier-drained":
        fs = frontier.stats(eng)
        if fs["open"] > 0:
            rows = frontier.next_rows(eng, n=8)
            return False, [f"{fs['open']} frontier row(s) still open — close each with a receipt (`sieve frontier done/dead ...` or COVERAGE + `sieve absorb`):"] + \
                   [f"  - {r['id']} [{r['kind']}] {r['component']}" for r in rows]
        return True, []
    for o in node["outputs"]:
        p = eng.path(o["path"])
        s = o.get("schema")
        if s in schema.MARKDOWN:
            errs += schema.validate_markdown(s, p if os.path.isdir(p) else os.path.dirname(p))
        elif s in schema.CONTRACTS:
            e, data = schema.validate_file(s, p)
            errs += e
            if not e:
                _semantic_checks(eng, node, data, errs)
        elif s is None:
            if not os.path.isfile(p) and not os.path.isdir(p):
                errs.append(f"{o['path']}: missing")
    return (not errs), errs
