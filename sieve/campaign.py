"""The campaign engine: a topology-driven audit campaign.

A campaign is a DAG of nodes declared in `campaigns/campaign.yml` (copied per engagement to
`.sieve/campaign/topology.yml`, where it and its prompts can be edited). Three node kinds:

    meta       run by the engine itself, in-process: x-ray, rules, seed, merge, gates, proof runs, report
    agentic    run by an agent the orchestrator dispatches; the engine renders its prompt, then validates the
               artifact it wrote against a versioned contract (`campaign_schema.py`) before the node counts
    reference  a static document a node's prompt inlines (methodology, shared rules)

The engine never calls a model. It decides *what is ready*, *what each agent is told*, and *whether what
came back is acceptable* — and refuses to move forward on anything unvalidated. State is on disk
(`.sieve/campaign/state.json`), so a run resumes after a crash, a context reset or an edit to the topology
(changed upstream artifacts mark downstream nodes stale rather than silently reusing them).

Features carried over from the design this is modelled on: topology file with exactly one primary output per
node, `repeat` expansion (parallel or series loops), `matrix` fan-out (one node per lens / agent), fan-in by
`depends_on`, profiles (smoke / default / exhaustive), editable prompts, a threat-model -> goal-plan chain,
an eight-lens invariant design with a merge, a dynamic strategy node, a triage panel with quorum, a
deterministic reportability gate, and a differential-reference independence audit.
"""
from __future__ import annotations

import fnmatch
import itertools
import json
import os
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple

from . import campaign_schema as schema
from . import pipeline, repo_root, util, yamlish
from .fence import card_for_prompt
from .state import Engagement

KINDS = ("meta", "agentic", "reference")
DONE_LIKE = ("done", "skipped")
_TPL = re.compile(r"\{(\w+)(?:-(\d+))?\}")


# ---------------------------------------------------------------------------- paths

def cdir(eng: Engagement, *parts: str) -> str:
    return eng.path("campaign", *parts)


def state_path(eng: Engagement) -> str:
    return cdir(eng, "state.json")


def active(eng: Engagement) -> bool:
    return os.path.isfile(state_path(eng))


def default_topology() -> str:
    return os.path.join(repo_root(), "campaigns", "campaign.yml")


def prompt_search(eng: Engagement, name: str) -> str:
    """The engagement's editable copy wins; the repo default is the fallback."""
    mine = cdir(eng, "prompts", name)
    if os.path.isfile(mine):
        return mine
    return os.path.join(repo_root(), "campaigns", "prompts", name)


# ---------------------------------------------------------------------------- topology

def load_topology(path: str) -> Dict[str, Any]:
    try:
        topo = yamlish.load_file(path)
    except (OSError, yamlish.YamlError) as exc:
        raise SystemExit(f"sieve campaign: cannot read topology {path}: {exc}")
    if not isinstance(topo, dict) or not isinstance(topo.get("nodes"), list):
        raise SystemExit(f"sieve campaign: {path} needs a top-level `nodes:` list")
    return topo


def _slug(v: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(v).lower()).strip("-") or "x"


def _subst(s: Any, vars_: Dict[str, Any]) -> Any:
    if not isinstance(s, str):
        return s

    def rep(m: "re.Match[str]") -> str:
        name, minus = m.group(1), m.group(2)
        if name not in vars_:
            return m.group(0)
        v = vars_[name]
        if minus:
            return str(int(v) - int(minus))
        return str(v)
    return _TPL.sub(rep, s)


