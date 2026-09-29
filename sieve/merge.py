"""`sieve merge` and `sieve absorb` — turn agents' raw output into findings files and frontier closures.

Both steps are deterministic and conservative in one direction only: they never *promote*. A block
that breaks a hard rule (no proof, hedge wording, a citation that does not resolve) is kept as a
LEAD with the reason written on it — nothing an agent found is lost — but it cannot become a
candidate for confirmation until a later pass raises it properly. Promotion happens only in
`judging.md` and `validate.py`, by a verifier that is not the discoverer.
"""
from __future__ import annotations

import glob
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import blocks as B
from . import cites, frontier, util, yamlish
from .config import load_config
from .report import SEVERITY_ORDER
from .state import Engagement

HEDGE = re.compile(
    r"could theoretically|in a worst[- ]case|with the right preconditions|if an attacker were somehow|"
    r"\b(?:may|might|could)\s+(?:potentially\s+)?(?:allow|permit|enable|lead to|result in)\b|"
    r"under certain conditions|could potentially|may potentially|\btheoretically\b|"
    r"\bit is possible that\b|\bin (?:some|certain) (?:cases|scenarios)\b", re.I)
PLACEHOLDER = re.compile(r"^\W*(n/?a|none|tbd|todo|pending|see (above|below|description)|\?+|-+)\W*$", re.I)
KEPT_ON_REMERGE = ("status", "validation", "gate", "verified_by", "judged_at", "complexity")
KIND_RANK = {"FINDING": 2, "LEAD": 1}


def _norm_key(pack: str, group_key: str) -> str:
    parts = [re.sub(r"\s+", " ", p).strip().lower() for p in str(group_key).split("|")]
    return pack.lower() + "|" + "|".join(p for p in parts if p)


def _agent_of(path: str) -> str:
    stem = os.path.basename(path)[:-3]
    return stem.replace("--", "/", 1) if "--" in stem else stem


def _pass_of(path: str, last_pass: int) -> int:
    m = re.search(r"pass-(\d+)", path)
    return int(m.group(1)) if m else last_pass


def _text_of(b: Dict[str, Any], keys: Tuple[str, ...]) -> str:
    return "\n".join(str(b.get(k, "")) for k in keys)


def classify(eng: Engagement, b: Dict[str, Any], idx: cites.FileIndex) -> Tuple[str, List[str], Dict[str, Any]]:
    """-> (final kind, [demotion reasons], citation report). Only ever moves FINDING down to LEAD."""
    if b["kind"] != "FINDING":
        return b["kind"], [], {"count": 0, "failures": [], "warnings": []}
    why: List[str] = []
    pack = str(b.get("pack") or "")
    proof = str(b.get("proof", "")).strip()
    if len(proof) < 20 or PLACEHOLDER.match(proof):
        why.append("no-proof")
    desc = str(b.get("description", ""))
    if not desc.strip():
        why.append("no-description")
    if HEDGE.search(desc):
        why.append("hedge-language")
    if str(b.get("severity", "")).lower() not in SEVERITY_ORDER:
        why.append("bad-severity")
    cite_rep = cites.verify_text(eng.root, _text_of(b, ("path", "proof", "description", "component")),
                                 hard_missing=(pack == "web3"), idx=idx)
    if cite_rep["failures"]:
        why.append("cite-fail")
    if pack == "web3" and cite_rep["count"] == 0:
        why.append("no-citation")
    return ("LEAD" if why else "FINDING"), why, cite_rep


def _render_body(b: Dict[str, Any], kind: str, why: List[str], cite_rep: Dict[str, Any],
                 alts: List[str], sources: List[str]) -> str:
    out: List[str] = []
    if kind == "FINDING":
        out += ["## Root cause", str(b.get("description", "")).strip(), "",
                "## Attack path", str(b.get("path", "")).strip() or "_(not stated)_", "",
                "## Proof", str(b.get("proof", "")).strip(), "",
                "## Remediation", str(b.get("fix", "")).strip() or "_(not stated)_", ""]
    else:
        out += ["## What was found", str(b.get("description", "")).strip() or "_(not stated)_", ""]
        if b.get("code_smells"):
            out += ["## Code smells", str(b["code_smells"]).strip(), ""]
        if b.get("path"):
            out += ["## Trail", str(b["path"]).strip(), ""]
        if b.get("proof"):
            out += ["## Partial evidence", str(b["proof"]).strip(), ""]
    if why:
        out += ["## Machine checks (`sieve merge`)",
                "Demoted from FINDING to LEAD: " + ", ".join(why) + ".", ""]
        for r in cite_rep.get("failures", []):
            out.append(f"- citation `{r['cite']}` — {r['why']}")
        out.append("")
    if cite_rep.get("warnings"):
        out += ["_Citations not found under the target root (not counted as failures for this pack):_"]
        out += [f"- `{r['cite']}`" for r in cite_rep["warnings"]] + [""]
    if alts:
        out += ["## Also reported by other agents / passes"] + [f"- {a}" for a in alts[:8]] + [""]
    out += ["## Raw source"] + [f"- `{s}`" for s in sources[:8]] + [""]
    return "\n".join(out)


