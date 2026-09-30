"""`sieve leads ...`: fold another tool's output into the work queue as leads."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import leads
from .state import Engagement


def cmd_add(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    try:
        res = leads.add(eng, {"source": args.source, "title": args.title, "file": args.file, "line": args.line,
                              "severity": args.severity, "detail": args.detail, "ref": args.ref, "pack": args.pack})
    except ValueError as exc:
        raise SystemExit(f"sieve leads add: {exc}")
    print(f"{res['leads']} lead(s) on record; frontier +{res['added']}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    data = json.load(sys.stdin) if args.file == "-" else json.load(open(args.file, encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("findings") or data.get("leads") or []
    bad = 0
    for raw in items:
        if isinstance(raw, dict):
            raw = dict(raw, source=raw.get("source") or args.source)
            try:
                leads.add(eng, raw)
            except ValueError:
                bad += 1
    res = leads.apply(eng)
    print(f"imported {len(items) - bad} lead(s) ({bad} skipped as malformed); {res['leads']} on record; frontier +{res['added']}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    for l in leads.load(eng):
        print(f"[{l['severity']:<8}] {l['source']:<10} {leads.component(l)}")
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("leads", help="fold another tool's findings (V12, Burp scanner, nuclei) into the work queue as leads")
    ls = p.add_subparsers(dest="lcmd", required=True)
    q = ls.add_parser("add")
    q.add_argument("--source", required=True, help="v12, burp, nuclei, ...")
    q.add_argument("--title", required=True)
    q.add_argument("--file", default="")
    q.add_argument("--line", type=int, default=0)
    q.add_argument("--severity", default="medium", choices=["critical", "high", "medium", "low", "informational"])
    q.add_argument("--detail", default="")
    q.add_argument("--ref", default="", help="a URL or run id where the tool's own evidence lives")
    q.add_argument("--pack", default="")
    q.set_defaults(func=cmd_add)
    q = ls.add_parser("import", help="a JSON list of leads, or `-` for stdin")
    q.add_argument("file")
    q.add_argument("--source", default="external")
    q.set_defaults(func=cmd_import)
    q = ls.add_parser("list")
    q.set_defaults(func=cmd_list)
