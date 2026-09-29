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
_RGB = {"finding": 0xE5484D, "confirmed": 0xE5484D, "deadend": 0x8B8D98, "invariant": 0x3E63DD,
        "component": 0x30A46C, "vector": 0xF5A623, "lesson": 0x8E4EC6, "engagement": 0xFFFFFF,
        "hypothesis": 0x12A594}


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


def export_engagement(eng: Engagement, out_dir: str = "") -> Dict[str, int]:
    out = out_dir or eng.path("vault")
    st = eng.load()
    eid = st["id"]
    init_scaffold(out)
    rows = frontier.load(eng)
    comps: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        comps.setdefault(r["component"], []).append(r)
    comp_name = {c: "C-" + slug(c) for c in comps}
    invs = _invariants(eng)
    inv_ids = {i for i, _ in invs}
    hyps = _hypotheses(eng)
    counts = {"components": 0, "invariants": 0, "findings": 0, "deadends": 0, "hypotheses": 0}

    def note(sub: str, name: str, meta: Dict[str, Any], body: str) -> None:
        util.atomic_write(os.path.join(out, sub, f"{name}.md"), yamlish.join_frontmatter(meta, body))

    # findings first — components and invariants link back to them
    findings: List[Tuple[str, Dict[str, Any]]] = []
    ftext: Dict[str, str] = {}
    for f in sorted(glob.glob(eng.path("findings", "*.md"))):
        meta, body = yamlish.split_frontmatter(util.read_text(f))
        fid = str(meta.get("id") or os.path.basename(f)[:-3])
        findings.append((fid, meta))
        ftext[fid] = body
        refs = [f"- engagement: {link(eid)}"]
        if meta.get("vector"):
            refs.append(f"- vector: {link(str(meta['vector']))}")
        if meta.get("component") in comp_name:
            refs.append(f"- component: {link(comp_name[meta['component']], str(meta['component']))}")
        for iv in _ids_in(body + str(meta.get("gate", "")), r"INV-\d+"):
            if iv in inv_ids:
                refs.append(f"- invariant: {link(iv)}")
        tags = ["finding", str(meta.get("severity", "")), str(meta.get("pack", ""))]
        if meta.get("status") == "confirmed":
            tags.append("confirmed")
        note("findings", fid, dict(meta, tags=[t for t in tags if t]), body.rstrip() + "\n\n" + LINKS_HEADING + "\n" + "\n".join(refs) + "\n")
        counts["findings"] += 1
    by_comp: Dict[str, List[str]] = {}
    for fid, meta in findings:
        by_comp.setdefault(str(meta.get("component", "")), []).append(fid)

    for c, rs in comps.items():
        lines = [f"# {c}", "", "| row | lens | status | note |", "|---|---|---|---|"]
        for r in rs:
            lines.append(f"| {r['id']} | {r['lens']} | {r['status']} | {r['note'][:90].replace('|', '/')} |")
        lines += ["", LINKS_HEADING, f"- engagement: {link(eid)}"]
        for fid in by_comp.get(c, []):
            lines.append(f"- finding: {link(fid)}")
        for r in rs:
            if r["status"] in ("dead", "blocked") or r["status"] == "done" and r["note"].startswith("clean"):
                lines.append(f"- dead end: {link(r['id'])}")
        for iv, txt in invs:
            if _mentions(txt, c):
                lines.append(f"- invariant: {link(iv)}")
        note("components", comp_name[c], {"tags": ["component", rs[0].get("pack", "")], "component": c}, "\n".join(lines) + "\n")
        counts["components"] += 1

    for iv, txt in invs:
        refs = [f"- engagement: {link(eid)}"]
        for c in comps:
            if _mentions(txt, c):
                refs.append(f"- component: {link(comp_name[c], c)}")
        for fid, _meta in findings:
            if iv in ftext.get(fid, ""):
                refs.append(f"- finding: {link(fid)}")
        note("invariants", iv, {"tags": ["invariant"]}, f"# {iv}\n\n{txt}\n\n{LINKS_HEADING}\n" + "\n".join(refs) + "\n")
        counts["invariants"] += 1

    for r in rows:
        if r["status"] not in ("dead", "blocked") and not (r["status"] == "done" and r["note"].startswith("clean")):
            continue
        att = frontier.attempts(eng, r["id"])
        rungs = sorted({a["rung"] for a in att})
        body = [f"# {r['id']} · {r['component']} ({r['lens']})", "", f"**{r['status']}** — {r['note']}", "", "## Attempts"]
        body += [f"{i}. `{a['rung']}` — {a['note']}" for i, a in enumerate(att, 1)] or ["_none logged_"]
        body += ["", LINKS_HEADING, f"- engagement: {link(eid)}", f"- component: {link(comp_name[r['component']], r['component'])}"]
        body += [f"- rung: {link('rung-' + rg, rg)}" for rg in rungs]
        note("deadends", r["id"], {"tags": ["deadend", r["status"]], "pack": r.get("pack", "")}, "\n".join(body) + "\n")
        for rg in rungs:
            _hub(out, f"rung-{rg}", "rung", f"Ladder rung — {rg}", frontier.LADDER.get(rg, ""))
        counts["deadends"] += 1

    for h in hyps:
        body = [f"# {h['id']}", "", "```", h["detail"], "```", "", LINKS_HEADING, f"- engagement: {link(eid)}"]
        if h["component"] in comp_name:
            body.append(f"- component: {link(comp_name[h['component']], h['component'])}")
        note("hypotheses", h["id"], {"tags": ["hypothesis", h["pack"]], "agent": h["agent"]}, "\n".join(body) + "\n")
        counts["hypotheses"] += 1

    stats = frontier.stats(eng)
    moc = [f"# {eid} — {st.get('name', '')}", "",
           f"packs: {', '.join(st.get('packs', []))} · phase: **{st.get('phase')}** · frontier: {json.dumps(stats)}", ""]
    for title, sub, names in (("Components", "components", sorted(comp_name.values())),
                              ("Invariants", "invariants", [i for i, _ in invs]),
                              ("Findings", "findings", [f for f, _ in findings]),
                              ("Dead ends", "deadends", sorted(r["id"] for r in rows if os.path.isfile(os.path.join(out, "deadends", r["id"] + ".md")))),
                              ("Hypotheses", "hypotheses", [h["id"] for h in hyps])):
        moc += [f"## {title}", ""] + ([f"- {link(n)}" for n in names] or ["_none_"]) + [""]
    util.atomic_write(os.path.join(out, f"{eid}.md"), yamlish.join_frontmatter({"tags": ["engagement"]}, "\n".join(moc)))
    return counts


def write_engagement_stub(kb_root: str, eng: Engagement, counts: Dict[str, int]) -> str:
    """A one-note stub in the knowledge vault so every card's `used in: [[SV-...]]` link resolves
    and the graph shows which engagement each card came from. No target detail — counts and the
    finding classes only; the full graph stays in the engagement's own vault."""
    st = eng.load()
    classes = sorted({str(yamlish.split_frontmatter(util.read_text(f))[0].get("class", ""))
                      for f in glob.glob(eng.path("findings", "*.md"))} - {""})
    body = [f"# {st['id']}", "", f"packs: {', '.join(st.get('packs', []))} · " +
            ", ".join(f"{v} {k}" for k, v in counts.items()), "",
            "## Classes found"] + ([f"- {link('class-' + slug(c), c)}" for c in classes] or ["_none confirmed_"])
    path = os.path.join(kb_root, "engagements", f"{st['id']}.md")
    util.atomic_write(path, yamlish.join_frontmatter({"tags": ["engagement"]}, "\n".join(body) + "\n"))
    return path
