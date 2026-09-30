"""Web3 x-ray: mechanical facts only — discovery, nSLOC, test inventory, a grep-only entry-point
scan across VMs, and (new) auto-invoking Slither/Aderyn when they're on PATH.

This deliberately does NOT parse or classify code itself. Grep is the source of truth for *which
lines are candidate entry points* (cheap, exact, language-agnostic), and the agent reads the source
to classify each one (permissionless / role-gated / admin), verified by re-reading the exact
`file:line` this scan names. A Python parser that tried to do the classification would be
re-implementing Slither/Aderyn worse than they do it.

Running Slither/Aderyn themselves is a different thing from re-implementing them, and belongs here:
this module already shells out to nothing dangerous (it's a read-only source walk), so shelling out
to a real static analyzer — capturing its own JSON, unmodified — is the same category of mechanical
work as the grep pass, not a step up in judgment. `run()` auto-invokes both tools when they're
installed and no report path was explicitly given; their result still lands in `tool_leads`, still
gated by `judging.md` before it ships, exactly as if the operator had run them by hand and passed
the path in. See references/xray.md Phase 0. This is the mechanical layer's own first move; it falls back to "operator
supplies the report" or "missing, coverage debt" only when the binary genuinely isn't on PATH.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from . import util

AUTO_RUN_TIMEOUT_SEC = int(os.environ.get("SIEVE_STATIC_TIMEOUT", "180"))

EXCLUDE_DIRS = {"node_modules", "lib", "artifacts", "cache", "out", "broadcast", "coverage", "typechain",
                "typechain-types", "interfaces", "interface", "mocks", "mock", "test", "tests", ".git", "target",
                "build", "dist", ".sieve", "forge-cache", "cache_hardhat", ".venv", "venv", "__pycache__"}
LANG_BY_EXT = {".sol": "solidity", ".vy": "vyper", ".move": "move", ".cairo": "cairo", ".rs": "rust"}
RUST_FRAMEWORKS = [("anchor", r"anchor_lang|#\[program\]"), ("cosmwasm", r"cosmwasm_std|#\[entry_point\]"),
                   ("near", r"near_sdk|#\[near_bindgen\]|#\[near\("), ("soroban", r"soroban_sdk|#\[contractimpl\]"),
                   ("ink", r"\bink!|#\[ink::contract\]"), ("solana-native", r"solana_program|entrypoint!\s*\(")]
COMMENT_LINE = {"solidity": r"^\s*(//|/\*|\*|\*/)", "rust": r"^\s*(//|/\*|\*|\*/)",
                "vyper": r"^\s*#", "move": r"^\s*(//|/\*|\*|\*/)", "cairo": r"^\s*(//|/\*|\*|\*/)"}

# One POSIX-portable pattern per language: cheap, exact, verified by re-reading the line, never
# trusted as a classification. Multi-line Solidity signatures need a second pass (closing-paren-
# on-its-own-line); the other languages here don't commonly wrap a visibility/decorator across
# lines, so one pattern each is enough.
ENTRY_PATTERNS: Dict[str, List["re.Pattern[str]"]] = {
    "solidity": [
        re.compile(r"function\s+\w+\s*\([^)]*\)\s+(external|public)"),
        re.compile(r"^\s*\)\s*(external|public)", re.M),
    ],
    "vyper": [re.compile(r"^@external", re.M)],
    "move": [re.compile(r"\b(public\s+entry\s+fun|entry\s+fun)\s+\w+")],
    "cairo": [re.compile(r"#\[(external\(v0\)|abi\(embed_v0\)|l1_handler|constructor)\]")],
    "anchor": [re.compile(r"pub\s+fn\s+\w+\s*\(\s*ctx\s*:\s*Context")],
}


def _excluded_file(name: str) -> bool:
    return name.endswith(".t.sol") or ("Test" in name and name.endswith(".sol")) or \
        ("Mock" in name and name.endswith(".sol"))


def detect_src_dirs(root: str) -> List[str]:
    dirs: List[str] = []
    ft = os.path.join(root, "foundry.toml")
    if os.path.isfile(ft):
        m = re.search(r'^\s*src\s*=\s*"([^"]+)"', util.read_text(ft), re.M)
        if m:
            dirs.append(m.group(1))
    for name in ("hardhat.config.js", "hardhat.config.ts", "hardhat.config.cjs", "hardhat.config.mjs"):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            m = re.search(r'sources\s*:\s*["\']([^"\']+)["\']', util.read_text(p))
            if m:
                dirs.append(m.group(1).lstrip("./"))
    for cand in ("src", "contracts", "programs", "sources", "move"):
        if os.path.isdir(os.path.join(root, cand)) and cand not in dirs:
            dirs.append(cand)
    return [d for d in dirs if os.path.isdir(os.path.join(root, d))] or ["."]


def discover(root: str, src_dirs: List[str]) -> Tuple[List[Dict[str, str]], List[str]]:
    files: List[Dict[str, str]] = []
    skipped: List[str] = []
    seen = set()
    for sd in src_dirs:
        base = os.path.join(root, sd)
        for cur, dirs, names in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for n in sorted(names):
                ext = os.path.splitext(n)[1].lower()
                if ext not in LANG_BY_EXT or _excluded_file(n):
                    continue
                rel = os.path.relpath(os.path.join(cur, n), root)
                if rel in seen:
                    continue
                seen.add(rel)
                lang = LANG_BY_EXT[ext]
                framework = ""
                if lang == "rust":
                    text = util.read_text(os.path.join(root, rel))
                    framework = next((name for name, pat in RUST_FRAMEWORKS if re.search(pat, text)), "")
                    if not framework:
                        skipped.append(f"{rel} (rust file with no recognised on-chain framework)")
                        continue
                files.append({"path": rel, "lang": lang, "framework": framework})
    return files, skipped


def nsloc(text: str, lang: str) -> int:
    """Non-blank lines minus lines that START with a comment marker. Deliberately crude — the
    same crude-but-cheap heuristic real nSLOC tools use as a first pass (a full comment-stripper is
    not worth the weight for a number that only orders review priority)."""
    marker = COMMENT_LINE.get(lang, r"^\s*(//|#)")
    n = 0
    for ln in text.split("\n"):
        if ln.strip() and not re.match(marker, ln):
            n += 1
    return n


def grep_entries(root: str, files: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Raw candidate entry points: file, line, the matched line's own text. Nothing classified.
    The agent reads each one and records permissionless / role-gated / admin from the real code —
    the discipline `references/xray.md` (Entry Point Scan) describes."""
    out: List[Dict[str, Any]] = []
    for f in files:
        lang = "anchor" if f.get("framework") == "anchor" else f["lang"]
        pats = ENTRY_PATTERNS.get(lang)
        if not pats:
            continue
        text = util.read_text(os.path.join(root, f["path"]))
        lines = text.split("\n")
        hit_lines = set()
        for pat in pats:
            for m in pat.finditer(text):
                hit_lines.add(text.count("\n", 0, m.start()) + 1)
        for ln in sorted(hit_lines):
            out.append({"file": f["path"], "line": ln, "lang": lang, "text": lines[ln - 1].strip()[:160]})
    return out