def profile_vars(topo: Dict[str, Any], profile: str, eng: Engagement) -> Dict[str, Any]:
    profiles = topo.get("profiles") or {}
    if profile not in profiles:
        raise SystemExit(f"sieve campaign: unknown profile {profile!r}; this topology defines: {', '.join(profiles) or 'none'}")
    v = dict(profiles[profile] or {})
    lenses = v.get("lenses", "all")
    v["lenses"] = list(schema.LENSES) if lenses in ("all", None) else [str(x) for x in lenses]
    v["packs"] = list(eng.load()["packs"])
    core_only = str(v.get("roster", "all")) == "core"
    loops = int(v.get("hunt_loops", 2))
    seen: List[str] = []
    for n in range(1, loops + 1):
        for a in pipeline.roster(eng, n):
            if core_only and a["tier"] != "core":
                continue
            if a["id"] not in seen:
                seen.append(a["id"])
    v["roster"] = seen
    v["hunt_loops"] = loops
    v["triage_quorum"] = max(2, int(v.get("triage_quorum", 2)))
    v["skip"] = [str(x) for x in (v.get("skip") or [])]
    v["_core_only"] = core_only
    return v


def _resolve(val: Any, pv: Dict[str, Any]) -> Any:
    if isinstance(val, str) and val.startswith("$"):
        key = val[1:]
        if key not in pv:
            raise SystemExit(f"sieve campaign: profile variable {val} is not defined")
        return pv[key]
    return val


def _as_list(v: Any) -> List[Any]:
    if isinstance(v, int) and not isinstance(v, bool):
        return list(range(1, v + 1))
    return list(v) if isinstance(v, (list, tuple)) else [v]


def expand(topo: Dict[str, Any], eng: Engagement, profile: str) -> List[Dict[str, Any]]:
    """Specs -> concrete nodes (matrix x repeat), dependencies resolved, paths templated."""
    pv = profile_vars(topo, profile, eng)
    nodes: List[Dict[str, Any]] = []
    for spec in topo["nodes"]:
        sid = str(spec.get("id"))
        if sid in pv["skip"]:
            continue
        if spec.get("packs") and not (set(spec["packs"]) & set(pv["packs"])):
            continue
        if spec.get("profiles") and profile not in spec["profiles"]:
            continue
        matrix = spec.get("matrix") or {}
        mvars = list(matrix.keys())
        mvals = [_as_list(_resolve(matrix[k], pv)) for k in mvars]
        rep = spec.get("repeat") or {}
        rvar = str(rep.get("var") or "n")
        rcount = int(_resolve(rep.get("count", 1), pv)) if rep else 1
        rmode = str(rep.get("mode") or "parallel")
        combos = list(itertools.product(*mvals)) if mvars else [()]
        for combo in combos:
            for i in range(1, rcount + 1):
                vars_: Dict[str, Any] = dict(zip(mvars, combo))
                if "agent" in vars_:
                    vars_["agent_id"] = vars_["agent"]
                    vars_["agent"] = _slug(vars_["agent_id"])
                    vars_["slug"] = str(vars_["agent_id"]).replace("/", "--")
                if rep:
                    vars_[rvar] = i
                vars_.update({k: v for k, v in pv.items() if k in ("hunt_loops", "triage_quorum")})
                if spec.get("builder") == "bundle":
                    ok_ids = {a["id"] for a in pipeline.roster(eng, int(vars_.get(rvar, 1)))}
                    if vars_["agent_id"] not in ok_ids:
                        continue
                nid = sid + "".join(f"-{_slug(vars_[k] if k != 'agent' else vars_['agent'])}" for k in mvars)
                if rep:
                    nid += f"-{rvar}{i}"
                node: Dict[str, Any] = {
                    "id": nid, "spec": sid, "kind": str(spec.get("kind", "agentic")),
                    "action": spec.get("action"), "builder": spec.get("builder"), "check": spec.get("check"),
                    "prompt": _subst(spec.get("prompt"), vars_), "file": _subst(spec.get("file"), vars_),
                    "description": str(spec.get("description", "")).strip(),
                    "vars": {k: v for k, v in vars_.items()}, "loop_mode": rmode if rep else None,
                    "repeat_var": rvar if rep else None, "arg": _subst(spec.get("arg"), vars_),
                    "_mkey": tuple(str(vars_.get(k)) for k in mvars),
                    "outputs": [], "_deps": spec.get("depends_on") or [], "index": i if rep else None,
                }
                for o in spec.get("outputs") or []:
                    node["outputs"].append({"name": str(o.get("name")), "path": _subst(str(o.get("path")), vars_),
                                            "schema": o.get("schema"), "primary": bool(o.get("primary"))})
                nodes.append(node)
    # dependencies: resolved against the expanded node list
    by_spec: Dict[str, List[Dict[str, Any]]] = {}
    for n in nodes:
        by_spec.setdefault(n["spec"], []).append(n)
    ids = [n["id"] for n in nodes]
    known_specs = {str(s.get("id")) for s in topo["nodes"]}
    for n in nodes:
        deps: List[str] = []
        for d in n.pop("_deps"):
            if isinstance(d, dict):
                want = {k: _resolve(_subst(v, n["vars"]), pv) for k, v in (d.get("where") or {}).items()}
                for other in by_spec.get(str(d.get("spec")), []):
                    if all(str(other["vars"].get(k)) == str(v) for k, v in want.items()) and other["id"] != n["id"]:
                        deps.append(other["id"])
            else:
                d = str(_subst(d, n["vars"]))
                if d in by_spec:
                    deps += [o["id"] for o in by_spec[d] if o["id"] != n["id"]]
                elif d in ids:
                    deps.append(d)
                elif d in known_specs:
                    continue            # a spec this profile / pack set left out — its dependents simply don't wait on it
                else:
                    hit = [i for i in ids if fnmatch.fnmatch(i, d) and i != n["id"]]
                    if not hit:
                        raise SystemExit(f"sieve campaign: node {n['id']} depends on {d!r}, which matches no node or spec")
                    deps += hit
        if n["loop_mode"] == "series" and n["index"] and n["index"] > 1:
            deps += [o["id"] for o in by_spec[n["spec"]]
                     if o["index"] == n["index"] - 1 and o["_mkey"] == n["_mkey"]]
        n["depends_on"] = list(dict.fromkeys(deps))
    return nodes


