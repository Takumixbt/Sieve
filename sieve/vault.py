"""Obsidian wiring — plain markdown, [[wikilinks]], YAML tags. Nothing here reads Obsidian's state.

Two vaults, one convention:

* the **knowledge vault** (`kb.vault`, default `~/.sieve/kb`): every card links to its vector card,
  its bug-class hub, its domain hub and the engagements that used it, so the graph view clusters
  what has actually paid;
* the **engagement vault** (`.sieve/vault/`, from `sieve vault export`): the audit as a graph —
  components, invariants, findings, dead ends and hypotheses, all interlinked.

Note names are unique on purpose (F-001, INV-3, R-0007, C-<component>, SV-<engagement>), so
Obsidian's shortest-path link resolution never guesses. The export is mechanical: it reshapes files
the audit already wrote; it never decides anything.
"""
from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, Dict, Iterable, List, Tuple

from . import frontier, util, vectors, yamlish
from .state import Engagement

LINKS_HEADING = "## Links"
_RGB = {"finding": 0xE5484D, "confirmed": 0xE5484D, "lead": 0xF76B15, "deadend": 0x8B8D98, "invariant": 0x3E63DD,
        "unprobed": 0xFFB224, "component": 0x30A46C, "vector": 0xF5A623, "lesson": 0x8E4EC6, "engagement": 0xFFFFFF,
        "hypothesis": 0x12A594, "report": 0x0091FF, "hub": 0x6E56CF}


def slug(text: str, maxlen: int = 48) -> str:
    return util.slug(text, maxlen) or "x"


def link(name: str, alias: str = "") -> str:
    return f"[[{name}|{alias}]]" if alias and alias != name else f"[[{name}]]"


# ------------------------------------------------------------------ vault scaffolding

def _write_if_missing(path: str, data: str) -> bool:
    if os.path.exists(path):
        return False
    util.atomic_write(path, data)
    return True


def init_scaffold(root: str, tags: Iterable[str] = _RGB) -> None:
    """A minimal `.obsidian/` so the graph opens coloured by note type. Never overwrites an
    existing config — a user's own Obsidian settings win."""
    _write_if_missing(os.path.join(root, ".obsidian", "app.json"),
                      json.dumps({"useMarkdownLinks": False, "newLinkFormat": "shortest",
                                  "alwaysUpdateLinks": True}, indent=2) + "\n")
    groups = [{"query": f"tag:#{t}", "color": {"a": 1, "rgb": _RGB[t]}} for t in tags if t in _RGB]
    _write_if_missing(os.path.join(root, ".obsidian", "graph.json"),
                      json.dumps({"colorGroups": groups, "showTags": False, "showAttachments": False,
                                  "hideUnresolved": False, "showOrphans": True}, indent=2) + "\n")


# ------------------------------------------------------------------ knowledge vault

def links_block(meta: Dict[str, Any]) -> str:
    """The `## Links` footer every KB card carries. Deterministic from frontmatter, so rewriting
    it on merge is idempotent."""
    out: List[str] = []
    if meta.get("vector"):
        out.append(f"- vector: {link(str(meta['vector']))}")
    if meta.get("class"):
        out.append(f"- class: {link('class-' + slug(str(meta['class'])), str(meta['class']))}")
    if meta.get("domain"):
        out.append(f"- domain: {link('domain-' + slug(str(meta['domain'])), str(meta['domain']))}")
    for u in meta.get("used_in") or []:
        eng = str(u).split(":")[0]
        if eng:
            out.append(f"- used in: {link(eng)}" + (f" · {link(str(u).split(':', 1)[1])}" if ":" in str(u) else ""))
    if not out:
        return ""
    return LINKS_HEADING + "\n" + "\n".join(out) + "\n"


def with_links(body: str, meta: Dict[str, Any]) -> str:
    """Replace (or append) the trailing `## Links` block."""
    body = re.split(rf"(?m)^{re.escape(LINKS_HEADING)}\s*$", body)[0].rstrip()
    block = links_block(meta)
    return f"{body}\n\n{block}" if block else body + "\n"


def _hub(root: str, name: str, kind: str, title: str, desc: str) -> None:
    path = os.path.join(root, "_hubs", f"{name}.md")
    if os.path.exists(path):
        return
    util.atomic_write(path, yamlish.join_frontmatter({"tags": ["hub", kind]},
                                                     f"# {title}\n\n{desc}\n"))