def _tests(root: str) -> Dict[str, Any]:
    t = {"test_files": 0, "test_functions": 0, "stateless_fuzz": 0, "foundry_invariant": 0, "echidna": 0,
         "medusa": 0, "halmos": 0, "certora_specs": 0, "fork": 0, "hardhat_tests": 0}
    for cur, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "lib", ".git", "out", "cache", "artifacts", "target", ".sieve")]
        for n in names:
            p = os.path.join(cur, n)
            rel = os.path.relpath(p, root)
            if n.endswith(".t.sol") or (n.endswith(".sol") and re.search(r"(^|/)tests?/", rel)):
                t["test_files"] += 1
                text = util.read_text(p)
                t["test_functions"] += len(re.findall(r"function\s+test\w*\s*\(", text))
                t["stateless_fuzz"] += len(re.findall(r"function\s+testFuzz\w*\s*\(", text))
                t["foundry_invariant"] += len(re.findall(r"function\s+invariant\w*\s*\(", text))
                t["echidna"] += len(re.findall(r"function\s+echidna_\w*\s*\(", text))
                t["medusa"] += len(re.findall(r"function\s+property_\w*\s*\(", text))
                t["halmos"] += len(re.findall(r"function\s+check_\w*\s*\(", text))
                if re.search(r"createFork|createSelectFork|vm\.rollFork", text):
                    t["fork"] += 1
            elif n.endswith(".spec"):
                t["certora_specs"] += 1
            elif re.search(r"\.(test|spec)\.(js|ts)$", n) and re.search(r"(^|/)tests?/", rel):
                t["hardhat_tests"] += 1
                t["test_functions"] += len(re.findall(r"\bit\s*\(", util.read_text(p)))
    return t


