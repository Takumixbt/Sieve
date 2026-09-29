"""Vector cards: the attack catalog. Parseable markdown, one card per heading.

    ### W3-ORC-01 · Spot-price oracle manipulation
    - signal: what to grep for / observe
    - attack: how it is exploited, in one or two sentences
      (continuation lines are indented two spaces)
    - proof: the oracle that confirms it (what evidence counts)
    - fp: false-positive traps
    - sev: severity ladder
    - kb: keywords for the knowledge base

Required keys: signal, attack, proof, fp, sev, kb. Optional: chain, tell, cwe, agents.
"""
from __future__ import annotations

import glob
import os
import re
from typing import Dict, List, Optional

from . import repo_root

REQUIRED = ("signal", "attack", "proof", "fp", "sev", "kb")
OPTIONAL = ("chain", "tell", "cwe", "agents")
ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+-\d{2,3}$")
_HEAD = re.compile(r"^###\s+([A-Z0-9][A-Z0-9-]*)\s+[·\-—–]\s+(.+?)\s*$")
_KEY = re.compile(r"^-\s+([a-z_]+):\s?(.*)$")


def parse_cards(text: str, source: str = "") -> List[Dict[str, str]]:
    cards: List[Dict[str, str]] = []
    cur: Optional[Dict[str, str]] = None
    key: Optional[str] = None
    for n, line in enumerate(text.split("\n"), 1):
        m = _HEAD.match(line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2), "_src": f"{source}:{n}"}
            cards.append(cur)
            key = None
            continue
        if cur is None:
            continue
        if line.startswith("## ") or line.startswith("# "):
            cur = None
            key = None
            continue
        km = _KEY.match(line)
        if km:
            key = km.group(1)
            cur[key] = km.group(2).strip()
            continue
        if key and line.startswith("  ") and line.strip():
            cur[key] = (cur[key] + " " + line.strip()).strip()
        elif not line.strip():
            key = None
    return cards


def pack_dir(pack: str) -> str:
    return os.path.join(repo_root(), "packs", pack)


def load_pack(pack: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for f in sorted(glob.glob(os.path.join(pack_dir(pack), "vectors", "*.md"))):
        with open(f, encoding="utf-8") as fh:
            for c in parse_cards(fh.read(), os.path.relpath(f, repo_root())):
                c["pack"] = pack
                c["group"] = group_of(c["id"])
                out.append(c)
    return out


def group_of(vid: str) -> str:
    parts = vid.split("-")
    return "-".join(parts[:-1]) if len(parts) > 1 else vid


def load_all() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    base = os.path.join(repo_root(), "packs")
    for name in sorted(os.listdir(base)):
        if os.path.isdir(os.path.join(base, name, "vectors")):
            out.extend(load_pack(name))
    return out


def validate(cards: List[Dict[str, str]]) -> List[str]:
    errs: List[str] = []
    seen: Dict[str, str] = {}
    for c in cards:
        cid = c["id"]
        if not ID_RE.match(cid):
            errs.append(f"{c['_src']}: bad vector id {cid!r}")
        if cid in seen:
            errs.append(f"{c['_src']}: duplicate vector id {cid} (first at {seen[cid]})")
        seen[cid] = c["_src"]
        for k in REQUIRED:
            if not c.get(k, "").strip():
                errs.append(f"{c['_src']}: {cid} is missing required key `{k}`")
        if c.get("tell"):
            try:
                re.compile(c["tell"].strip("`"))
            except re.error as exc:
                errs.append(f"{c['_src']}: {cid} `tell` is not a valid regex: {exc}")
    return errs


def for_groups(pack: str, groups: List[str]) -> List[Dict[str, str]]:
    want = set(groups)
    return [c for c in load_pack(pack) if c["group"] in want or c["id"] in want]


def render(cards: List[Dict[str, str]]) -> str:
    out: List[str] = []
    for c in cards:
        out.append(f"### {c['id']} · {c['title']}")
        for k in REQUIRED + OPTIONAL:
            if c.get(k):
                out.append(f"- {k}: {c[k]}")
        out.append("")
    return "\n".join(out)
