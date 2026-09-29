"""Git-history security pass: where was this code hurried, patched, forked, or left half-done?

Scoped to the current branch (HEAD) only. Describes what the history shows, never what another
branch might contain. Works for any language; the dangerous-area patterns cover all three packs.
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from . import util

SRC_EXT = {".sol", ".vy", ".move", ".rs", ".cairo", ".go", ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt",
           ".swift", ".m", ".mm", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".rb", ".php", ".cs", ".scala",
           ".sh", ".yul", ".fc", ".func", ".tolk"}
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|specs?|fuzz|invariants?|mocks?)(/|$)|\.t\.sol$|_test\.(go|py|rs|c|cc|cpp)$|"
                     r"\.(test|spec)\.(js|jsx|ts|tsx)$|Tests?\.(java|kt|swift)$", re.I)

FIX_PATTERNS: List[Tuple[str, int, str]] = [
    (r"\bfix(es|ed|ing)?\b", 3, "fix"),
    (r"\bbug\b", 2, "bug"),
    (r"vuln|security|cve-\d|exploit", 4, "security wording"),
    (r"reentran|overflow|underflow|race condition|toctou|injection|xss|csrf|ssrf|sqli|idor|bypass|escalat|leak|"
     r"\bdos\b|denial of service|use[- ]after|double[- ]free|out[- ]of[- ]bounds|oob", 4, "vulnerability class named"),
    (r"\b(auth|authz|permission|access control|validat\w*|sanitiz\w*|escap\w*|bounds?|check(s|ed)?)\b", 2, "hardening wording"),
    (r"hotfix|patch|regress|revert", 2, "patch/revert"),
    (r"audit|finding|issue #?\d+|report", 1, "audit/report reference"),
]
GUARD_ADD = re.compile(r"\b(require|assert|revert|check|validate|onlyOwner|onlyRole|nonReentrant|memcmp|strncpy|"
                       r"snprintf|sizeof|bounds|len\(|isAuthenticated|authorize|sanitize|escape)\b|^\+\s*if\s*\(", re.I)

AREAS: Dict[str, str] = {
    "access_control": r"onlyowner|onlyrole|access|auth|permission|acl|role|owner|admin|policy|guard",
    "fund_flows": r"transfer|withdraw|deposit|mint|burn|borrow|repay|swap|payout|settle|escrow|vault|treasury|payment",
    "oracle_price": r"oracle|price|twap|feed|rate|quote",
    "signatures_identity": r"sign|ecrecover|permit|nonce|jwt|token|session|oauth|saml|login|password|credential",
    "upgrade_init": r"proxy|upgrade|initializ|migrat|implementation",
    "input_parsing": r"pars|decod|deserial|unmarshal|upload|import|render|template|xml|yaml|json|protocol|packet",
    "memory_native": r"alloc|free|buffer|memcpy|strcpy|copy|string|array|vector|arena|pool",
    "crypto": r"crypt|hash|key|cipher|random|rng|tls|cert|hmac|kdf",
}
FORK_LIBS = ["openzeppelin", "solmate", "solady", "uniswap", "aave", "compound", "chainlink", "curve", "balancer",
             "zeppelin", "prb-math", "forge-std", "openssl", "libpng", "zlib", "sqlite", "curl", "lodash", "jquery"]
VENDOR_DIRS = ("third_party/", "third-party/", "vendor/", "deps/", "external/", "extern/")


def _git(repo: str, *args: str, timeout: int = 60) -> str:
    rc, out, _err = util.run(["git", "-C", repo, *args], timeout=timeout)
    return out if rc == 0 else ""


def _is_src(path: str, src_prefixes: Optional[List[str]]) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext not in SRC_EXT or TEST_RE.search(path):
        return False
    if src_prefixes:
        return any(path.startswith(p.rstrip("/") + "/") or path == p for p in src_prefixes)
    return True


def _parse_log(repo: str, n: int) -> List[Dict[str, Any]]:
    fmt = "%x1e%H%x1f%an%x1f%ad%x1f%s%x1f%P"
    out = _git(repo, "log", "-n", str(n), "--date=short", f"--format={fmt}", "--numstat", timeout=120)
    commits: List[Dict[str, Any]] = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        lines = rec.split("\n")
        parts = lines[0].split("\x1f")
        if len(parts) < 5:
            continue
        files = []
        for ln in lines[1:]:
            m = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", ln)
            if m:
                files.append({"path": m.group(3).split(" => ")[-1].strip("{}"),
                              "add": 0 if m.group(1) == "-" else int(m.group(1)),
                              "del": 0 if m.group(2) == "-" else int(m.group(2))})
        commits.append({"sha": parts[0], "author": parts[1], "date": parts[2], "subject": parts[3],
                        "merge": len(parts[4].split()) > 1, "files": files})
    return commits


def analyze(repo: str, src_dirs: Optional[List[str]] = None, late_days: int = 30,
            max_commits: int = 1500) -> Dict[str, Any]:
    repo = os.path.abspath(repo)
    if not os.path.isdir(os.path.join(repo, ".git")) and not _git(repo, "rev-parse", "--git-dir").strip():
        return {"meta": {"git": False}, "repo_shape": {"shape": "no_git", "note": "not a git repository"}}
    head = _git(repo, "rev-parse", "HEAD").strip()
    if not head:
        return {"meta": {"git": True}, "repo_shape": {"shape": "no_git", "note": "repository has no commits"}}
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    total = int((_git(repo, "rev-list", "--count", "HEAD").strip() or "0"))
    log = _parse_log(repo, max_commits)
    nonmerge = [c for c in log if not c["merge"]]
    merges = [c for c in log if c["merge"]]
    # the merge-excluded log above only has numstat for non-merge commits; merges counted from parents
    all_log = _parse_log_merges(repo, max_commits)
    if all_log is not None:
        merges = all_log
    result: Dict[str, Any] = {"meta": {"git": True, "branch": branch, "head": head[:12], "commits_analysed": len(log),
                                       "truncated": total > max_commits, "src_dirs": src_dirs or []}}
    dates = sorted(c["date"] for c in log) or [""]
    result["repo_shape"] = {
        "shape": "squashed_import" if total <= 1 else "normal_dev",
        "commits": total, "first": dates[0], "last": dates[-1], "merge_commits": len(merges),
        "contributors": len({c["author"] for c in log}),
        "note": ("All source arrived in one commit; there is no development history to analyse."
                 if total <= 1 else ""),
    }
    # ---- contributors (source lines only)
    by_author: Dict[str, Dict[str, int]] = defaultdict(lambda: {"commits": 0, "add": 0, "del": 0})
    total_add = 0
    for c in nonmerge:
        touched = False
        for f in c["files"]:
            if _is_src(f["path"], src_dirs):
                by_author[c["author"]]["add"] += f["add"]
                by_author[c["author"]]["del"] += f["del"]
                total_add += f["add"]
                touched = True
        if touched:
            by_author[c["author"]]["commits"] += 1
    result["contributors"] = sorted(
        ({"author": a, **v, "pct_of_source_added": round(100.0 * v["add"] / total_add, 1) if total_add else 0.0}
         for a, v in by_author.items()), key=lambda x: -x["add"])[:12]
    # ---- hotspots
    hot: Counter = Counter()
    for c in nonmerge:
        for f in c["files"]:
            if _is_src(f["path"], src_dirs):
                hot[f["path"]] += 1
    result["hotspots"] = [{"file": p, "modifications": n} for p, n in hot.most_common(15)]
    # ---- fix candidates
    cands: List[Dict[str, Any]] = []
    for c in nonmerge:
        src_files = [f for f in c["files"] if _is_src(f["path"], src_dirs)]
        if not src_files:
            continue
        score, reasons = 0, []
        subj = c["subject"].lower()
        for pat, w, why in FIX_PATTERNS:
            if re.search(pat, subj):
                score += w
                reasons.append(why)
        if score == 0:
            continue
        if len(src_files) <= 3:
            score += 1
            reasons.append("focused change")
        adds = sum(f["add"] for f in src_files)
        dels = sum(f["del"] for f in src_files)
        if dels > adds:
            score += 1
            reasons.append("deletes more than it adds")
        cands.append({"sha": c["sha"][:12], "date": c["date"], "subject": c["subject"][:100], "score": score,
                      "reasons": reasons, "files": [f["path"] for f in src_files][:4], "_full": c["sha"]})
    cands.sort(key=lambda x: -x["score"])
    for x in cands[:12]:  # diff-level signal only for the strongest candidates (keeps this fast)
        patch = _git(repo, "show", "--unified=0", "--format=", x["_full"], "--", *x["files"], timeout=60)
        added_guards = [ln for ln in patch.split("\n") if ln.startswith("+") and not ln.startswith("+++")
                        and GUARD_ADD.search(ln)]
        if added_guards:
            x["score"] += 2
            x["reasons"].append(f"adds guard-like lines ({len(added_guards)})")
    for x in cands:
        x.pop("_full", None)
    cands.sort(key=lambda x: -x["score"])
    result["fix_candidates"] = cands[:20]
    # ---- dangerous areas
    area_commits: Dict[str, set] = defaultdict(set)
    area_files: Dict[str, Counter] = defaultdict(Counter)
    for c in nonmerge:
        for f in c["files"]:
            if not _is_src(f["path"], src_dirs):
                continue
            for area, pat in AREAS.items():
                if re.search(pat, f["path"], re.I) or re.search(pat, c["subject"], re.I):
                    area_commits[area].add(c["sha"])
                    area_files[area][f["path"]] += 1
    result["dangerous_area_changes"] = sorted(
        ({"area": a, "commits": len(s), "key_files": [p for p, _ in area_files[a].most_common(3)]}
         for a, s in area_commits.items()), key=lambda x: -x["commits"])
    # ---- late changes
    late: List[Dict[str, Any]] = []
    if log and total > 1:
        head_date = max(c["date"] for c in log)
        cutoff = _shift_date(head_date, -late_days)
        for c in nonmerge:
            if c["date"] >= cutoff:
                src = [f for f in c["files"] if _is_src(f["path"], src_dirs)]
                if src:
                    size = sum(f["add"] + f["del"] for f in src)
                    late.append({"sha": c["sha"][:12], "date": c["date"], "subject": c["subject"][:90],
                                 "lines": size, "large": size > 200, "files": len(src)})
        late.sort(key=lambda x: -x["lines"])
    result["late_changes"] = {"window_days": late_days, "commits": len(late), "top": late[:12]}
    # ---- forked dependencies
    tracked = _git(repo, "ls-files").split("\n")
    subs = {}
    gm = os.path.join(repo, ".gitmodules")
    if os.path.isfile(gm):
        cur = None
        for ln in util.read_text(gm).split("\n"):
            m = re.match(r'\s*\[submodule "(.+)"\]', ln)
            if m:
                cur = m.group(1)
                subs[cur] = {}
            elif cur and "=" in ln:
                k, v = [x.strip() for x in ln.split("=", 1)]
                subs[cur][k] = v
    forked: List[Dict[str, str]] = []
    seen_paths: set = set()
    for name, d in subs.items():
        forked.append({"library": name, "path": d.get("path", name), "status": "submodule", "upstream": d.get("url", "")})
        seen_paths.add(d.get("path", name))
    for p in tracked:
        pl = p.lower()
        top = "/".join(p.split("/")[:2])
        if top in seen_paths:
            continue
        for lib in FORK_LIBS:
            if lib in pl and (pl.startswith(("lib/", "contracts/lib/", "src/lib/", "node_modules/")) or
                              any(pl.startswith(v) for v in VENDOR_DIRS) or "/vendor/" in pl or "/third_party/" in pl):
                key = f"{lib}@{top}"
                if key not in seen_paths:
                    seen_paths.add(key)
                    forked.append({"library": lib, "path": top, "status": "internalized (tracked in repo)", "upstream": ""})
                break
    result["forked_deps"] = forked[:25]
    # ---- tech debt
    grep = _git(repo, "grep", "-nIE", r"(TODO|FIXME|HACK|XXX)\b", "--", *[f"*{e}" for e in sorted(SRC_EXT)], timeout=60)
    debt: List[Dict[str, Any]] = []
    for ln in grep.split("\n"):
        m = re.match(r"^(.+?):(\d+):(.*)$", ln)
        if not m or TEST_RE.search(m.group(1)):
            continue
        if src_dirs and not _is_src(m.group(1), src_dirs):
            continue
        debt.append({"file": m.group(1), "line": int(m.group(2)),
                     "text": m.group(3).strip()[:140],
                     "type": re.search(r"(TODO|FIXME|HACK|XXX)", m.group(3)).group(1)})
    result["tech_debt"] = {"total": len(debt), "items": debt[:40]}
    for item in result["tech_debt"]["items"][:15]:
        blame = _git(repo, "blame", "-L", f"{item['line']},{item['line']}", "--porcelain", "--", item["file"])
        am = re.search(r"^author (.+)$", blame, re.M)
        tm = re.search(r"^author-time (\d+)", blame, re.M)
        if am:
            item["author"] = am.group(1)
        if tm:
            import datetime as _dt
            item["date"] = _dt.datetime.fromtimestamp(int(tm.group(1)), _dt.timezone.utc).strftime("%Y-%m-%d")
    # ---- dev patterns
    src_commits = [c for c in nonmerge if any(_is_src(f["path"], src_dirs) for f in c["files"])]
    with_tests = [c for c in src_commits if any(TEST_RE.search(f["path"]) and
                                                os.path.splitext(f["path"])[1].lower() in SRC_EXT for f in c["files"])]
    result["dev_patterns"] = {
        "source_commits": len(src_commits),
        "test_co_change_rate_pct": round(100.0 * len(with_tests) / len(src_commits), 1) if src_commits else 0.0,
        "note": "test_co_change_rate measures files modified together in a commit; it is NOT test coverage.",
        "merge_ratio_pct": round(100.0 * len(merges) / max(1, len(log) + len(merges)), 1),
    }
    return result


def _parse_log_merges(repo: str, n: int) -> Optional[List[Dict[str, Any]]]:
    out = _git(repo, "log", "-n", str(n), "--merges", "--format=%H")
    return [{"sha": s} for s in out.split() if s] if out is not None else None


def _shift_date(d: str, days: int) -> str:
    import datetime as _dt
    try:
        return (_dt.date.fromisoformat(d) + _dt.timedelta(days=days)).isoformat()
    except ValueError:
        return d