def _subsystem(path: str, src_dirs: List[str]) -> str:
    parts = path.split(os.sep)
    for sd in src_dirs:
        sdp = sd.strip("./").split("/") if sd not in (".", "") else []
        if sdp and parts[:len(sdp)] == sdp:
            parts = parts[len(sdp):]
            break
    return parts[0] if len(parts) > 1 else "(root)"


def _slither_leads(path: str) -> List[Dict[str, Any]]:
    """Slither's own `--json` output, reshaped into leads. Field names come straight from
    Slither's schema — never re-derived — so a schema change surfaces as a KeyError, not silence."""
    import json
    data = json.loads(util.read_text(path))
    out: List[Dict[str, Any]] = []
    for d in (data.get("results") or {}).get("detectors", []):
        elem = (d.get("elements") or [{}])[0]
        loc = (elem.get("source_mapping") or {})
        lines = loc.get("lines") or []
        out.append({"source": "slither", "check": d.get("check", ""), "impact": d.get("impact", ""),
                    "confidence": d.get("confidence", ""), "description": (d.get("description", "") or "")[:400],
                    "file": loc.get("filename_relative", ""), "line": lines[0] if lines else 0})
    return out


def _aderyn_leads(path: str) -> List[Dict[str, Any]]:
    """Aderyn's own `--output json` report, reshaped the same way as Slither's."""
    import json
    data = json.loads(util.read_text(path))
    out: List[Dict[str, Any]] = []
    for severity_key in ("high_issues", "medium_issues", "low_issues"):
        for issue in (data.get(severity_key) or {}).get("issues", []):
            for inst in issue.get("instances", [{}]):
                out.append({"source": "aderyn", "check": issue.get("title", ""),
                            "impact": severity_key.replace("_issues", ""), "confidence": "",
                            "description": (issue.get("description", "") or "")[:400],
                            "file": inst.get("contract_path", ""), "line": inst.get("line_no", 0)})
    return out


def deps_missing(root: str) -> Optional[str]:
    """Why a compile-based analyzer cannot work on this tree yet, or None. Slither and Aderyn compile the project;
    on a Hardhat project without node_modules or a Foundry project with empty submodules that means a long hang
    followed by a failure. Sieve never installs a target's dependencies itself (an install runs the target's own scripts),
    so it says what to do instead."""
    hardhat = any(os.path.isfile(os.path.join(root, n)) for n in
                  ("hardhat.config.ts", "hardhat.config.js", "hardhat.config.cjs", "hardhat.config.mjs"))
    if hardhat and not os.path.isdir(os.path.join(root, "node_modules")):
        return ("Hardhat project without node_modules: in a sandbox run `npm ci --ignore-scripts`, "
                "then `sieve scan --refresh`")
    if os.path.isfile(os.path.join(root, "foundry.toml")) and os.path.isfile(os.path.join(root, ".gitmodules")):
        lib = os.path.join(root, "lib")
        if not os.path.isdir(lib) or not os.listdir(lib):
            return "Foundry project whose lib/ submodules are not checked out: `git submodule update --init --recursive`, then `sieve scan --refresh`"
    return None


def _last_error(res: Any) -> str:
    """The last meaningful line a failed analyzer printed, so the coverage-debt note says why."""
    text = ((getattr(res, "stderr", "") or "") + chr(10) + (getattr(res, "stdout", "") or "")).strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    hit = next((l for l in reversed(lines) if any(w in l for w in ("Error", "error", "Exception", "failed", "Invalid"))), lines[-1] if lines else "no output")
    return hit[:220]