def _load_index(eng: Engagement) -> Dict[str, Any]:
    return util.read_json(eng.path("findings", "index.json"), {"next": 1, "keys": {}}) or {"next": 1, "keys": {}}


def _existing_meta(eng: Engagement, fid: str) -> Dict[str, Any]:
    p = eng.path("findings", f"{fid}.md")
    if not os.path.isfile(p):
        return {}
    try:
        return yamlish.split_frontmatter(util.read_text(p))[0]
    except yamlish.YamlError:
        return {}


def merge(eng: Engagement) -> Dict[str, Any]:
    st = eng.load()
    last_pass = int(st.get("pass_current") or 1)
    files = sorted(glob.glob(eng.path("raw", "pass-*", "*.md")))
    roaming = eng.path("raw", "roaming.md")
    if os.path.isfile(roaming):
        files.append(roaming)
    idx = cites.FileIndex(eng.root)
    per_agent: Dict[str, Dict[str, int]] = {}
    hyps: List[Dict[str, Any]] = []
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for f in files:
        agent = "roaming" if f == roaming else _agent_of(f)
        text = util.read_text(f)
        rel = os.path.relpath(f, eng.root)
        n_pass = _pass_of(f, last_pass)
        stat = per_agent.setdefault(f"{agent}#{n_pass}", {"FINDING": 0, "LEAD": 0, "HYPOTHESIS": 0, "demoted": 0})
        for b in B.parse_blocks(text, rel):
            b["_agent"], b["_pass"], b["_rel"] = agent, n_pass, b["_src"]
            stat[b["kind"]] += 1
            if not b.get("pack"):
                b["pack"] = agent.split("/")[0] if "/" in agent and agent.split("/")[0] in st["packs"] else st["packs"][0]
            b.setdefault("class", "unclassified")
            b.setdefault("component", "unknown")
            if b["kind"] == "HYPOTHESIS":
                hyps.append({k: b.get(k, "") for k in ("_agent", "_pass", "pack", "class", "component", "question",
                                                       "next_step", "technique", "moonshot", "_src")})
                continue
            gk = b.get("group_key") or f"{b['component']}|{b['class']}"
            b["_key"] = _norm_key(b["pack"], gk)
            final, why, rep = classify(eng, b, idx)
            b["_final"], b["_why"], b["_cites"] = final, why, rep
            if why:
                stat["demoted"] += 1
            groups.setdefault(b["_key"], []).append(b)

    index = _load_index(eng)
    demotions: List[Dict[str, Any]] = []
    written: List[str] = []
    new_ids = 0
    summary_rows: List[Dict[str, Any]] = []
    for key, members in groups.items():
        def rank(b: Dict[str, Any]) -> Tuple[int, int, int]:
            try:
                conf = int(b.get("confidence") or 0)
            except (TypeError, ValueError):
                conf = 0
            return (KIND_RANK.get(b["_final"], 0), conf, -b["_pass"])
        members_sorted = sorted(members, key=rank, reverse=True)
        win = members_sorted[0]
        fid = index["keys"].get(key)
        if not fid:
            fid = f"F-{int(index['next']):03d}"
            index["next"] = int(index["next"]) + 1
            index["keys"][key] = fid
            new_ids += 1
        prior = _existing_meta(eng, fid)
        judged = prior.get("status") in ("confirmed", "trace-verified", "demoted", "rejected")
        agents = sorted({m["_agent"] for m in members} | set(prior.get("found_by") or []))
        passes = sorted({m["_pass"] for m in members} | set(int(p) for p in (prior.get("passes") or [])))
        kind = prior.get("kind") if judged else win["_final"]
        why = [] if judged else win["_why"]
        if win["kind"] == "FINDING" and win["_final"] == "LEAD":
            demotions.append({"id": fid, "agent": win["_agent"], "pass": win["_pass"], "why": win["_why"],
                              "component": win.get("component")})
        title = str(win.get("title") or "").strip() or f"{win.get('class')} — {win.get('component')}"
        claim = "|".join(str(win.get(k, "")).strip() for k in ("component", "class", "description", "path", "proof"))
        meta: Dict[str, Any] = {
            "id": fid, "kind": kind, "pack": win["pack"], "class": win.get("class"), "title": title,
            "component": win.get("component"), "group_key": win.get("group_key") or f"{win['component']}|{win['class']}",
            "severity": str(win.get("severity") or "").lower() or None,
            "status": prior.get("status") if judged else ("candidate" if kind == "FINDING" else "lead"),
            "confidence": win.get("confidence") if kind == "FINDING" else None,
            "vector": win.get("vector") or None, "cwe": win.get("cwe") or None,
            "found_by": agents, "passes": passes, "reports": len(members),
            "complexity": prior.get("complexity") or win.get("complexity") or None,
            "demoted_by": why or None, "claim_hash": util.sha256_bytes(claim.encode())[:16],
            "validation": prior.get("validation") or "unvalidated",
            "tell": win.get("tell") or None, "source_ref": win.get("source_ref") or None,
        }
        for k in KEPT_ON_REMERGE:
            if k in prior and prior[k] is not None:
                meta[k] = prior[k]
        meta = {k: v for k, v in meta.items() if v not in (None, "", [])}
        alts = []
        for m in members_sorted[1:]:
            d = str(m.get("description", "")).strip()
            if d and d != str(win.get("description", "")).strip():
                alts.append(f"{m['_agent']} (pass {m['_pass']}): {d[:200]}")
        sources = [m["_src"] for m in members_sorted]
        body = _render_body(win, kind, why, win["_cites"], alts, sources)
        if judged:
            old = util.read_text(eng.path("findings", f"{fid}.md"))
            body = yamlish.split_frontmatter(old)[1]  # a judged finding's body is frozen; only provenance updates
        util.atomic_write(eng.path("findings", f"{fid}.md"), yamlish.join_frontmatter(meta, body))
        written.append(fid)
        summary_rows.append(meta)

    util.write_json(eng.path("findings", "index.json"), index)
    util.write_json(eng.path("findings", "hypotheses.json"), hyps)
    cand = {m["id"]: {"group_key": m.get("group_key"), "found_by": m.get("found_by"), "severity": m.get("severity")}
            for m in summary_rows if m.get("kind") == "FINDING"}
    util.write_json(eng.path("findings", "candidates.json"), cand)
    summary_rows.sort(key=lambda m: m["id"])
    lines = [f"# Ledger — {len(summary_rows)} merged item(s)", "",
             "| id | kind | sev | status | component | class | found by |", "|---|---|---|---|---|---|---|"]
    for m in summary_rows:
        lines.append(f"| {m['id']} | {m.get('kind')} | {m.get('severity', '')} | {m.get('status', '')} | "
                     f"{m.get('component', '')} | {m.get('class', '')} | {', '.join(m.get('found_by', []))} |")
    util.atomic_write(eng.path("findings", "ledger.md"), "\n".join(lines) + "\n")
    return {"files": len(files), "per_agent": per_agent, "items": len(summary_rows), "new": new_ids,
            "findings": sum(1 for m in summary_rows if m.get("kind") == "FINDING"),
            "leads": sum(1 for m in summary_rows if m.get("kind") == "LEAD"),
            "hypotheses": len(hyps), "demotions": demotions}


