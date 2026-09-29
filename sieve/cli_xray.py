"""`sieve xray ...` — run the mechanical enumerators and write .sieve/xray/facts.json.

Thin on purpose: every function here already exists in xray_git / xray_web3 / xray_web and does
counting, discovery, or grep — never classification. Classification is the agent's job, done by
reading the source this writes pointers to, per references/xray.md.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List

from . import util, xray_git, xray_web, xray_web3
from .state import Engagement


def _write_facts(eng: Engagement, facts: Dict[str, Any]) -> str:
    os.makedirs(eng.path("xray"), exist_ok=True)
    path = eng.path("xray", "facts.json")
    existing = util.read_json(path, {}) or {}
    existing[facts["pack"]] = facts
    util.write_json(path, existing)
    return path


def cmd_web3(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    facts = xray_web3.run(eng.root, slither_json=args.slither, aderyn_json=args.aderyn,
                           auto_static=not args.no_auto_static)
    path = _write_facts(eng, facts)
    if facts["auto_ran"]:
        print(f"static analysis: auto-ran {', '.join(facts['auto_ran'])} (local-tooling.md 2.1) "
              f"— .sieve/xray/{{tool}}.json written")
    print(f"web3: {len(facts['files'])} file(s), {facts['nsloc_total']} nSLOC, "
          f"{len(facts['entry_candidates'])} entry-point candidate(s), {len(facts['tool_leads'])} tool lead(s)")
    for n in facts["skipped"] + facts["notes"]:
        print(f"note: {n}")
    print(f"wrote {path}\nNEXT: read entry_candidates + tool_leads, then write xray/entry-points.md, "
          f"xray/invariants.md, xray/architecture.json per references/xray.md")
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    facts = xray_web.run(openapi=args.openapi, har=args.har, url_lists=args.url_list)
    path = _write_facts(eng, facts)
    header, rows = xray_web.surface_tsv(facts)
    util.write_tsv(eng.path("xray", "surface.tsv"), header, rows)
    print(f"web: {facts['counts']['endpoints']} endpoint(s) merged, "
          f"{facts['counts']['auth_unknown_or_no']} without confirmed auth")
    for n in facts["notes"]:
        print(f"note: {n}")
    print(f"wrote {path} and xray/surface.tsv\nNEXT: read surface.tsv, mark auth/object-ref by hand where "
          f"'unknown', then dispatch the web agents")
    return 0


def cmd_git(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    result = xray_git.analyze(eng.root, src_dirs=args.src)
    util.write_json(eng.path("xray", "git-security.json"), result)
    shape = result["repo_shape"]["shape"]
    print(f"repo shape: {shape}")
    if shape == "normal_dev":
        print(f"{len(result['fix_candidates'])} fix candidate(s), {len(result['hotspots'])} hotspot(s), "
              f"{result['tech_debt']['total']} tech-debt marker(s)")
    print(f"wrote {eng.path('xray', 'git-security.json')}")
    return 0


def cmd_map(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    arch = eng.path("xray", "architecture.json")
    if not os.path.isfile(arch):
        raise SystemExit(f"sieve map: write {arch} first (see references/xray.md's architecture.json format)")
    import subprocess
    import sys
    script = os.path.join(os.path.dirname(__file__), os.pardir, "scripts", "generate_svg.py")
    svg = eng.path("xray", "architecture.svg")
    rc = subprocess.call([sys.executable, script, arch, svg])
    if rc == 0:
        print(f"wrote {svg}")
    return rc


def register(sub: Any) -> None:
    p = sub.add_parser("xray", help="run the mechanical enumerators")
    xs = p.add_subparsers(dest="xcmd", required=True)

    q = xs.add_parser("web3")
    q.add_argument("--slither", help="path to `slither . --json <path>` output "
                   "(skips the auto-run if given)")
    q.add_argument("--aderyn", help="path to `aderyn . --output <path>` output "
                   "(skips the auto-run if given)")
    q.add_argument("--no-auto-static", action="store_true",
                   help="don't auto-invoke installed slither/aderyn — leave the gap as coverage-debt")
    q.set_defaults(func=cmd_web3)

    q = xs.add_parser("web")
    q.add_argument("--openapi", action="append", default=[])
    q.add_argument("--har", action="append", default=[])
    q.add_argument("--url-list", action="append", default=[], dest="url_list",
                   help="one URL per line (httpx/katana/gau output)")
    q.set_defaults(func=cmd_web)

    q = xs.add_parser("git", help="the git-history security pass")
    q.add_argument("--src", action="append", help="source dir(s) to scope the pass to")
    q.set_defaults(func=cmd_git)

    q = xs.add_parser("map", help="render xray/architecture.json to architecture.svg")
    q.set_defaults(func=cmd_map)