def init_kb_vault(vault: str) -> Tuple[int, int]:
    """Scaffold the knowledge vault, materialise vector cards as linkable notes, create the hub
    notes the cards point at, and refresh every card's Links block. Returns (vector notes, cards)."""
    os.makedirs(vault, exist_ok=True)
    init_scaffold(vault)
    n_vec = 0
    packs = set()
    groups = set()
    for c in vectors.load_all():
        packs.add(c["pack"])
        groups.add(c["group"])
        meta = {"vector": c["id"], "pack": c["pack"], "sev": c.get("sev", ""), "cwe": c.get("cwe", ""),
                "tags": ["vector", c["pack"]]}
        body = [f"# {c['id']} · {c['title']}", ""]
        for k in ("signal", "attack", "chain", "proof", "fp", "kb"):
            if c.get(k):
                body.append(f"**{k}** — {c[k]}")
                body.append("")
        body += [LINKS_HEADING, f"- domain: {link('domain-' + slug(c['pack']), c['pack'])}",
                 f"- class: {link('class-' + slug(c['group'].lower()), c['group'])}", ""]
        util.atomic_write(os.path.join(vault, "vectors", f"{c['id']}.md"),
                          yamlish.join_frontmatter(meta, "\n".join(body)))
        n_vec += 1
    for p in packs:
        _hub(vault, f"domain-{slug(p)}", "domain", f"Domain — {p}", f"Everything the knowledge base holds for {p}.")
    for g in groups:
        _hub(vault, f"class-{slug(g.lower())}", "class", f"Class — {g}", "Cards and vector cards of this bug class.")
    n_cards = 0
    for path in glob.glob(os.path.join(vault, "**", "*.md"), recursive=True):
        rel = os.path.relpath(path, vault)
        if rel.startswith(("vectors", "_hubs", ".obsidian")):
            continue
        meta, body = yamlish.split_frontmatter(util.read_text(path))
        if not meta.get("id"):
            continue
        for key, kind in (("class", "class"), ("domain", "domain")):
            if meta.get(key):
                _hub(vault, f"{kind}-{slug(str(meta[key]))}", kind, f"{kind.title()} — {meta[key]}",
                     "Cards of this " + kind + ".")
        new = with_links(body, meta)
        if new.strip() != body.strip():
            util.atomic_write(path, yamlish.join_frontmatter(meta, new))
        n_cards += 1
    return n_vec, n_cards


# ------------------------------------------------------------------ engagement vault

_INV = re.compile(r"(?m)^(?:[#>\-*\s]*\**)(INV-\d+)\**\b[:.\s-]*(.*)$")
_HYP = re.compile(r"(?m)^HYPOTHESIS\s*\|(.*)$")


def _field(header: str, key: str) -> str:
    m = re.search(rf"\b{key}:\s*([^|]+)", header)
    return m.group(1).strip() if m else ""


def _invariants(eng: Engagement) -> List[Tuple[str, str]]:
    p = eng.path("xray", "invariants.md")
    if not os.path.isfile(p):
        return []
    text = util.read_text(p)
    hits = list(_INV.finditer(text))
    out = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        out.append((m.group(1), (m.group(2) + text[m.end():end]).strip()))
    return out


def _hypotheses(eng: Engagement) -> List[Dict[str, str]]:
    out = []
    for p in sorted(glob.glob(eng.path("raw", "*.md"))):
        agent = os.path.basename(p)[:-3]
        text = util.read_text(p)
        for n, m in enumerate(_HYP.finditer(text), 1):
            tail = text[m.end():m.end() + 900].split("\n\n")[0]
            out.append({"id": f"H-{slug(agent, 24)}-{n}", "agent": agent, "component": _field(m.group(1), "component"),
                        "class": _field(m.group(1), "class"), "pack": _field(m.group(1), "pack"),
                        "detail": tail.strip()})
    return out


def _mentions(text: str, component: str) -> bool:
    """A component is mentioned by its full name, or by its member name when that is distinctive."""
    tail = re.split(r"[.:/]", component)[-1]
    return bool(component) and (component in text or (len(tail) >= 5 and tail in text))


def _ids_in(text: str, pattern: str) -> List[str]:
    return sorted(set(re.findall(pattern, text)))


def namespace(eng: Engagement) -> str:
    """The prefix that keeps this engagement's note names unique inside a vault shared by every engagement
    (`F-001` exists in all of them). Readable target name plus the engagement's own random suffix."""
    st = eng.load()
    return f"{slug(str(st.get('name') or 'target'), 16)}-{str(st['id']).split('-')[-1]}"


