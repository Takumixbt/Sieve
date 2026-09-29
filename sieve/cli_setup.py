"""`sieve doctor` and `sieve lint` — environment check and skill self-check."""
from __future__ import annotations

import argparse
import glob
import os
import subprocess
from typing import Any, Dict, List, Tuple

from . import hook as hooklib
from . import repo_root, tooling, util, vectors
from .config import load_config

def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config()
    print(f"sieve home: {repo_root()}\n")
    missing_total = 0
    for pack in ("prereq", "web", "web3", "binary"):
        rows = tooling.load(pack)
        print(f"[{pack}]")
        for t in rows:
            st = tooling.status(t)
            mark = {"ok": "\u2713", "missing": "\u00b7", "manual": "?"}[st]
            missing_total += st == "missing"
            path = tooling.find_bin(t["bin"]) if t["bin"] else None
            print(f"  {mark} {t['name'][:24]:<24} {t['job'][:70]}" + (f"  ({path})" if path and args.verbose else ""))
        print()
    print("[knowledge base]")
    for name in ("solodit", "osv", "nvd"):
        sc = cfg.source(name)
        env = sc.get("api_key_env")
        have = bool(env and os.environ.get(str(env)))
        status = "n/a (no key needed)" if not env else ("set" if have else f"MISSING ({env})")
        print(f"  {name:<8} enabled={sc.get('enabled')}  key={status}")
    print()
    print("[persistence]")
    found = hooklib.installed()
    print(f"  Stop hook \u2014 user: {found['user']}  project: {found['project']}")
    if not any(found.values()):
        print("  install with: sieve hooks install --scope user")
    print()
    if missing_total:
        print(f"{missing_total} tool(s) missing \u2014 `sieve install <prereq|web|web3|binary>` prints the commands "
              "(add --run to execute them). '?' = no binary to probe (manual install or a library).")
    print("A missing tool is not an error \u2014 it's coverage-debt, printed in the final report.")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    rows = tooling.load(args.group)
    if args.only:
        rows = [t for t in rows if t["name"].lower() == args.only.lower()]
    if not rows:
        raise SystemExit(f"sieve install: nothing matches {args.group!r}" + (f" / {args.only!r}" if args.only else "")
                         + f" (groups: {', '.join(tooling.GROUPS)})")
    todo = []
    for t in rows:
        st = tooling.status(t)
        if st == "ok":
            print(f"  \u2713 {t['name']:<24} already installed")
        elif t["command"]:
            print(f"  \u00b7 {t['name']:<24} {t['command']}")
            todo.append(t)
        else:
            print(f"  ? {t['name']:<24} manual: {t['install']}")
    if not args.run:
        if todo:
            print(f"\n{len(todo)} command(s) above are dry-run only. Re-run with --run to execute them "
                  "(sudo/network access as the commands need).")
        return 0
    if not todo:
        return 0
    if not args.yes:
        ans = input(f"\nRun {len(todo)} install command(s) shown above on this machine? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("aborted; nothing was run")
            return 1
    failed = 0
    for t in todo:
        print(f"\n$ {t['command']}")
        rc = subprocess.call(["sh", "-c", t["command"]])
        ok = rc == 0 and (not t["bin"] or tooling.find_bin(t["bin"]) is not None)
        print(f"  -> {'installed' if ok else 'FAILED or not on PATH yet'} ({t['name']})")
        failed += not ok
    if failed:
        print(f"\n{failed} install(s) need attention (open a new shell for PATH changes, then `sieve doctor`).")
    return 1 if failed else 0


def cmd_lint(args: argparse.Namespace) -> int:
    problems: List[str] = []

    cards = vectors.load_all()
    problems += vectors.validate(cards)

    packs_dir = os.path.join(repo_root(), "packs")
    for pack in sorted(os.listdir(packs_dir)):
        adir = os.path.join(packs_dir, pack, "agents")
        if not os.path.isdir(adir):
            continue
        for f in sorted(glob.glob(os.path.join(adir, "*.md"))):
            meta, _body = _frontmatter_or_none(f)
            if meta is None:
                problems.append(f"{os.path.relpath(f, repo_root())}: missing YAML frontmatter")
                continue
            for req in ("name", "owns", "tier"):
                if req not in meta:
                    problems.append(f"{os.path.relpath(f, repo_root())}: frontmatter missing `{req}`")

    readme = os.path.join(repo_root(), "agents", "README.md")
    if os.path.isfile(readme):
        text = util.read_text(readme)
        for pack in ("web3", "web", "binary", "seams"):
            adir = os.path.join(packs_dir, pack, "agents")
            for f in sorted(glob.glob(os.path.join(adir, "*.md"))) if os.path.isdir(adir) else []:
                name = os.path.splitext(os.path.basename(f))[0]
                if name not in text:
                    problems.append(f"agents/README.md: {pack}/{name} is not listed in the roster table")

    for pack in ("web3", "web", "binary"):
        jp = os.path.join(packs_dir, pack, "judging.md")
        if not os.path.isfile(jp):
            problems.append(f"packs/{pack}/judging.md is missing (referenced by references/judging.md)")

    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"clean: {len(cards)} vector card(s), all agent files and pack judging.md present")
    return 0


def _frontmatter_or_none(path: str):
    from . import yamlish
    try:
        return yamlish.split_frontmatter(util.read_text(path))
    except yamlish.YamlError:
        return None, ""


def register(sub: Any) -> None:
    p = sub.add_parser("doctor", help="check installed tools, KB keys, and hook status")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("install", help="print (or, with --run, execute) install commands from references/local-tooling.md")
    p.add_argument("group", choices=list(tooling.GROUPS), help="prereq | web | web3 | web3-chains | binary")
    p.add_argument("--run", action="store_true", help="execute the missing tools' install commands")
    p.add_argument("--yes", action="store_true", help="don't ask for confirmation before --run")
    p.add_argument("--only", help="a single tool by name")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("lint", help="validate vector cards and agent frontmatter")
    p.set_defaults(func=cmd_lint)
