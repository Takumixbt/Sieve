"""`sieve doctor` and `sieve lint` — environment check and skill self-check."""
from __future__ import annotations

import argparse
import glob
import os
from typing import Any, Dict, List, Tuple

from . import hook as hooklib
from . import repo_root, util, vectors
from .config import load_config

TOOLS: Dict[str, List[Tuple[str, str]]] = {
    "web": [("subfinder", "recon"), ("httpx", "recon"), ("katana", "recon"), ("nuclei", "recon"),
            ("ffuf", "active"), ("gau", "recon"), ("sqlmap", "injection confirmation"),
            ("dalfox", "XSS confirmation")],
    "web3": [("forge", "PoC / fork tests"), ("slither", "static corroboration"),
             ("aderyn", "static corroboration"), ("myth", "symbolic execution"),
             ("semgrep", "pattern rules")],
    "binary": [("checksec", "mitigation triage"), ("readelf", "triage"), ("strings", "triage"),
               ("r2", "reverse engineering"), ("frida", "mobile dynamic"),
               ("objection", "mobile dynamic"), ("jadx", "mobile static"), ("apktool", "mobile static"),
               ("adb", "mobile static/dynamic")],
}


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config()
    print(f"sieve home: {repo_root()}")
    print()
    for pack, tools in TOOLS.items():
        print(f"[{pack}]")
        for name, use in tools:
            path = util.which(name)
            mark = "✓" if path else "·"
            print(f"  {mark} {name:<12} {use}" + (f"  ({path})" if path and args.verbose else ""))
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
    print(f"  Stop hook — user: {found['user']}  project: {found['project']}")
    if not any(found.values()):
        print("  install with: sieve hooks install --scope user")
    print()
    print("A missing tool is not an error — it's coverage-debt, printed in the final report.")
    return 0


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

    p = sub.add_parser("lint", help="validate vector cards and agent frontmatter")
    p.set_defaults(func=cmd_lint)