def _auto_run_slither(root: str, out_dir: str) -> Tuple[Optional[str], Optional[str]]:
    """Shell out to an installed `slither`, exactly the invocation `local-tooling.md` 2.1 names.
    Returns (json_path, failure_note) — exactly one is non-None. Slither's own exit code is not a
    reliable success signal (it can be non-zero purely because detectors fired), so success is
    judged by whether it wrote a parseable JSON file, not by its return code."""
    exe = shutil.which("slither")
    if not exe:
        return None, None
    why = deps_missing(root)
    if why:
        return None, f"slither: skipped, {why}"
    out_path = os.path.join(out_dir, "slither.json")
    cmd = [exe, root, "--json", out_path]
    try:
        res = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=AUTO_RUN_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return None, f"slither: auto-run timed out after {AUTO_RUN_TIMEOUT_SEC}s (coverage-debt — run manually with a longer budget)"
    except OSError as exc:
        return None, f"slither: auto-run failed to launch ({exc})"
    if not os.path.isfile(out_path):
        return None, f"slither: auto-run produced no JSON output (likely a compilation failure: check the project builds, then run manually). Its last error: {_last_error(res)}"
    return out_path, None


def _auto_run_aderyn(root: str, out_dir: str) -> Tuple[Optional[str], Optional[str]]:
    """Shell out to an installed `aderyn`, mirroring `_auto_run_slither`'s success/failure shape."""
    exe = shutil.which("aderyn")
    if not exe:
        return None, None
    why = deps_missing(root)
    if why:
        return None, f"aderyn: skipped, {why}"
    out_path = os.path.join(out_dir, "aderyn.json")
    cmd = [exe, root, "--output", out_path]
    try:
        res = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=AUTO_RUN_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return None, f"aderyn: auto-run timed out after {AUTO_RUN_TIMEOUT_SEC}s (coverage-debt — run manually with a longer budget)"
    except OSError as exc:
        return None, f"aderyn: auto-run failed to launch ({exc})"
    if not os.path.isfile(out_path):
        return None, f"aderyn: auto-run produced no JSON output (likely a compilation failure: check the project builds, then run manually). Its last error: {_last_error(res)}"
    return out_path, None


