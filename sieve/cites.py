"""Citation verification — the machine half of "cite or drop".

A finding that names `Vault.sol:142` is making a claim about a real file. This module re-reads that
file and answers, without any model in the loop: does it exist, is the line in range, and — when the
citation carries a quoted snippet — does the quoted code really appear at that spot. A fabricated
`file:line` is the failure mode the skill cannot tolerate (`shared-rules.md`), so it is checked by
code rather than trusted to narration.

Scope: only source-shaped citations are checked (`path/to/file.ext:LINE[-LINE]`, `file.ext#L12`).
Requests, transaction hashes and decompiler addresses are not files and are left to the oracles.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import util

SRC_EXT = {
    "sol", "vy", "yul", "rs", "go", "py", "js", "mjs", "cjs", "ts", "tsx", "jsx", "java", "kt", "kts",
    "swift", "m", "mm", "c", "cc", "cpp", "cxx", "h", "hpp", "rb", "php", "cs", "move", "cairo", "func",
    "fc", "tolk", "sh", "bash", "yml", "yaml", "json", "toml", "xml", "smali", "ex", "exs", "scala",
    "lua", "asm", "s", "gradle", "plist", "html", "vue", "svelte", "graphql", "gql", "proto", "sql",
    "tf", "dockerfile", "conf", "ini", "env",
}
SKIP_DIRS = {".git", "node_modules", ".sieve", "__pycache__", "target", "build", "dist", "out",
             "cache", "artifacts", ".venv", "venv", "lib/forge-std"}

_CITE = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?[A-Za-z0-9_@.~+/\\\-]*[A-Za-z0-9_\-]\.(?P<ext>[A-Za-z0-9]{1,10}))"
    r"(?::|#L)(?P<a>\d{1,7})(?:\s*[-–]\s*L?(?P<b>\d{1,7}))?"
    r"(?:\s*[`'\"“](?P<snip>[^`'\"”\n]{3,200})[`'\"”])?")


def extract(text: str) -> List[Dict[str, Any]]:
    """Every source-shaped citation in `text`, de-duplicated, in order of appearance."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for m in _CITE.finditer(text or ""):
        if m.group("ext").lower() not in SRC_EXT:
            continue
        a = int(m.group("a"))
        b = int(m.group("b")) if m.group("b") else a
        if b < a:
            a, b = b, a
        key = (m.group("path"), a, b, m.group("snip") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append({"raw": m.group(0).strip(), "path": m.group("path").replace("\\", "/"),
                    "start": a, "end": b, "snippet": (m.group("snip") or "").strip()})
    return out


class FileIndex:
    """Lazy basename index of the target tree, so `Vault.sol:10` resolves even without a full path."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self._by_base: Optional[Dict[str, List[str]]] = None

    def _build(self) -> Dict[str, List[str]]:
        idx: Dict[str, List[str]] = {}
        n = 0
        for base, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                idx.setdefault(f, []).append(os.path.relpath(os.path.join(base, f), self.root))
                n += 1
                if n > 200000:
                    return idx
        return idx

    def resolve(self, path: str) -> Tuple[Optional[str], str]:
        """-> (relative path or None, reason)."""
        p = path.strip().lstrip("./")
        full = os.path.abspath(os.path.join(self.root, p)) if not os.path.isabs(path) else os.path.abspath(path)
        if not (full == self.root or full.startswith(self.root + os.sep)):
            return None, "path is outside the engagement root"
        if os.path.isfile(full):
            return os.path.relpath(full, self.root), "exact"
        if self._by_base is None:
            self._by_base = self._build()
        cands = self._by_base.get(os.path.basename(p), [])
        suffix = [c for c in cands if c.replace(os.sep, "/").endswith(p.replace("\\", "/"))]
        pick = suffix or cands
        if len(pick) == 1:
            return pick[0], "matched by name"
        if not pick:
            return None, "no such file under the engagement root"
        return None, f"ambiguous: {len(pick)} files match ({', '.join(pick[:3])}...) — cite the full path"


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def verify_one(idx: FileIndex, cite: Dict[str, Any]) -> Dict[str, Any]:
    rel, why = idx.resolve(cite["path"])
    res: Dict[str, Any] = {"cite": cite["raw"], "ok": False, "why": why, "file": rel}
    if rel is None:
        res["kind"] = "missing-file"
        return res
    full = os.path.join(idx.root, rel)
    try:
        lines = util.read_text(full).split("\n")
    except OSError as exc:
        res.update(kind="unreadable", why=str(exc))
        return res
    n = len(lines)
    if lines and lines[-1] == "":
        n -= 1
    res["sha256"] = util.sha256_file(full)
    res["lines"] = n
    if cite["start"] < 1 or cite["end"] > n:
        res.update(kind="line-out-of-range", why=f"{rel} has {n} line(s); cited {cite['start']}-{cite['end']}")
        return res
    window = "\n".join(lines[cite["start"] - 1:cite["end"]])
    res["excerpt"] = window[:400]
    if cite["snippet"]:
        near = "\n".join(lines[max(0, cite["start"] - 4):min(n, cite["end"] + 3)])
        if _norm(cite["snippet"]) not in _norm(near):
            res.update(kind="snippet-mismatch",
                       why=f"the quoted code `{cite['snippet'][:80]}` is not at {rel}:{cite['start']} (±3 lines)")
            return res
    res.update(ok=True, kind="ok", why=why if why != "exact" else "verified")
    return res


def verify_text(root: str, text: str, hard_missing: bool = True,
                idx: Optional[FileIndex] = None) -> Dict[str, Any]:
    """Verify every citation in `text`.

    `hard_missing=False` (web / binary packs, where the cited artifact may be a decompiled copy
    outside the tree) downgrades *file not found* to a warning; an in-range check on files that do
    exist, and any quoted-snippet mismatch, still fail hard.
    """
    idx = idx or FileIndex(root)
    results = [verify_one(idx, c) for c in extract(text)]
    failures: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    for r in results:
        if r["ok"]:
            continue
        if r.get("kind") == "missing-file" and not hard_missing:
            warnings.append(r)
        else:
            failures.append(r)
    return {"count": len(results), "results": results, "failures": failures, "warnings": warnings,
            "ok": not failures}