# ---------------------------------------------------------------------------- absorb

def _resolve_finding(eng: Engagement, ref: str) -> Optional[str]:
    ref = ref.strip().strip("`")
    if not ref:
        return None
    items: List[Dict[str, Any]] = []
    for f in sorted(glob.glob(eng.path("findings", "F-*.md"))):
        try:
            meta = yamlish.split_frontmatter(util.read_text(f))[0]
        except yamlish.YamlError:
            continue
        if meta.get("id"):
            items.append(meta)
    for m in items:
        if m["id"].lower() == ref.lower():
            return m["id"]
    low = re.sub(r"\s+", " ", ref).lower()
    for m in items:
        if re.sub(r"\s+", " ", str(m.get("group_key", ""))).lower().replace(" |", "|").replace("| ", "|") == \
                low.replace(" |", "|").replace("| ", "|"):
            return m["id"]
    comp = [m for m in items if str(m.get("component", "")).lower() == low]
    if len(comp) == 1:
        return comp[0]["id"]
    sub = [m for m in items if low in str(m.get("title", "")).lower() or low in str(m.get("group_key", "")).lower()]
    return sub[0]["id"] if len(sub) == 1 else None


def _cites_ok(eng: Engagement, idx: cites.FileIndex, text: str, hard_missing: bool) -> Optional[str]:
    rep = cites.verify_text(eng.root, text, hard_missing=hard_missing, idx=idx)
    if rep["failures"]:
        r = rep["failures"][0]
        return f"citation `{r['cite']}` does not check out: {r['why']}"
    return None