def estimate(eng: Engagement, topo: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, int]]:
    """What each profile would dispatch for this engagement: agent runs (the expensive part) and mechanical steps."""
    topo = topo or load_topology(default_topology())
    out: Dict[str, Dict[str, int]] = {}
    for prof in (topo.get("profiles") or {}):
        nodes = expand(topo, eng, prof)
        out[prof] = {"nodes": len(nodes),
                     "agentic": sum(1 for n in nodes if n["kind"] == "agentic"),
                     "meta": sum(1 for n in nodes if n["kind"] == "meta")}
    return out


def validate_topology(nodes: List[Dict[str, Any]]) -> List[str]:
    errs: List[str] = []
    ids = [n["id"] for n in nodes]
    dup = {i for i in ids if ids.count(i) > 1}
    for d in sorted(dup):
        errs.append(f"duplicate node id {d}")
    known = set(ids)
    for n in nodes:
        if n["kind"] not in KINDS:
            errs.append(f"{n['id']}: kind must be one of {KINDS}")
        if n["kind"] == "meta" and not n.get("action"):
            errs.append(f"{n['id']}: a meta node needs `action:`")
        if n["kind"] == "agentic" and not (n.get("prompt") or n.get("builder")):
            errs.append(f"{n['id']}: an agentic node needs `prompt:` or `builder:`")
        if n["kind"] == "reference" and not n.get("file"):
            errs.append(f"{n['id']}: a reference node needs `file:`")
        for d in n["depends_on"]:
            if d not in known:
                errs.append(f"{n['id']}: depends on unknown node {d}")
        outs = n["outputs"]
        if outs:
            prim = [o for o in outs if o["primary"]]
            if len(prim) != 1:
                errs.append(f"{n['id']}: needs exactly one primary output, has {len(prim)}")
            for o in outs:
                s = o.get("schema")
                if s and s not in schema.CONTRACTS and s not in schema.MARKDOWN and s != "rollcall":
                    errs.append(f"{n['id']}: output {o['name']} uses unknown contract {s!r}")
                if re.search(r"\{\w+(?:-\d+)?\}", o["path"]):
                    errs.append(f"{n['id']}: output path {o['path']} has an unresolved variable")
        elif n["kind"] == "agentic":
            errs.append(f"{n['id']}: an agentic node must declare an output (no free-form handoffs)")
    # cycle check (Kahn)
    indeg = {n["id"]: 0 for n in nodes}
    kids: Dict[str, List[str]] = {i: [] for i in ids}
    for n in nodes:
        for d in n["depends_on"]:
            if d in kids:
                indeg[n["id"]] += 1
                kids[d].append(n["id"])
    queue = [i for i, d in indeg.items() if d == 0]
    seen = 0
    while queue:
        cur = queue.pop()
        seen += 1
        for k in kids[cur]:
            indeg[k] -= 1
            if indeg[k] == 0:
                queue.append(k)
    if seen != len(nodes):
        cyc = [i for i, d in indeg.items() if d > 0]
        errs.append(f"dependency cycle among: {', '.join(cyc[:8])}")
    return errs