def vault_root(cfg: Any) -> str:
    """The single Sieve vault: $SIEVE_VAULT, else `vault.root` from config, else Documents/Sieve Vault (OneDrive's
    Documents when that is where Documents lives), else ~/.sieve/vault."""
    env = os.environ.get("SIEVE_VAULT")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    conf = str(cfg.get("vault.root", "") or "")
    if conf:
        return os.path.abspath(os.path.expanduser(os.path.expandvars(conf)))
    home = os.path.expanduser("~")
    for docs in (os.path.join(home, "OneDrive", "Documents"), os.path.join(home, "Documents")):
        if os.path.isdir(os.path.join(docs, "Sieve Vault")):
            return os.path.join(docs, "Sieve Vault")
    for docs in (os.path.join(home, "OneDrive", "Documents"), os.path.join(home, "Documents")):
        if os.path.isdir(docs):
            return os.path.join(docs, "Sieve Vault")
    return os.path.join(home, ".sieve", "vault")


ROOT_NOTE = "Sieve"
PLAN_KINDS = {"goal", "invariant", "strategy", "roaming", "seam"}


def init_root(root: str) -> None:
    """The vault's front door: a root note every engagement and the knowledge base hang off."""
    init_scaffold(root)
    path = os.path.join(root, f"{ROOT_NOTE}.md")
    if not os.path.exists(path):
        util.atomic_write(path, yamlish.join_frontmatter({"tags": ["hub", "root"]}, "\n".join([
            f"# {ROOT_NOTE}", "",
            "The single vault for every Sieve audit. The knowledge base lives under `KB/` (cards, vector notes, class and "
            "domain hubs); each engagement is a folder under `Engagements/` with its invariants, findings, dead ends and "
            "hypotheses as linked notes. Open the graph and filter by tag: `unprobed` invariants are the audit's coverage "
            "gaps, `confirmed` findings are what survived the machine's proof.", "",
            "## Engagements", "", "_none yet_", "",
            f"Live views (Dataview): {link('_Dashboard')}", ""])))
    dash = os.path.join(root, "_Dashboard.md")
    if not os.path.exists(dash):
        util.atomic_write(dash, DASHBOARD)


DASHBOARD = """---
tags: [hub, dashboard]
---

# Dashboard

Needs the Dataview community plugin. Everything here is derived from the notes; nothing is typed by hand.

## Findings by severity

```dataview
TABLE severity, status, class, component
FROM #finding
SORT severity ASC
```

## Confirmed by the machine

```dataview
TABLE severity, class, confidence
FROM #confirmed
SORT confidence DESC
```

## Audit gaps: invariants nobody has probed

```dataview
TABLE engagement, coverage
FROM #unprobed
```

## Engagements

```dataview
TABLE packs, unprobed
FROM #engagement
```
"""


def _register_engagement(root: str, eid: str, moc: str, name: str, packs: str, counts: Dict[str, int]) -> None:
    path = os.path.join(root, f"{ROOT_NOTE}.md")
    meta, body = yamlish.split_frontmatter(util.read_text(path)) if os.path.exists(path) else ({"tags": ["hub", "root"]}, f"# {ROOT_NOTE}\n\n## Engagements\n")
    line = f"- {link(moc, name)} ({packs}): " + ", ".join(f"{v} {k}" for k, v in counts.items() if v)
    lines = [l for l in body.split("\n") if not l.startswith(f"- [[{moc}")]
    if "## Engagements" not in "\n".join(lines):
        lines += ["", "## Engagements"]
    out: List[str] = []
    for l in lines:
        if l.strip() == "_none yet_":
            continue
        out.append(l)
        if l.strip() == "## Engagements":
            out += ["", line]
    util.atomic_write(path, yamlish.join_frontmatter(meta, "\n".join(out).rstrip() + "\n"))


