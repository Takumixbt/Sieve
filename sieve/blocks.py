"""Parsers for what a hunting agent writes: FINDING / LEAD / HYPOTHESIS blocks, the COVERAGE
section, reasoning markers, and the DONE line. Pure text in, plain dicts out — no judgment here.

Formats are the ones `references/shared-rules.md` defines; the COVERAGE grammar is the one the
generated bundle's OUTPUT CONTRACT states (`pipeline.output_contract`).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

KINDS = ("FINDING", "LEAD", "HYPOTHESIS")
LADDER_RUNGS = ("input", "layer", "precondition", "inversion", "precedent", "sibling", "transplant",
                "construct", "fresh-eyes")

_HEAD = re.compile(r"^\s*(?:[-*>#]+\s*)*(?:\*\*|`)*(FINDING|LEAD|HYPOTHESIS)(?:\*\*|`)*\s*\|\s*(?P<rest>.+?)\s*$")
_KEY = re.compile(r"^\s{0,3}(?:[-*]\s+)?(?:\*\*)?(?P<k>[a-z][a-z0-9_]*)(?:\*\*)?:\s*(?P<v>.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_DONE = re.compile(r"^\s*SIEVE-AGENT-DONE\s+(?P<agent>\S+)\s+pass\s+(?P<n>\d+)\s*$")
_COV_HEAD = re.compile(r"^\s{0,3}#{1,6}\s*COVERAGE\b", re.I)
_ANY_HEAD = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_ROW = re.compile(r"^\s*(?:[-*]\s+)?(?P<row>R-\d{4,})\s*\|\s*(?P<disp>[A-Za-z-]+)\s*(?:\|\s*(?P<rest>.*))?$")
_RUNG_RX = re.compile(r"\b(" + "|".join(LADDER_RUNGS) + r")\s*:\s*")


def _header_fields(rest: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for seg in rest.split("|"):
        if ":" in seg:
            k, v = seg.split(":", 1)
            k = k.strip().lower().replace(" ", "_")
            if re.fullmatch(r"[a-z][a-z0-9_]*", k):
                out[k] = v.strip()
    return out


def parse_blocks(text: str, src: str = "") -> List[Dict[str, Any]]:
    """Every FINDING/LEAD/HYPOTHESIS block in `text`. Headers inside a fenced code block that opened
    *before* the block are ignored (an agent quoting the format is not emitting a finding)."""
    blocks: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    key: Optional[str] = None
    in_fence = False
    fence_owner_is_block = False
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if _FENCE.match(line):
            if not in_fence:
                in_fence = True
                fence_owner_is_block = cur is not None and key is not None
            else:
                in_fence = False
            if cur is not None and key is not None and fence_owner_is_block:
                cur[key] = (cur[key] + "\n" + line).strip("\n")
            continue
        if in_fence:
            if cur is not None and key is not None and fence_owner_is_block:
                cur[key] = cur[key] + "\n" + line
            continue
        m = _HEAD.match(line)
        if m:
            cur = {"kind": m.group(1), "_src": f"{src}:{i}", "_line": i}
            cur.update(_header_fields(m.group("rest")))
            blocks.append(cur)
            key = None
            continue
        if cur is None:
            continue
        if _ANY_HEAD.match(line) or _DONE.match(line):
            cur, key = None, None
            continue
        if not line.strip():
            j = i
            while j < len(lines) and not lines[j].strip():
                j += 1
            nxt = lines[j] if j < len(lines) else ""
            if not nxt or not (_KEY.match(nxt) or nxt.startswith((" ", "\t"))):
                cur, key = None, None
            continue
        km = _KEY.match(line)
        if km:
            key = km.group("k")
            cur[key] = km.group("v").strip()
        elif key is not None:
            cur[key] = (cur[key] + " " + line.strip()).strip()
    return blocks


def parse_attempts(text: str) -> List[Dict[str, str]]:
    """`inversion: made caller owner via initialize -> reverts; input: replayed with a non-owner`."""
    spans = list(_RUNG_RX.finditer(text or ""))
    out: List[Dict[str, str]] = []
    for n, m in enumerate(spans):
        end = spans[n + 1].start() if n + 1 < len(spans) else len(text)
        note = text[m.end():end].strip(" ;,\t\"'`")
        if note:
            out.append({"rung": m.group(1), "note": note})
    return out


def parse_coverage(text: str) -> List[Dict[str, Any]]:
    """Rows of the `## COVERAGE` section:  R-0007 | clean | why it holds | inversion: ...; input: ..."""
    rows: List[Dict[str, Any]] = []
    on = False
    for line in text.split("\n"):
        if _COV_HEAD.match(line):
            on = True
            continue
        if on and (_ANY_HEAD.match(line) or _DONE.match(line)):
            on = False
        if not on:
            continue
        m = _ROW.match(line)
        if not m:
            continue
        rest = m.group("rest") or ""
        disp = m.group("disp").lower()
        note, attempts = "", []
        if disp in ("finding", "found"):
            note = rest.strip()                       # a group_key contains `|` — keep the whole reference
        elif disp in ("dead", "deadend", "dead-end"):
            attempts = parse_attempts(rest)
            if not attempts:
                note = rest.strip()
        else:
            parts = re.split(r"\s\|\s", rest, maxsplit=1)   # ` | ` (space-pipe-space) separates note from attempts
            note = parts[0].strip()
            attempts = parse_attempts(parts[1]) if len(parts) > 1 else []
            if not attempts and _RUNG_RX.search(note) and disp in ("clean", "done", "open"):
                attempts, note = parse_attempts(note), ""
        rows.append({"row": m.group("row"), "disp": "finding" if disp in ("finding", "found") else
                     ("dead" if disp.startswith("dead") else disp), "note": note, "attempts": attempts})
    return rows


def done_marker(text: str) -> Optional[Dict[str, Any]]:
    found = None
    for line in text.split("\n"):
        m = _DONE.match(line)
        if m:
            found = {"agent": m.group("agent"), "pass": int(m.group("n"))}
    return found


def count_markers(text: str) -> Dict[str, int]:
    """Reasoning markers that carry reasoning: `[Feynman: ...]` with at least 20 characters after the label, each distinct
    (repeating one sentence, or emitting bare `[Socratic]` tags, does not satisfy the quota)."""
    out: Dict[str, int] = {}
    for k in ("Feynman", "Socratic", "Inversion"):
        seen = set()
        for m in re.finditer(r"\[\s*" + k + r"\b[\s:.-]*([^\]\n]{20,})", text, re.I):
            seen.add(re.sub(r"\W+", " ", m.group(1).lower()).strip())
        out[k] = len(seen)
    return out


def techniques(blocks: List[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for b in blocks:
        for t in re.split(r"[,/]", str(b.get("technique", ""))):
            t = t.strip().lower()
            if t and t not in seen:
                seen.append(t)
    return seen


def moonshots(blocks: List[Dict[str, Any]]) -> int:
    n = 0
    for b in blocks:
        v = str(b.get("moonshot", "")).strip().lower()
        if v in ("true", "yes", "1", "y") or "moonshot" in str(b.get("technique", "")).lower():
            n += 1
    return n