def _auto_run_trailmark(root: str, out_dir: str, target: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Shell out to an installed `trailmark` (`uv tool install trailmark`) to build a call/reference
    graph once — so xray Phase 1's call-chain tracing and blast-radius questions can become graph
    queries instead of a pure manual read (`local-tooling.md` 2.1). Best-effort: trailmark's CLI is
    young and its exact flags may drift between releases — a failed or malformed invocation here is
    coverage-debt, exactly like a slither/aderyn compile failure, never a blocker. A manual call-chain
    read is always the fallback when this doesn't run, not a requirement that it does."""
    exe = shutil.which("trailmark")
    if not exe:
        return None, None
    out_path = os.path.join(out_dir, "graph.json")
    # `trailmark analyze PATH --language auto` prints the graph as JSON on stdout (there is no --json flag). Point it at the
    # source directory, not the repo root: a root with node_modules or a frontend makes it parse a lot of unrelated code.
    cmd = [exe, "analyze", target if target and os.path.isdir(target) else root, "--language", "auto"]
    try:
        result = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=AUTO_RUN_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return None, f"trailmark: auto-run timed out after {AUTO_RUN_TIMEOUT_SEC}s (coverage-debt — run manually)"
    except OSError as exc:
        return None, f"trailmark: auto-run failed to launch ({exc})"
    if not result.stdout.strip():
        return None, ("trailmark: auto-run produced no output (its CLI may have changed since — "
                       "run `trailmark --help` and wire manually, local-tooling.md 2.1)")
    try:
        util.atomic_write(out_path, result.stdout)
    except OSError as exc:
        return None, f"trailmark: failed to write {out_path} ({exc})"
    return out_path, None


def _mark_corroboration(leads: List[Dict[str, Any]]) -> None:
    """Two independent detector engines flagging the same file:line is a meaningfully higher-
    confidence signal than either one alone (different dataflow analyses, different implementations,
    same conclusion). Mutates `leads` in place, adding `corroborated: bool` to every entry — never
    drops or reorders anything; `judging.md`'s triage routing is free to use this, not required to."""
    for a in leads:
        a.setdefault("corroborated", False)
    for i, a in enumerate(leads):
        if not a.get("file") or not a.get("line"):
            continue
        for j, b in enumerate(leads):
            if i == j or a.get("source") == b.get("source") or not b.get("file"):
                continue
            if a["file"] == b["file"] and abs(int(a.get("line") or 0) - int(b.get("line") or 0)) <= 2:
                a["corroborated"] = True
                b["corroborated"] = True


def run(root: str, src_dirs: Optional[List[str]] = None, slither_json: Optional[str] = None,
        aderyn_json: Optional[str] = None, auto_static: bool = True) -> Dict[str, Any]:
    root = os.path.abspath(root)
    if os.environ.get("SIEVE_NO_STATIC") == "1":   # tests and air-gapped runs: skip the auto-invoked analyzers
        auto_static = False
    dirs = src_dirs or detect_src_dirs(root)
    files, skipped = discover(root, dirs)
    by_sub: Dict[str, int] = defaultdict(int)
    total = 0
    for f in files:
        f["nsloc"] = nsloc(util.read_text(os.path.join(root, f["path"])), f["lang"])
        total += f["nsloc"]
        by_sub[_subsystem(f["path"], dirs)] += f["nsloc"]

    leads: List[Dict[str, Any]] = []
    notes: List[str] = []
    auto_ran: List[str] = []
    auto_failed: Dict[str, str] = {}
    out_dir = os.path.join(root, ".sieve", "xray")

    # Static analysis is the mechanical layer's first move, not operator-supplied corroboration:
    # auto-invoke every installed tool unless the caller already handed us a report or opted out.
    results: Dict[str, Any] = {}
    if auto_static:
        os.makedirs(out_dir, exist_ok=True)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as pool:      # the three analyzers are independent: run them side by side
            futs = {}
            if not slither_json:
                futs["slither"] = pool.submit(_auto_run_slither, root, out_dir)
            if not aderyn_json:
                futs["aderyn"] = pool.submit(_auto_run_aderyn, root, out_dir)
            src0 = os.path.join(root, dirs[0]) if dirs else None
            futs["trailmark"] = pool.submit(_auto_run_trailmark, root, out_dir, src0)
            results = {k: f.result() for k, f in futs.items()}
        for name in ("slither", "aderyn"):
            if name in results:
                path_, note = results[name]
                if name == "slither":
                    slither_json = path_ or slither_json
                else:
                    aderyn_json = path_ or aderyn_json
                if path_:
                    auto_ran.append(name)
                elif note:
                    auto_failed[name] = note

    for path, loader, name in ((slither_json, _slither_leads, "slither"), (aderyn_json, _aderyn_leads, "aderyn")):
        if not path:
            if name in auto_failed:
                notes.append(auto_failed[name])
            else:
                notes.append(f"{name}: not installed / no report supplied — coverage-debt (local-tooling.md 2.1)")
            continue
        try:
            leads += loader(path)
        except (OSError, ValueError, KeyError) as exc:
            notes.append(f"{name} {path}: {exc}")

    _mark_corroboration(leads)

    graph_path = None
    if auto_static:
        graph_path, note = results.get("trailmark", (None, None))
        if graph_path:
            auto_ran.append("trailmark")
        elif note:
            notes.append(note)
        else:
            notes.append("trailmark: not installed, call-chain tracing stays manual "
                         "(optional accelerant, not coverage-debt; local-tooling.md 2.1)")

    return {"pack": "web3", "root": root, "generated": util.now_iso(), "src_dirs": dirs,
            "languages": sorted({f["lang"] for f in files}), "files": files, "skipped": skipped,
            "nsloc_total": total, "by_subsystem": dict(by_sub),
            "entry_candidates": grep_entries(root, files), "tests": _tests(root),
            "tool_leads": leads, "auto_ran": auto_ran, "graph_path": graph_path, "notes": notes}