def export_engagement(eng: Engagement, out_dir: str = "", kb_root: str = "", root: str = "") -> Dict[str, int]:
    """Write the audit as a linked note graph. Note names carry the engagement namespace, so any number of
    engagements can share one vault. Everything is derived from files the audit already wrote: this decides nothing."""
    out = out_dir or eng.path("vault")
    st = eng.load()
    eid = st["id"]
    ns = namespace(eng)
    if not root:                      # inside the shared vault the root already carries the one .obsidian config
        init_scaffold(out)

    def nm(x: str) -> str:
        return f"{ns}-{x}"

    def ln(x: str, alias: str = "") -> str:
        return link(nm(x), alias or x)

    rows = frontier.load(eng)
    comps: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        if r["kind"] in PLAN_KINDS:      # goals, invariants and strategies have their own notes; they are not code components
            continue
        comps.setdefault(r["component"], []).append(r)
    comp_name = {c: f"C-{slug(c, 36)}-{util.sha256_bytes(c.encode())[:4]}" for c in comps}
    invs = _invariants(eng)
    inv_ids = {i for i, _ in invs}
    hyps = _hypotheses(eng)
    counts = {"components": 0, "invariants": 0, "findings": 0, "leads": 0, "deadends": 0, "hypotheses": 0}

    def note(sub: str, name: str, meta: Dict[str, Any], body: str) -> None:
        util.atomic_write(os.path.join(out, sub, f"{nm(name)}.md"), yamlish.join_frontmatter(meta, body))

    classes_seen: Dict[str, int] = {}
    # findings first: components and invariants link back to them
    findings: List[Tuple[str, Dict[str, Any]]] = []
    ftext: Dict[str, str] = {}
    for f in sorted(glob.glob(eng.path("findings", "*.md"))):
        meta, body = yamlish.split_frontmatter(util.read_text(f))
        fid = str(meta.get("id") or os.path.basename(f)[:-3])
        if not re.fullmatch(r"[A-Z]+-\d+", fid):
            continue
        findings.append((fid, meta))
        ftext[fid] = body
        refs = [f"- engagement: {link(eid)}"]
        if meta.get("vector"):
            refs.append(f"- vector: {link(str(meta['vector']))}")
        klass = str(meta.get("class") or "")
        if klass:
            refs.append(f"- class: {link('class-' + slug(klass), klass)}")
            classes_seen[klass] = classes_seen.get(klass, 0) + 1
            if kb_root:
                _hub(kb_root, f"class-{slug(klass)}", "class", f"Class: {klass}", "Cards and vector cards of this bug class.")
        if meta.get("component") in comp_name:
            refs.append(f"- component: {ln(comp_name[meta['component']], str(meta['component']))}")
        for iv in _ids_in(body + str(meta.get("gate", "")), r"INV-\d+"):
            if iv in inv_ids:
                refs.append(f"- invariant: {ln(iv)}")
        is_lead = str(meta.get("kind", "FINDING")) == "LEAD"
        tags = ["lead" if is_lead else "finding", str(meta.get("severity", "")), str(meta.get("pack", ""))]
        if meta.get("status") == "confirmed":
            tags.append("confirmed")
        note("findings", fid, dict(meta, tags=[t for t in tags if t]),
             body.rstrip() + "\n\n" + LINKS_HEADING + "\n" + "\n".join(refs) + "\n")
        counts["leads" if is_lead else "findings"] += 1
    by_comp: Dict[str, List[str]] = {}
    for fid, meta in findings:
        by_comp.setdefault(str(meta.get("component", "")), []).append(fid)

    for c, rs in comps.items():
        lines = [f"# {c}", "", "| row | lens | status | note |", "|---|---|---|---|"]
        for r in rs:
            lines.append(f"| {r['id']} | {r['lens']} | {r['status']} | {r['note'][:90].replace('|', '/')} |")
        lines += ["", LINKS_HEADING, f"- engagement: {link(eid)}"]
        for fid in by_comp.get(c, []):
            lines.append(f"- finding: {ln(fid)}")
        for r in rs:
            if r["status"] in ("dead", "blocked") or r["status"] == "done" and r["note"].startswith("clean"):
                lines.append(f"- dead end: {ln(r['id'])}")
        for iv, txt in invs:
            if _mentions(txt, c):
                lines.append(f"- invariant: {ln(iv)}")
        note("components", comp_name[c], {"tags": ["component", rs[0].get("pack", "")], "component": c}, "\n".join(lines) + "\n")
        counts["components"] += 1

    # An invariant is a promise the audit must probe. Its coverage state comes from the frontier row seeded for it
    # and from the findings that cite it, so a promise nobody examined is visible as an `unprobed` note.
    inv_rows: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        m = re.match(r"(INV-\d+)\b", r["component"])
        if r["kind"] == "invariant" and m:
            inv_rows.setdefault(m.group(1), []).append(r)
    unprobed: List[str] = []
    for iv, txt in invs:
        cited = [fid for fid, _m in findings if iv in ftext.get(fid, "")]
        rs = inv_rows.get(iv, [])
        if cited:
            state = "broken"
        elif rs and all(r["status"] == "done" for r in rs):
            state = "clean"
        elif rs and all(r["status"] in ("done", "dead") for r in rs):
            state = "dead-end"
        else:
            state = "unprobed"
            unprobed.append(iv)
        refs = [f"- engagement: {link(eid)}"]
        for c in comps:
            if _mentions(txt, c):
                refs.append(f"- component: {ln(comp_name[c], c)}")
        for fid in cited:
            refs.append(f"- finding: {ln(fid)}")
        for r in rs:
            refs.append(f"- frontier row: {r['id']} ({r['status']})")
        note("invariants", iv, {"tags": ["invariant", state if state != "unprobed" else "unprobed"], "coverage": state},
             f"# {iv}\n\n**coverage: {state}**\n\n{txt}\n\n{LINKS_HEADING}\n" + "\n".join(refs) + "\n")
        counts["invariants"] += 1

    for r in rows:
        if r["status"] not in ("dead", "blocked") and not (r["status"] == "done" and r["note"].startswith("clean")):
            continue
        att = frontier.attempts(eng, r["id"])
        rungs = sorted({a["rung"] for a in att})
        body = [f"# {r['id']}: {r['component']} ({r['lens']})", "", f"**{r['status']}**: {r['note']}", "", "## Attempts"]
        body += [f"{i}. `{a['rung']}`: {a['note']}" for i, a in enumerate(att, 1)] or ["_none logged_"]
        body += ["", LINKS_HEADING, f"- engagement: {link(eid)}"]
        if r["component"] in comp_name:
            body.append(f"- component: {ln(comp_name[r['component']], r['component'])}")
        inv = re.match(r"(INV-\d+)\b", r["component"])
        if inv and inv.group(1) in inv_ids:
            body.append(f"- invariant: {ln(inv.group(1))}")
        body += [f"- rung: {link('rung-' + rg, rg)}" for rg in rungs]
        note("deadends", r["id"], {"tags": ["deadend", r["status"]], "pack": r.get("pack", "")}, "\n".join(body) + "\n")
        for rg in rungs:
            _hub(kb_root or out, f"rung-{rg}", "rung", f"Ladder rung: {rg}", frontier.LADDER.get(rg, ""))
        counts["deadends"] += 1

    for h in hyps:
        body = [f"# {h['id']}", "", "```", h["detail"], "```", "", LINKS_HEADING, f"- engagement: {link(eid)}"]
        if h["component"] in comp_name:
            body.append(f"- component: {ln(comp_name[h['component']], h['component'])}")
        note("hypotheses", h["id"], {"tags": ["hypothesis", h["pack"]], "agent": h["agent"]}, "\n".join(body) + "\n")
        counts["hypotheses"] += 1

    report_path = eng.path("report", "report.md")
    has_report = os.path.isfile(report_path)
    if has_report:
        note("", "Report", {"tags": ["report"], "engagement": eid},
             util.read_text(report_path).rstrip() + f"\n\n{LINKS_HEADING}\n- engagement: {link(eid)}\n")

    stats = frontier.stats(eng)
    moc = [f"# {st.get('name', '')} ({eid})", "",
           f"packs: {', '.join(st.get('packs', []))} · phase: **{st.get('phase')}** · frontier: {json.dumps(stats)}", "",
           f"Up: {link(ROOT_NOTE)}", ""]
    if invs:
        moc += ["## Coverage", "",
                f"{len(invs) - len(unprobed)} of {len(invs)} invariants probed. "
                + ("Unprobed (no receipt yet, the audit's gaps): " + ", ".join(ln(i) for i in unprobed) if unprobed
                   else "Every invariant has a receipt."), ""]
    for title, names, mk in (
            ("Components", sorted(set(comp_name.values())), ln),
            ("Invariants", [i for i, _ in invs], ln),
            ("Findings", [f for f, m in findings if str(m.get("kind", "FINDING")) != "LEAD"], ln),
            ("Leads", [f for f, m in findings if str(m.get("kind", "FINDING")) == "LEAD"], ln),
            ("Dead ends", sorted(r["id"] for r in rows if os.path.isfile(os.path.join(out, "deadends", nm(r["id"]) + ".md"))), ln),
            ("Hypotheses", [h["id"] for h in hyps], ln)):
        moc += [f"## {title}", ""] + ([f"- {mk(n)}" for n in names] or ["_none_"]) + [""]
    if classes_seen:
        moc += ["## Classes found", ""] + [f"- {link('class-' + slug(c), c)} ({n})" for c, n in sorted(classes_seen.items())] + [""]
    if has_report:
        moc += ["## Report", "", f"- {ln('Report')}", ""]
    util.atomic_write(os.path.join(out, f"{eid}.md"), yamlish.join_frontmatter(
        {"tags": ["engagement"], "engagement": eid, "packs": list(st.get("packs", [])), "unprobed": len(unprobed)}, "\n".join(moc)))
    if root:
        _register_engagement(root, eid, eid, str(st.get("name", eid)), ",".join(st.get("packs", [])), counts)
    counts["unprobed_invariants"] = len(unprobed)
    return counts
