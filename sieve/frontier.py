"""The frontier: the audit's work queue.

Everything that must be examined is a row. An agent's job is to drain the queue. A row leaves the
queue only through a door that leaves a receipt:

    done --finding F-1     a finding or lead came out of it
    done --clean           examined and clean — needs >= 2 attempts incl. an INVERSION attempt
    dead                   needs >= N attempts spread over >= M different ladder rungs
    block                  only for the whitelisted human-only reasons

"I could not find anything" is never a closure by itself.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import util
from .config import Config
from .state import Engagement

HEADER = ["id", "kind", "pack", "component", "lens", "source", "status", "prio", "attempts", "note", "updated"]
STATUSES = ("open", "probing", "done", "dead", "blocked")
OPEN = ("open", "probing")

# The stuck ladder. Each rung is a different *kind* of move, so three attempts on three rungs
# are three genuinely different ideas, not three retries.
LADDER: Dict[str, str] = {
    "input": "vary the input, verb, identity, encoding, ordering or timing",
    "layer": "attack a different layer of the same feature (client/API/infra/chain; decoder/handler/storage)",
    "precondition": "change, lower or manufacture the precondition; chain a second weakness",
    "inversion": "invert the guard: what must be true for this to work, and can I make it true?",
    "precedent": "search the knowledge base / disclosed reports for the same shape",
    "sibling": "compare with the sibling operation, other version, other branch, other role",
    "transplant": "import a vector from another domain (web race -> same-block ordering, TOCTOU -> check-then-act)",
    "construct": "write the exploit assuming the bug exists; the point where it will not build is the guard or the bug",
    "fresh-eyes": "hand the question to an agent with no prior context",
}

BLOCK_REASONS = ("scope", "credentials", "irreversible", "tooling")


def _lock(eng: Engagement) -> str:
    return eng.path("frontier.lock")


def load(eng: Engagement) -> List[Dict[str, str]]:
    return util.read_tsv(eng.frontier_path())[1]


def _save(eng: Engagement, rows: List[Dict[str, Any]]) -> None:
    util.write_tsv(eng.frontier_path(), HEADER, rows)


def _next_id(rows: List[Dict[str, str]]) -> str:
    n = 0
    for r in rows:
        try:
            n = max(n, int(r["id"].split("-")[1]))
        except (IndexError, ValueError):
            continue
    return f"R-{n + 1:04d}"


def add(eng: Engagement, kind: str, component: str, pack: str = "", lens: str = "*",
        source: str = "manual", prio: int = 3, note: str = "") -> str:
    with util.file_lock(_lock(eng)):
        rows = load(eng)
        for r in rows:  # idempotent seeding
            if (r["kind"], r["pack"], r["component"], r["lens"]) == (kind, pack, component, lens):
                return r["id"]
        rid = _next_id(rows)
        rows.append({"id": rid, "kind": kind, "pack": pack, "component": component, "lens": lens,
                     "source": source, "status": "open", "prio": prio, "attempts": 0,
                     "note": note, "updated": util.now_iso()})
        _save(eng, rows)
        return rid


def add_many(eng: Engagement, items: Iterable[Dict[str, Any]]) -> int:
    """Bulk, idempotent seeding under one lock (one read, one write). Returns rows actually added."""
    added = 0
    with util.file_lock(_lock(eng)):
        rows = load(eng)
        seen = {(r["kind"], r["pack"], r["component"], r["lens"]) for r in rows}
        for it in items:
            key = (it["kind"], it.get("pack", ""), it["component"], it.get("lens", "*"))
            if key in seen:
                continue
            seen.add(key)
            rows.append({"id": _next_id(rows), "kind": key[0], "pack": key[1], "component": key[2], "lens": key[3],
                         "source": it.get("source", "seed"), "status": "open", "prio": it.get("prio", 3),
                         "attempts": 0, "note": it.get("note", ""), "updated": util.now_iso()})
            added += 1
        if added:
            _save(eng, rows)
    return added


def _find(rows: List[Dict[str, str]], rid: str) -> Dict[str, str]:
    for r in rows:
        if r["id"] == rid:
            return r
    raise SystemExit(f"sieve frontier: no such row {rid}")


def _attempts_path(eng: Engagement, rid: str) -> str:
    return eng.path("deadends", f"{rid}.jsonl")


def attempts(eng: Engagement, rid: str) -> List[Dict[str, Any]]:
    p = _attempts_path(eng, rid)
    out: List[Dict[str, Any]] = []
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln:
                    try:
                        out.append(json.loads(ln))
                    except ValueError:
                        continue
    return out


def _log_attempt(eng: Engagement, rid: str, rung: str, note: str) -> None:
    if rung not in LADDER:
        raise SystemExit(f"sieve frontier: unknown rung {rung!r}; valid: {', '.join(LADDER)}")
    if len(note.strip()) < 8:
        raise SystemExit("sieve frontier: an attempt needs a real note (>= 8 chars): what exactly did you try?")
    os.makedirs(eng.path("deadends"), exist_ok=True)
    with open(_attempts_path(eng, rid), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"rung": rung, "note": note.strip(), "time": util.now_iso()}) + "\n")


def attempt(eng: Engagement, rid: str, rung: str, note: str) -> int:
    with util.file_lock(_lock(eng)):
        rows = load(eng)
        row = _find(rows, rid)
        _log_attempt(eng, rid, rung, note)
        row["attempts"] = str(len(attempts(eng, rid)))
        if row["status"] == "open":
            row["status"] = "probing"
        row["updated"] = util.now_iso()
        _save(eng, rows)
        return int(row["attempts"])


def _close(eng: Engagement, rid: str, status: str, note: str) -> None:
    rows = load(eng)
    row = _find(rows, rid)
    row["status"] = status
    row["note"] = note
    row["attempts"] = str(len(attempts(eng, rid)))
    row["updated"] = util.now_iso()
    _save(eng, rows)


def done_finding(eng: Engagement, rid: str, ref: str) -> None:
    if not ref.strip():
        raise SystemExit("sieve frontier: --finding needs a finding or lead id")
    with util.file_lock(_lock(eng)):
        _close(eng, rid, "done", f"produced {ref}")


def done_clean(eng: Engagement, rid: str, note: str, cfg: Config) -> None:
    with util.file_lock(_lock(eng)):
        att = attempts(eng, rid)
        rungs = {a["rung"] for a in att}
        problems = []
        if len(att) < 2:
            problems.append(f"only {len(att)} attempt(s) logged; a clean claim needs >= 2")
        if "inversion" not in rungs:
            problems.append("no `inversion` attempt logged; every clean path gets a backward pass")
        if len(note.strip()) < 12:
            problems.append("--clean needs a note that names the guard or reason it holds (>= 12 chars)")
        if problems:
            raise SystemExit("sieve frontier: refusing to close %s as clean:\n  - %s\n"
                             "Log attempts with `sieve frontier attempt %s --rung inversion --note ...`"
                             % (rid, "\n  - ".join(problems), rid))
        _close(eng, rid, "done", "clean: " + note.strip())


def dead(eng: Engagement, rid: str, tries: Iterable[Tuple[str, str]], cfg: Config) -> None:
    min_att = int(cfg.get("persistence.min_dead_attempts", 3))
    min_rungs = int(cfg.get("persistence.min_distinct_rungs", 3))
    with util.file_lock(_lock(eng)):
        for rung, note in tries:
            _log_attempt(eng, rid, rung, note)
        att = attempts(eng, rid)
        rungs = {a["rung"] for a in att}
        problems = []
        if len(att) < min_att:
            problems.append(f"{len(att)} attempt(s) logged, need >= {min_att}")
        if len(rungs) < min_rungs:
            problems.append(f"{len(rungs)} distinct rung(s) used ({', '.join(sorted(rungs)) or 'none'}), "
                            f"need >= {min_rungs}")
        if problems:
            unused = [r for r in LADDER if r not in rungs]
            rows = load(eng)
            row = _find(rows, rid)
            row["attempts"] = str(len(att))
            if row["status"] == "open":
                row["status"] = "probing"
            _save(eng, rows)
            raise SystemExit(
                "sieve frontier: %s is not dead yet:\n  - %s\nUnused rungs you can still climb: %s\n"
                "Pick one (references/methodology.md Part 6b) and try it." % (rid, "\n  - ".join(problems),
                                                                      "; ".join(f"{r} ({LADDER[r]})" for r in unused[:4])))
        _close(eng, rid, "dead", f"dead after {len(att)} attempts over {len(rungs)} rungs")


def block(eng: Engagement, rid: str, reason: str, note: str) -> None:
    if reason not in BLOCK_REASONS:
        raise SystemExit(f"sieve frontier: block reasons are {', '.join(BLOCK_REASONS)} — "
                         "'hard', 'unlikely' and 'time' are not reasons")
    if len(note.strip()) < 12:
        raise SystemExit("sieve frontier: a block needs a note stating exactly what is missing (>= 12 chars)")
    with util.file_lock(_lock(eng)):
        _close(eng, rid, "blocked", f"{reason}: {note.strip()}")


def reopen(eng: Engagement, rid: str, note: str = "reopened") -> None:
    with util.file_lock(_lock(eng)):
        rows = load(eng)
        row = _find(rows, rid)
        row["status"] = "open"
        row["note"] = note
        row["updated"] = util.now_iso()
        _save(eng, rows)


def next_rows(eng: Engagement, lens: Optional[str] = None, n: int = 5) -> List[Dict[str, str]]:
    rows = [r for r in load(eng) if r["status"] in OPEN and (lens is None or r["lens"] in ("*", lens))]
    rows.sort(key=lambda r: (-int(r.get("prio") or 3), r["id"]))
    return rows[:n]


def stats(eng: Engagement) -> Dict[str, Any]:
    rows = load(eng)
    by_status: Dict[str, int] = {s: 0 for s in STATUSES}
    by_lens: Dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        if r["status"] in OPEN:
            by_lens[r["lens"]] = by_lens.get(r["lens"], 0) + 1
    total = len(rows)
    closed = by_status["done"] + by_status["dead"] + by_status["blocked"]
    return {"total": total, "by_status": by_status, "open_by_lens": by_lens,
            "open": by_status["open"] + by_status["probing"],
            "closed_pct": round(100.0 * closed / total, 1) if total else 100.0}


def progress_hash(eng: Engagement) -> str:
    """Changes whenever real work happened. Used by the Stop hook to tell stalling from working."""
    rows = load(eng)
    parts = [f"{r['id']}:{r['status']}:{r['attempts']}" for r in rows]
    for sub in ("raw", "findings", "proofs"):
        d = eng.path(sub)
        n = 0
        size = 0
        for base, _dirs, files in os.walk(d):
            for f in files:
                n += 1
                try:
                    size += os.path.getsize(os.path.join(base, f))
                except OSError:
                    pass
        parts.append(f"{sub}:{n}:{size}")
    try:
        st = eng.load()
        parts.append(f"phase:{st.get('phase')}:{st.get('pass_current')}:{st.get('pass_step')}")
    except SystemExit:
        pass
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
