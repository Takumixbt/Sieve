"""The hunt pipeline, mechanical half: roster -> bundle -> dispatch -> rollcall.

Everything here is bookkeeping a script can do exactly and an orchestrator tends to narrate instead
(`references/dispatch.md`): build each actor's bundle from files on disk, print its size, record who
was spawned, and afterwards check — by reading what they wrote — that each one really finished and
really did the reasoning the completeness contract (`methodology.md` Part 0) requires. Judgment
stays with the agents; this module only refuses to let "I dispatched them" stand in for evidence.
"""
from __future__ import annotations

import glob
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from . import blocks as B
from . import frontier, repo_root, util, vectors, yamlish
from .config import load_config
from .state import Engagement

REFERENCES = ("methodology.md", "hypothesis-craft.md", "shared-rules.md")
XRAY_FILES = ("x-ray.md", "entry-points.md", "invariants.md", "authz-matrix.md", "attack-surface.md",
              "precedents.md")
INDEX_CAP = {"files": 300, "entries": 250, "leads": 120, "surface": 300, "history": 12}


# ------------------------------------------------------------------ roster

def discover(pack: str) -> List[Dict[str, Any]]:
    d = os.path.join(repo_root(), "packs", pack, "agents")
    out: List[Dict[str, Any]] = []
    for f in sorted(glob.glob(os.path.join(d, "*.md"))):
        if os.path.basename(f) == "README.md":
            continue
        try:
            meta, _ = yamlish.split_frontmatter(util.read_text(f))
        except yamlish.YamlError:
            meta = {}
        stem = os.path.basename(f)[:-3]
        name = str(meta.get("name") or stem)
        vec = meta.get("vectors") or []
        if isinstance(vec, str):
            vec = [v.strip() for v in vec.split(",") if v.strip()]
        out.append({"pack": pack, "name": name, "id": f"{pack}/{name}", "slug": f"{pack}--{name}",
                    "path": f, "owns": str(meta.get("owns") or ""), "tier": str(meta.get("tier") or "deep"),
                    "enum_only": bool(meta.get("enumeration_only")), "vectors": list(vec)})
    return out