def topology_hash(nodes: List[Dict[str, Any]]) -> str:
    slim = [{k: n[k] for k in ("id", "kind", "action", "builder", "depends_on", "outputs", "prompt", "check")} for n in nodes]
    return util.sha256_bytes(json.dumps(slim, sort_keys=True).encode())[:16]


# ---------------------------------------------------------------------------- state

def new_state(nodes: List[Dict[str, Any]], profile: str) -> Dict[str, Any]:
    st: Dict[str, Any] = {"version": 1, "profile": profile, "created": util.now_iso(), "topology": topology_hash(nodes),
                          "nodes": {}}
    for n in nodes:
        st["nodes"][n["id"]] = {"status": "done" if n["kind"] == "reference" else "pending", "attempts": 0,
                                "started": None, "finished": util.now_iso() if n["kind"] == "reference" else None,
                                "error": None, "artifacts": {}, "inputs": {}, "note": ""}
    return st


def save(eng: Engagement, st: Dict[str, Any]) -> None:
    util.write_json(state_path(eng), st)


def event(eng: Engagement, node: str, what: str, detail: str = "") -> None:
    os.makedirs(cdir(eng), exist_ok=True)
    with open(cdir(eng, "events.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"time": util.now_iso(), "node": node, "event": what, "detail": detail[:400]}) + "\n")


def load(eng: Engagement, allow_drift: bool = False) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    if not active(eng):
        raise SystemExit("sieve campaign: no campaign here (`sieve campaign init`)")
    st = util.read_json(state_path(eng), {})
    topo = load_topology(cdir(eng, "topology.yml"))
    nodes = expand(topo, eng, st["profile"])
    errs = validate_topology(nodes)
    if errs:
        raise SystemExit("sieve campaign: the topology is invalid:\n  - " + "\n  - ".join(errs))
    if topology_hash(nodes) != st.get("topology") and not allow_drift:
        raise SystemExit("sieve campaign: .sieve/campaign/topology.yml (or the roster) changed since `campaign init`. "
                         "Nodes already done keep their results; run `sieve campaign init --resume` to adopt the new "
                         "topology (new nodes are added as pending, removed ones dropped).")
    return topo, nodes, st


def init(eng: Engagement, profile: str, topology: Optional[str] = None, force: bool = False,
         resume: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    existing = active(eng)
    if existing and not (force or resume):
        raise SystemExit("sieve campaign: a campaign already exists here; `--resume` adopts topology changes, "
                         "`--force` starts over.")
    src = topology or default_topology()
    os.makedirs(cdir(eng, "prompts"), exist_ok=True)
    os.makedirs(cdir(eng, "artifacts"), exist_ok=True)
    if not (existing and resume) or topology:
        shutil.copyfile(src, cdir(eng, "topology.yml"))
    topo = load_topology(cdir(eng, "topology.yml"))
    prev = util.read_json(state_path(eng), {}) if existing else {}
    if resume and prev:
        profile = prev.get("profile", profile)
    nodes = expand(topo, eng, profile)
    errs = validate_topology(nodes)
    if errs:
        raise SystemExit("sieve campaign: the topology is invalid:\n  - " + "\n  - ".join(errs))
    for n in nodes:  # editable copies of every prompt the topology references
        if n.get("prompt"):
            dst = cdir(eng, "prompts", n["prompt"])
            srcp = os.path.join(repo_root(), "campaigns", "prompts", n["prompt"])
            if not os.path.isfile(dst) and os.path.isfile(srcp):
                shutil.copyfile(srcp, dst)
    st = new_state(nodes, profile)
    if resume and prev:
        for nid, ns in (prev.get("nodes") or {}).items():
            if nid in st["nodes"] and ns.get("status") in ("done", "skipped", "running"):
                st["nodes"][nid] = ns
        st["created"] = prev.get("created", st["created"])
    save(eng, st)
    event(eng, "*", "init", f"profile={profile} nodes={len(nodes)} resume={resume}")
    return nodes, st


# ---------------------------------------------------------------------------- scheduling

def artifact_hash(eng: Engagement, node: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for o in node["outputs"]:
        p = eng.path(o["path"])
        contract = schema.MARKDOWN.get(str(o.get("schema")))
        if contract and os.path.isdir(p):
            # hash only the files the contract names — other nodes legitimately add files to the same directory
            h = "".join(util.sha256_file(os.path.join(p, f)) for f in sorted(contract["files"]) if os.path.isfile(os.path.join(p, f)))
            out[o["name"]] = util.sha256_bytes(h.encode())
        elif os.path.isdir(p):
            h = ""
            for base, _d, files in sorted(os.walk(p)):
                for f in sorted(files):
                    h += util.sha256_file(os.path.join(base, f))
            out[o["name"]] = util.sha256_bytes(h.encode())
        elif os.path.isfile(p):
            out[o["name"]] = util.sha256_file(p)
    return out


def effective_status(eng: Engagement, node: Dict[str, Any], st: Dict[str, Any], nodes_by_id: Dict[str, Dict[str, Any]],
                     dep_status: Optional[Dict[str, str]] = None) -> str:
    ns = st["nodes"][node["id"]]
    s = ns["status"]
    if s == "pending":
        deps = [(dep_status or {}).get(d, st["nodes"][d]["status"]) for d in node["depends_on"]]
        if all(x in DONE_LIKE for x in deps):
            return "ready"
        if any(x == "failed" for x in deps):
            return "blocked"
        return "pending"
    if s == "done" and node["outputs"]:
        for name, sha in (ns.get("artifacts") or {}).items():
            cur = artifact_hash(eng, node).get(name)
            if cur != sha:
                return "stale"
        for d, sha in (ns.get("inputs") or {}).items():
            dn = nodes_by_id.get(d)
            if dn and dn["outputs"] and st["nodes"][d]["status"] == "done":
                cur = artifact_hash(eng, dn)
                if util.sha256_bytes(json.dumps(cur, sort_keys=True).encode()) != sha:
                    return "stale"
    return s


def topo_order(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by = {n["id"]: n for n in nodes}
    indeg = {n["id"]: len(n["depends_on"]) for n in nodes}
    kids: Dict[str, List[str]] = {}
    for n in nodes:
        for d in n["depends_on"]:
            kids.setdefault(d, []).append(n["id"])
    queue = [n["id"] for n in nodes if indeg[n["id"]] == 0]
    out: List[Dict[str, Any]] = []
    while queue:
        cur = queue.pop(0)
        out.append(by[cur])
        for k in kids.get(cur, []):
            indeg[k] -= 1
            if indeg[k] == 0:
                queue.append(k)
    return out if len(out) == len(nodes) else list(nodes)


def statuses(eng: Engagement, nodes: List[Dict[str, Any]], st: Dict[str, Any]) -> Dict[str, str]:
    """Effective status of every node, computed dependencies-first so a node whose upstream is stale is not ready."""
    by = {n["id"]: n for n in nodes}
    out: Dict[str, str] = {}
    for n in topo_order(nodes):
        out[n["id"]] = effective_status(eng, n, st, by, out)
    return out


def mark_running(eng: Engagement, st: Dict[str, Any], node: Dict[str, Any], nodes_by_id: Dict[str, Dict[str, Any]]) -> None:
    ns = st["nodes"][node["id"]]
    ns["status"] = "running"
    ns["started"] = util.now_iso()
    ns["attempts"] = int(ns.get("attempts", 0)) + 1
    ins = {}
    for d in node["depends_on"]:
        dn = nodes_by_id[d]
        if dn["outputs"]:
            ins[d] = util.sha256_bytes(json.dumps(artifact_hash(eng, dn), sort_keys=True).encode())
    ns["inputs"] = ins
    event(eng, node["id"], "start", f"attempt {ns['attempts']}")


def mark_done(eng: Engagement, st: Dict[str, Any], node: Dict[str, Any], note: str = "") -> None:
    ns = st["nodes"][node["id"]]
    ns["status"] = "done"
    ns["finished"] = util.now_iso()
    ns["error"] = None
    ns["artifacts"] = artifact_hash(eng, node)
    ns["note"] = note
    event(eng, node["id"], "done", note)


def mark_failed(eng: Engagement, st: Dict[str, Any], node: Dict[str, Any], why: str) -> None:
    ns = st["nodes"][node["id"]]
    ns["status"] = "failed"
    ns["error"] = why[:2000]
    event(eng, node["id"], "failed", why[:300])


def descendants(nodes: List[Dict[str, Any]], root: str) -> List[str]:
    kids: Dict[str, List[str]] = {}
    for n in nodes:
        for d in n["depends_on"]:
            kids.setdefault(d, []).append(n["id"])
    out, stack = [], [root]
    while stack:
        cur = stack.pop()
        for k in kids.get(cur, []):
            if k not in out:
                out.append(k)
                stack.append(k)
    return out


def reset_node(eng: Engagement, st: Dict[str, Any], nodes: List[Dict[str, Any]], nid: str, cascade: bool = True) -> List[str]:
    ids = [nid] + (descendants(nodes, nid) if cascade else [])
    by = {n["id"]: n for n in nodes}
    for i in ids:
        if by[i]["kind"] == "reference":
            continue
        st["nodes"][i].update(status="pending", error=None, started=None, finished=None, artifacts={}, inputs={})
    event(eng, nid, "reset", f"cascade={cascade} n={len(ids)}")
    return ids


# ---------------------------------------------------------------------------- prompts

def _inline(eng: Engagement, node: Dict[str, Any], by: Dict[str, Dict[str, Any]], cap: int = 400) -> str:
    """Upstream artifacts, verbatim (capped), so the agent starts from what earlier nodes produced."""
    parts: List[str] = []
    for d in node["depends_on"]:
        dn = by[d]
        if dn["kind"] == "reference" and dn.get("file"):
            p = os.path.join(repo_root(), dn["file"])
            if os.path.isfile(p):
                parts.append(f"### reference: {dn['file']}\n\n{util.read_text(p)}")
            continue
        for o in dn["outputs"]:
            p = eng.path(o["path"])
            if os.path.isdir(p) or not os.path.isfile(p) or not o["path"].endswith((".json", ".md", ".txt")):
                continue
            text = util.read_text(p)
            lines = text.split("\n")
            more = f"\n… ({len(lines) - cap} more lines in .sieve/{o['path']})" if len(lines) > cap else ""
            parts.append(f"### {d} → {o['path']}\n\n```\n" + "\n".join(lines[:cap]) + f"\n```{more}")
    return "\n\n".join(parts) or "_(no upstream artifacts)_"


def findings_block(eng: Engagement, mode: str) -> str:
    """Findings rendered for the prompts that judge or prove them: `candidates` (awaiting a verdict — the
    discoverer is deliberately hidden), `cleared` (passed Gates 0-5, awaiting proof), `proven` (with the
    receipts the engine wrote, for the independence audit)."""
    from . import validate
    from .flow import _unjudged
    judged = validate.load_judged(eng)
    ids = validate.all_finding_ids(eng)
    if mode == "candidates":
        want = set(_unjudged(eng))
    elif mode == "cleared":
        want = {i for i in ids if (judged.get(i) or {}).get("gates") == "cleared" and (judged.get(i) or {}).get("verdict") in ("cleared", None)}
    else:
        want = {i for i in ids if any(r.get("kind") == "exec" for r in validate.receipts(eng, i))}
    out: List[str] = []
    for fid in ids:
        if fid not in want:
            continue
        meta, body = validate.finding_meta(eng, fid)
        if meta.get("kind") != "FINDING":
            continue
        j = judged.get(fid) or {}
        head = (f"#### {fid} — {meta.get('title')}\n- class: {meta.get('class')} · component: {meta.get('component')} · "
                f"proposed severity: {j.get('severity') or meta.get('severity')} · proposed confidence: {meta.get('confidence')}")
        extra = ""
        if mode == "cleared":
            extra = "\n- gate reasoning: " + " | ".join(f"{v['verifier']}: {str(v.get('reason'))[:160]}" for v in j.get("votes", [])[:3])
        if mode == "proven":
            for r in validate.receipts(eng, fid):
                if r.get("kind") == "exec":
                    ctl = r.get("control") or {}
                    extra += (f"\n- proof `{r.get('oracle')}`: cmd `{r.get('cmd')}`; expects `{r.get('expect')}`; verdict {r.get('verdict')}; "
                              f"control kinds {ctl.get('kinds') or ['waived']}; control cmd `{ctl.get('cmd')}`; patch files "
                              f"{(ctl.get('patch') or {}).get('files_changed', [])}; PoC files {list((r.get('poc_files') or {}).keys())}")
        out.append(head + extra + "\n\n" + body.strip())
    return "\n\n---\n\n".join(out) or "_(none)_"


def render_prompt(eng: Engagement, node: Dict[str, Any], nodes: List[Dict[str, Any]], profile: str) -> Tuple[str, int]:
    by = {n["id"]: n for n in nodes}
    st = eng.load()
    ndir = cdir(eng, "nodes", node["id"])
    os.makedirs(ndir, exist_ok=True)
    out_path = os.path.join(ndir, "prompt.md")
    v = dict(node["vars"], profile=profile, node=node["id"], packs=",".join(st["packs"]), engagement=st["id"])
    head = (f"<!-- SIEVE CAMPAIGN NODE · {node['id']} · profile {profile} · engagement {st['id']} · {util.now_iso()} -->\n"
            f"# Campaign node — `{node['id']}`\n\nEngagement `{st['name']}` · packs {v['packs']}. "
            f"{node['description']}\n")
    if node.get("builder") == "bundle":
        loop = int(node["vars"].get("loop", 1))
        agent = next(a for a in pipeline.roster(eng, loop) if a["id"] == node["vars"]["agent_id"])
        bpath, blines, sha = pipeline.build_bundle(eng, loop, agent)
        man = util.read_json(eng.path("bundles", f"manifest-{loop}.json"), {}) or {}
        man[agent["slug"]] = {"lines": blines, "sha256": sha}
        util.write_json(eng.path("bundles", f"manifest-{loop}.json"), man)
        body = pipeline.dispatch_prompt(os.path.relpath(bpath, eng.root), blines, agent["slug"], loop)
        text = head + "\n" + body + "\n"
        util.atomic_write(out_path, text)
        return out_path, blines
    if node.get("builder") == "roaming":
        loop = int(eng.load().get("pass_current") or 1)
        bpath, blines, _ = pipeline.build_roaming_bundle(eng, loop)
        body = pipeline.dispatch_prompt(os.path.relpath(bpath, eng.root), blines, "roaming", loop)
        text = head + "\n" + body + "\n"
        util.atomic_write(out_path, text)
        return out_path, blines
    ppath = prompt_search(eng, node["prompt"])
    if not os.path.isfile(ppath):
        raise SystemExit(f"sieve campaign: prompt {node['prompt']} not found (looked in {ppath})")
    task = util.read_text(ppath)
    for k, val in v.items():
        task = task.replace("{{" + k + "}}", str(val))
    for tag in ("candidates", "cleared", "proven"):
        if "{{" + tag + "}}" in task:
            task = task.replace("{{" + tag + "}}", findings_block(eng, tag))
    contracts = "\n\n".join(schema.describe(o["schema"]) for o in node["outputs"] if o.get("schema") and o["schema"] != "rollcall")
    outs = "\n".join(f"- `{eng.path(o['path'])}`" + (" (primary)" if o["primary"] else "") for o in node["outputs"])
    shared = util.read_text(os.path.join(repo_root(), "references", "shared-rules.md"))
    hc = util.read_text(os.path.join(repo_root(), "references", "hypothesis-craft.md"))
    text = "\n".join([
        head, "## Your task\n", task.strip(), "\n## Inputs from earlier nodes\n", _inline(eng, node, by),
        "\n## Scope card (the fence — `.sieve/case.md`)\n", card_for_prompt(eng, "_(none)_"),
        "\n## Output\n", f"Write these files, exactly:\n{outs}\n", contracts,
        "\nThe engine validates the file(s) before this node counts as done; a rejected artifact comes back to you with "
        "the exact errors. Your last action: `sieve campaign submit " + node["id"] + "`.",
        "\n## How to think and what you may claim\n", "### references/hypothesis-craft.md\n\n" + hc,
        "### references/shared-rules.md\n\n" + shared])
    util.atomic_write(out_path, text)
    return out_path, text.count("\n") + 1


# ---------------------------------------------------------------------------- next-action text for flow/hook

def next_action(eng: Engagement) -> Tuple[str, str]:
    try:
        _topo, nodes, st = load(eng, allow_drift=True)
    except SystemExit as exc:
        return "Fix the campaign", str(exc)
    sts = statuses(eng, nodes, st)
    ready = [n for n in nodes if sts[n["id"]] == "ready"]
    running = [n for n in nodes if sts[n["id"]] == "running"]
    failed = [n for n in nodes if sts[n["id"]] == "failed"]
    stale = [n for n in nodes if sts[n["id"]] == "stale"]
    total = len(nodes)
    done = sum(1 for n in nodes if sts[n["id"]] in DONE_LIKE)
    prog = f"campaign {done}/{total} nodes done"
    if all(sts[n["id"]] in DONE_LIKE for n in nodes):
        return "Campaign complete", f"{prog}. `sieve finish` (frontier drained + report + map required)."
    if failed:
        return ("A campaign node failed",
                f"{prog}. `sieve campaign status` — {failed[0]['id']}: {st['nodes'][failed[0]['id']]['error']}. "
                "Fix the cause and `sieve campaign retry <node>` (or `sieve campaign skip <node> --reason ...`).")
    if stale:
        return "Stale nodes", f"{prog}. Upstream artifacts changed under: {', '.join(n['id'] for n in stale[:5])} — `sieve campaign run --rerun-stale`."
    meta_ready = [n for n in ready if n["kind"] == "meta"]
    if meta_ready:
        return "Run the mechanical nodes", f"{prog}. `sieve campaign run` (ready: {', '.join(n['id'] for n in meta_ready[:5])})."
    agentic_ready = [n for n in ready if n["kind"] == "agentic"]
    if agentic_ready:
        return ("Dispatch agents",
                f"{prog}. `sieve campaign next` renders {len(agentic_ready)} prompt(s) — spawn them ALL in ONE message "
                f"(ready: {', '.join(n['id'] for n in agentic_ready[:6])}{'…' if len(agentic_ready) > 6 else ''}), "
                "then `sieve campaign run` once they return.")
    if running:
        return ("Agents are running",
                f"{prog}. Waiting on: {', '.join(n['id'] for n in running[:6])}. When they have written their artifacts: "
                "`sieve campaign run` (it validates and advances).")
    return "Campaign idle", prog