def absorb(eng: Engagement, n: int) -> Dict[str, Any]:
    cfg = load_config(eng.root)
    st = eng.load()
    idx = cites.FileIndex(eng.root)
    hard = "web3" in st["packs"]
    applied: List[str] = []
    refused: List[str] = []
    skipped = 0
    rows_by_id = {r["id"]: r for r in frontier.load(eng)}
    files = sorted(glob.glob(eng.path("raw", f"pass-{n}", "*.md")))
    roaming = eng.path("raw", "roaming.md")
    if os.path.isfile(roaming):
        files.append(roaming)
    for f in files:
        who = os.path.basename(f)[:-3]
        cov = B.parse_coverage(util.read_text(f))
        note_counts: Dict[str, int] = {}
        for c in cov:
            if c["disp"] in ("clean", "done"):
                key = re.sub(r"\W+", " ", c["note"]).strip().lower()
                if key:
                    note_counts[key] = note_counts.get(key, 0) + 1
        for c in cov:
            rid, disp = c["row"], c["disp"]
            row = rows_by_id.get(rid)
            tag = f"{who}:{rid}"
            if row is None:
                refused.append(f"{tag} — no such frontier row")
                continue
            if row["status"] in ("done", "dead", "blocked"):
                skipped += 1
                continue
            bad = _cites_ok(eng, idx, c["note"] + "\n" + "\n".join(a["note"] for a in c["attempts"]), hard)
            if bad:
                refused.append(f"{tag} — {bad}")
                continue
            have = {(x["rung"], x["note"]) for x in frontier.attempts(eng, rid)}
            for a in c["attempts"]:
                if (a["rung"], a["note"]) in have or len(a["note"]) < 8:
                    continue
                frontier.attempt(eng, rid, a["rung"], a["note"])
                have.add((a["rung"], a["note"]))
            try:
                if disp == "finding":
                    fid = _resolve_finding(eng, c["note"])
                    if not fid:
                        refused.append(f"{tag} — finding reference {c['note']!r} matches no merged finding/lead "
                                       f"(use the F-id from .sieve/findings/ledger.md or the exact group_key)")
                        continue
                    frontier.done_finding(eng, rid, fid)
                    applied.append(f"{tag} → done ({fid})")
                elif disp in ("clean", "done"):
                    key = re.sub(r"\W+", " ", c["note"]).strip().lower()
                    if key and note_counts.get(key, 0) >= 3:
                        refused.append(f"{tag} — the same 'why it holds' text is pasted on {note_counts[key]} rows; "
                                       f"a receipt must be specific to its row")
                        continue
                    frontier.done_clean(eng, rid, c["note"], cfg)
                    applied.append(f"{tag} → clean")
                elif disp == "dead":
                    frontier.dead(eng, rid, [], cfg)
                    applied.append(f"{tag} → dead")
                elif disp == "blocked":
                    reason, _, note = c["note"].partition(":")
                    frontier.block(eng, rid, reason.strip().lower(), note.strip() or c["note"])
                    applied.append(f"{tag} → blocked ({reason.strip()})")
                elif disp == "open":
                    applied.append(f"{tag} → still open ({len(c['attempts'])} attempt(s) logged)")
                else:
                    refused.append(f"{tag} — unknown disposition {disp!r} (finding | clean | dead | blocked | open)")
            except SystemExit as exc:
                msg = str(exc).strip().split("\n")
                refused.append(f"{tag} — refused: " + "; ".join(x.strip(" -") for x in msg[1:3] if x.strip()) if len(msg) > 1
                               else f"{tag} — refused: {msg[0]}")
    return {"applied": applied, "refused": refused, "already_closed": skipped, "files": len(files),
            "frontier": frontier.stats(eng)}