def roster(eng: Engagement, pass_n: int, only: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    st = eng.load()
    packs = list(st.get("packs") or [])
    mode = st.get("mode", "deep")
    agents: List[Dict[str, Any]] = []
    for p in packs:
        agents += discover(p)
    if mode in ("quick", "focus"):
        agents = [a for a in agents if a["tier"] == "core"]
    if len(packs) >= 2 and pass_n >= 2 and mode == "deep":
        agents += discover("seams")          # the seams only exist once two packs have produced output
    if only:
        want = {w.strip() for w in only if w.strip()}
        picked = [a for a in agents if a["name"] in want or a["id"] in want or a["slug"] in want]
        if not picked:
            raise SystemExit("sieve: --only matched nothing; roster this pass: "
                             + ", ".join(a["id"] for a in agents))
        agents = picked
    return agents


ROAMING = {"pack": "roaming", "name": "roaming", "id": "roaming", "slug": "roaming", "path": "",
           "owns": "what nobody on the roster owns — the unusual thing about THIS system", "tier": "core",
           "enum_only": False, "vectors": []}


def raw_path(eng: Engagement, n: int, agent: Dict[str, Any]) -> str:
    if agent["slug"] == "roaming":
        return eng.path("raw", "roaming.md")
    return eng.path("raw", f"pass-{n}", f"{agent['slug']}.md")


def bundle_path(eng: Engagement, n: int, agent: Dict[str, Any]) -> str:
    if agent["slug"] == "roaming":
        return eng.path("bundles", "roaming-bundle.md")
    return eng.path("bundles", f"pass-{n}", f"{agent['slug']}-bundle.md")


def _facts(eng: Engagement) -> Dict[str, Any]:
    return util.read_json(eng.path("xray", "facts.json"), {}) or {}


def kloc(eng: Engagement, pack: str) -> float:
    f = _facts(eng).get(pack) or {}
    try:
        return float(f.get("nsloc_total") or 0) / 1000.0
    except (TypeError, ValueError):
        return 0.0


def quota(eng: Engagement, agent: Dict[str, Any]) -> Dict[str, int]:
    """The numbers this agent's output file must reach — computed once so the bundle states them and
    rollcall enforces exactly the same ones."""
    if agent["slug"] == "roaming":   # hypothesis-craft.md §5: three classes nobody on the roster owns
        return {"hypotheses": 3, "techniques": 3, "moonshots": 1, "feynman": 2, "socratic": 2, "inversion": 2}
    cfg = load_config(eng.root)
    q = cfg.get("audit.hypothesis_quota", {}) or {}
    m = cfg.get("audit.markers", {}) or {}
    k = kloc(eng, agent["pack"]) if agent["pack"] != "seams" else sum(kloc(eng, p) for p in eng.load()["packs"])
    out = {"hypotheses": int(q.get("min_total", 8)), "techniques": int(q.get("min_techniques", 4)),
           "moonshots": int(q.get("min_moonshots", 1))}
    for name in ("feynman", "socratic", "inversion"):
        spec = m.get(name, {}) or {}
        need = float(spec.get("base", 2)) + float(spec.get("per_kloc", 1)) * k
        out[name] = int(min(float(spec.get("cap", 40)), math.ceil(need)))
    return out


# ------------------------------------------------------------------ bundle

def _section(n: int, total: int, title: str, body: str) -> str:
    bar = "═" * 72
    return f"\n{bar}\n# [{n}/{total}] {title}\n{bar}\n\n{body.strip()}\n"


def _read_or(path: str, missing: str) -> str:
    return util.read_text(path) if os.path.isfile(path) else missing


def _rows_for(eng: Engagement, agent: Dict[str, Any], cap: int = 60) -> str:
    rows = [r for r in frontier.load(eng) if r["status"] in frontier.OPEN and r["lens"] in ("*", agent["name"])]
    rows.sort(key=lambda r: (-int(r.get("prio") or 3), r["id"]))
    if not rows:
        return "_No open frontier rows are assigned to your lens. Hunt your lens across the whole scope and add rows (`sieve frontier add`) for anything you find that has no home._"
    lines = ["| row | kind | component | prio | lens | note |", "|---|---|---|---|---|---|"]
    for r in rows[:cap]:
        lines.append(f"| {r['id']} | {r['kind']} | {r['component']} | {r['prio']} | {r['lens']} | {r['note'][:60]} |")
    if len(rows) > cap:
        lines.append(f"\n_+{len(rows) - cap} more open rows — `sieve frontier next --lens {agent['name']} -n 200`._")
    return "\n".join(lines)


def _source_index(eng: Engagement, agent: Dict[str, Any]) -> str:
    facts = _facts(eng)
    packs = eng.load()["packs"] if agent["pack"] == "seams" else [agent["pack"]]
    out: List[str] = []
    for p in packs:
        f = facts.get(p)
        if not f:
            out.append(f"_({p}: no mechanical facts — run `sieve xray {p}`; binary targets are triaged by hand per "
                       f"`xray.md` Phase 2.)_")
            continue
        if p == "web3":
            files = sorted(f.get("files") or [], key=lambda x: -int(x.get("nsloc") or 0))
            out.append(f"**web3 — {len(files)} file(s), {f.get('nsloc_total', 0)} nSLOC** (read these yourself; paths are relative to the target root)\n")
            out.append("| file | lang | nSLOC |\n|---|---|---|")
            for x in files[:INDEX_CAP["files"]]:
                out.append(f"| {x['path']} | {x.get('lang', '')} | {x.get('nsloc', 0)} |")
            ents = f.get("entry_candidates") or []
            out.append(f"\n**Entry-point candidates (grep-derived, {len(ents)})**\n")
            for e in ents[:INDEX_CAP["entries"]]:
                out.append(f"- {e['file']}:{e['line']}  `{str(e['text']).strip()[:110]}`")
            leads = f.get("tool_leads") or []
            out.append(f"\n**Static-analysis leads ({len(leads)}; corroborated = two tools agree — read those first)**\n")
            for l in sorted(leads, key=lambda x: not x.get("corroborated"))[:INDEX_CAP["leads"]]:
                star = "★ " if l.get("corroborated") else ""
                out.append(f"- {star}[{l.get('source')}] {l.get('check')} ({l.get('impact')}) {l.get('file')}:{l.get('line')}")
        elif p == "web":
            rows = f.get("surface") or []
            out.append(f"**web — {len(rows)} endpoint(s) merged from OpenAPI / HAR / URL lists**\n")
            out.append("| method | path | auth | sources |\n|---|---|---|---|")
            for r in rows[:INDEX_CAP["surface"]]:
                out.append(f"| {r['method']} | {r['path']} | {r['auth']} | {','.join(r['sources'])} |")
        else:
            out.append(f"_({p}: facts present but no index renderer — read `.sieve/xray/facts.json`.)_")
    g = util.read_json(eng.path("xray", "git-security.json"), {}) or {}
    fixes = g.get("fix_candidates") or []
    if fixes:
        out.append("\n**Git history — fix-scored commits (a candidate, not a verdict; Five Whys them)**\n")
        for c in fixes[:INDEX_CAP["history"]]:
            out.append(f"- {c['sha']} score {c['score']} — {c['subject']}  ({', '.join(c.get('files', []))})")
    return "\n".join(out) if out else "_(no x-ray facts — run `sieve xray` first.)_"


def _vectors_for(agent: Dict[str, Any]) -> str:
    packs = [agent["pack"]]
    cards: List[Dict[str, str]] = []
    for p in packs:
        cards += vectors.load_pack(p)
    if agent["vectors"]:
        want = tuple(agent["vectors"])
        cards = [c for c in cards if c["id"].startswith(want)]
    if not cards:
        return "_(this pack has no vector cards for your lens — hunt from first principles.)_"
    return vectors.render(cards)


def output_contract(eng: Engagement, n: int, agent: Dict[str, Any]) -> str:
    q = quota(eng, agent)
    raw = raw_path(eng, n, agent)
    rel = os.path.relpath(raw, eng.root)
    if agent["enum_only"]:
        body = f"""You are an **enumeration-only** actor: you map surface and never decide a verdict
(`agents/README.md`). Write your map to ONE file — `{rel}` — using LEAD / HYPOTHESIS blocks for anything
worth a follow-up. Quotas below do not apply to you; the COVERAGE section and the DONE line do."""
    else:
        body = f"""You write ONE file: **`{rel}`** (absolute: `{raw}`). It is the only file you may create — everything
else under the target is read-only (`shared-rules.md`). Put PoC code inside the file as quoted text.
This contract is machine-checked by `sieve rollcall` after you finish; a file that misses it is sent back.

**Quotas for your lens (computed from this target's size):**

| what | minimum |
|---|---|
| distinct hypotheses (FINDING + LEAD + HYPOTHESIS blocks) | {q['hypotheses']} |
| distinct techniques across them (tag each block `technique: <name>` from methodology.md Part 3) | {q['techniques']} |
| moonshots (tag `moonshot: true` on a hypothesis that felt like a stretch) | {q['moonshots']} |
| `[Feynman: …]` markers in your working notes | {q['feynman']} |
| `[Socratic: …]` markers | {q['socratic']} |
| `[Inversion: …]` markers | {q['inversion']} |"""
    return body + f"""

**Block rules the merge step enforces mechanically** (a block that breaks them is kept — as a LEAD, with the
reason recorded — never silently dropped, and never promoted):

- A FINDING needs a real `proof:` (concrete values, a trace, or a request/response — not "see above").
- Every `file:line` you cite is re-read by code. A citation whose file or line does not exist, or whose quoted
  snippet is not at that line, demotes the block. Quote code as `` file.sol:42 `require(x)` `` if you want the
  snippet checked too.
- Hedge language in `description:` (*could theoretically, might allow, under certain conditions…*) demotes it.
- Tag `pack:`, `class:`, `component:` on every block so it dedups (`group_key`).

**Then a `## COVERAGE` section** — one line per frontier row you examined (the rows assigned to you are in section 4):

```
## COVERAGE
R-0007 | finding | <the group_key or title of the FINDING/LEAD you wrote for it>
R-0008 | clean   | <the guard that makes it hold, file:line> | inversion: <what you tried to make it true>; input: <what you varied>
R-0009 | dead    | layer: <attempt>; sibling: <attempt>; precedent: <attempt>
R-0010 | open    | <what is left and why>
```

Rungs are the stuck ladder (`sieve ladder`): input, layer, precondition, inversion, precedent, sibling, transplant,
construct, fresh-eyes. `sieve absorb` closes a row only when it can be closed with a receipt — `clean` needs ≥2
attempts including `inversion`; `dead` needs ≥3 attempts on ≥3 different rungs. Identical text pasted across rows
is refused.

**Last line of the file, after everything else:** `SIEVE-AGENT-DONE {agent['slug']} pass {n}`
A file without that line is treated as a crashed agent."""


def build_bundle(eng: Engagement, n: int, agent: Dict[str, Any]) -> Tuple[str, int, str]:
    st = eng.load()
    root = repo_root()
    total = 9
    parts: List[str] = [f"<!-- SIEVE BUNDLE · {agent['id']} · pass {n} · engagement {st['id']} · {util.now_iso()} -->\n"
                        f"# Bundle — {agent['id']} (pass {n})\n\nRead this whole file before you hunt. It holds your scope, "
                        f"your lens, the finding format and the anti-hallucination protocol. Do not re-derive any of it."]
    parts.append(_section(1, total, "SCOPE CARD — the fence (.sieve/case.md)",
                          _read_or(eng.case_path(), "**NO SCOPE CARD — do not touch anything.**")))
    xr = [f"### xray/{name}\n\n{util.read_text(eng.path('xray', name))}" for name in XRAY_FILES
          if os.path.isfile(eng.path("xray", name))]
    parts.append(_section(2, total, "X-RAY — what the pre-hunt map found",
                          "\n\n".join(xr) or "_(no x-ray narrative yet — that is a process failure; say so in your output.)_"))
    parts.append(_section(3, total, "PLAN — the ranked hit list from PRIME (.sieve/plan.md)",
                          _read_or(eng.path("plan.md"), "_(empty)_")))
    prior = ""
    if n >= 2:
        ledger = eng.path("findings", "ledger.md")
        prior = ("### What earlier passes already reported (report yours in full anyway — a bug you reach again "
                 "is still there)\n\n" + _read_or(ledger, "_(nothing merged yet)_") + "\n\n")
    parts.append(_section(4, total, f"FRONTIER — the rows assigned to you (lens {agent['name']})",
                          prior + _rows_for(eng, agent)))
    parts.append(_section(5, total, "SOURCE / SURFACE INDEX", _source_index(eng, agent)))
    refs = [f"### references/{r}\n\n{util.read_text(os.path.join(root, 'references', r))}" for r in REFERENCES]
    parts.append(_section(6, total, "METHOD — how to think and what you may claim", "\n\n".join(refs)))
    parts.append(_section(7, total, f"VECTOR CARDS — packs/{agent['pack']}/vectors", _vectors_for(agent)))
    parts.append(_section(8, total, "OUTPUT CONTRACT — generated, binding", output_contract(eng, n, agent)))
    parts.append(_section(9, total, f"YOUR LENS — {agent['id']}", util.read_text(agent["path"])))
    text = "\n".join(parts)
    path = bundle_path(eng, n, agent)
    util.atomic_write(path, text)
    return path, text.count("\n") + 1, util.sha256_bytes(text.encode("utf-8"))


def build_roaming_bundle(eng: Engagement, n: int) -> Tuple[str, int, str]:
    """The roaming pass (`hypothesis-craft.md` §5): no lens, no vector cards. The actor is told what has
    already been covered — the ledger, the closed rows, every class already raised — and asked what is
    unusual about *this* system that nobody on the roster was looking for."""
    st = eng.load()
    root = repo_root()
    closed = [r for r in frontier.load(eng) if r["status"] in ("done", "dead")]
    classes = sorted({str(x.get("class", "")) for x in _merged_meta(eng)})
    closed_txt = "\n".join(f"- {r['id']} [{r['kind']}] {r['component']} — {r['note'][:80]}" for r in closed[:150])
    covered = ("### Classes already raised in this engagement\n\n" + (", ".join(c for c in classes if c) or "_(none)_")
               + "\n\n### Frontier rows already closed\n\n" + (closed_txt or "_(none)_"))
    total = 7
    parts = [f"<!-- SIEVE ROAMING BUNDLE · pass {n} · engagement {st['id']} · {util.now_iso()} -->\n"
             "# Bundle — the roaming pass\n\nYou have no lens and no vector cards on purpose. Everyone on the roster "
             "looked through a named lens; you look for what none of them owned."]
    parts.append(_section(1, total, "SCOPE CARD — the fence (.sieve/case.md)",
                          _read_or(eng.case_path(), "**NO SCOPE CARD.**")))
    xr = [f"### xray/{name}\n\n{util.read_text(eng.path('xray', name))}" for name in XRAY_FILES
          if os.path.isfile(eng.path("xray", name))]
    parts.append(_section(2, total, "X-RAY", "\n\n".join(xr) or "_(none)_"))
    parts.append(_section(3, total, "WHAT IS ALREADY COVERED", covered + "\n\n### Ledger\n\n"
                          + _read_or(eng.path("findings", "ledger.md"), "_(nothing merged)_")))
    scope_pack = st["packs"][0] if len(st["packs"]) == 1 else "seams"
    parts.append(_section(4, total, "SOURCE / SURFACE INDEX", _source_index(eng, {"pack": scope_pack, "name": "roaming"})))
    refs = [f"### references/{r}\n\n{util.read_text(os.path.join(root, 'references', r))}" for r in REFERENCES]
    parts.append(_section(5, total, "METHOD", "\n\n".join(refs)))
    parts.append(_section(6, total, "OUTPUT CONTRACT — generated, binding", output_contract(eng, n, ROAMING)))
    parts.append(_section(7, total, "YOUR TASK — roaming pass", (
        "List every class already covered (section 3). Then ask, of THIS system, what is unusual about it: the odd "
        "dependency, the custom encoding, the legacy path, the feature that exists for one customer, the assumption "
        "the whole design leans on. Write **at least three hypothesis classes nobody on the roster was looking for** and "
        "test each one to a proof or a documented dead end (receipts: `sieve ladder`). Dead ends are written down too — "
        "that is what stops the next pass repeating them. Your COVERAGE section closes the `roaming` frontier row.")))
    text = "\n".join(parts)
    path = bundle_path(eng, n, ROAMING)
    util.atomic_write(path, text)
    return path, text.count("\n") + 1, util.sha256_bytes(text.encode("utf-8"))


def _merged_meta(eng: Engagement) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in sorted(glob.glob(eng.path("findings", "F-*.md"))):
        try:
            out.append(yamlish.split_frontmatter(util.read_text(f))[0])
        except yamlish.YamlError:
            continue
    return out


def dispatch_prompt(bundle: str, lines: int, slug: str, n: int) -> str:
    return (f"Read `{bundle}` ({lines} lines) in full before hunting — it holds your scope, your lens, the finding "
            f"format, and the anti-hallucination protocol. Do not re-derive any of it. Write your output to the file "
            f"its OUTPUT CONTRACT names and finish it with `SIEVE-AGENT-DONE {slug} pass {n}`. Emit findings in the "
            f"shared-rules.md format at SUSPECT or REACHABLE. You do not gate, dedup, or verify. Be your own devil's "
            f"advocate — do not finish until coverage feels complete.")


# ------------------------------------------------------------------ dispatch record

def dispatch_path(eng: Engagement, n: int) -> str:
    return eng.path("bundles", f"dispatch-{n}.json")


def record_dispatch(eng: Engagement, n: int, agents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Verify each bundle on disk is intact (exists, hash matches what `sieve bundle` wrote) and record the
    spawn. Refuses a truncated or missing bundle — the failure `dispatch.md` warns about."""
    manifest = util.read_json(eng.path("bundles", f"manifest-{n}.json"), {}) or {}
    recs: List[Dict[str, Any]] = []
    problems: List[str] = []
    for a in agents:
        p = bundle_path(eng, n, a)
        meta = manifest.get(a["slug"])
        if not os.path.isfile(p) or not meta:
            problems.append(f"{a['id']}: bundle not built (`sieve bundle --all`)")
            continue
        if util.sha256_file(p) != meta["sha256"]:
            problems.append(f"{a['id']}: bundle changed or was truncated since it was built — rebuild it")
            continue
        recs.append({"agent": a["id"], "slug": a["slug"], "bundle": os.path.relpath(p, eng.root),
                     "lines": meta["lines"], "sha256": meta["sha256"],
                     "raw": os.path.relpath(raw_path(eng, n, a), eng.root), "spawned": util.now_iso()})
    if problems:
        raise SystemExit("sieve dispatch: refusing to dispatch:\n  - " + "\n  - ".join(problems))
    util.write_json(dispatch_path(eng, n), {"pass": n, "agents": recs, "time": util.now_iso()})
    return recs


# ------------------------------------------------------------------ rollcall

def check_agent(eng: Engagement, n: int, agent: Dict[str, Any]) -> Dict[str, Any]:
    p = raw_path(eng, n, agent)
    res: Dict[str, Any] = {"agent": agent["id"], "slug": agent["slug"], "raw": os.path.relpath(p, eng.root),
                           "status": "ok", "shortfalls": [], "notes": []}
    if not os.path.isfile(p) or os.path.getsize(p) < 200:
        res.update(status="lost", size=0)
        res["shortfalls"].append("no output file (or under 200 bytes) — the agent never wrote its results")
        return res
    text = util.read_text(p)
    res["size"] = len(text)
    done = B.done_marker(text)
    if not done or done["agent"] != agent["slug"] or done["pass"] != n:
        res["status"] = "lost"
        res["shortfalls"].append(f"no `SIEVE-AGENT-DONE {agent['slug']} pass {n}` line — treated as a crashed/truncated agent")
    blocks = B.parse_blocks(text, res["raw"])
    counts = {k: sum(1 for b in blocks if b["kind"] == k) for k in B.KINDS}
    res["blocks"] = counts
    res["coverage_rows"] = len(B.parse_coverage(text))
    res["findings_without_proof"] = sum(1 for b in blocks if b["kind"] == "FINDING" and len(str(b.get("proof", "")).strip()) < 20)
    if not agent["enum_only"] and res["status"] != "lost":
        q = quota(eng, agent)
        hyp = len(blocks)
        tech = B.techniques(blocks)
        moon = B.moonshots(blocks)
        mk = B.count_markers(text)
        res["measured"] = {"hypotheses": hyp, "techniques": len(tech), "moonshots": moon,
                           "feynman": mk["Feynman"], "socratic": mk["Socratic"], "inversion": mk["Inversion"]}
        for key, have in (("hypotheses", hyp), ("techniques", len(tech)), ("moonshots", moon),
                          ("feynman", mk["Feynman"]), ("socratic", mk["Socratic"]), ("inversion", mk["Inversion"])):
            if have < q[key]:
                res["shortfalls"].append(f"{key}: {have} of {q[key]} required")
        if res["shortfalls"]:
            res["status"] = "thin"
    if res["status"] != "lost" and res["coverage_rows"] == 0:
        assigned = [r for r in frontier.load(eng) if r["status"] in frontier.OPEN and r["lens"] in ("*", agent["name"])]
        if assigned:
            res["notes"].append("no COVERAGE lines — none of your assigned rows can be closed from this file")
    if res["findings_without_proof"]:
        res["notes"].append(f"{res['findings_without_proof']} FINDING block(s) have no real proof: — they will merge as LEADs")
    return res


def rollcall(eng: Engagement, n: int, roaming: bool = False) -> Dict[str, Any]:
    disp = None if roaming else util.read_json(dispatch_path(eng, n), None)
    if roaming:
        agents = [ROAMING]
    elif disp:
        by_slug = {a["slug"]: a for a in roster(eng, n)}
        agents = [by_slug[r["slug"]] for r in disp["agents"] if r["slug"] in by_slug]
    else:
        agents = roster(eng, n)
    results = [check_agent(eng, n, a) for a in agents]
    report = {"pass": n, "time": util.now_iso(), "agents": results,
              "ok": [r["agent"] for r in results if r["status"] == "ok"],
              "thin": [r["agent"] for r in results if r["status"] == "thin"],
              "lost": [r["agent"] for r in results if r["status"] == "lost"]}
    os.makedirs(eng.path("logs"), exist_ok=True)
    util.write_json(eng.path("logs", "rollcall-roaming.json" if roaming else f"rollcall-{n}.json"), report)
    return report
