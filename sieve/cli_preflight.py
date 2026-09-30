"""`sieve preflight` and `sieve config`: know what works before an audit starts, and read settings without opening yaml."""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

from . import preflight, util
from .config import load_config
from .state import Engagement


def cmd_preflight(args: argparse.Namespace) -> int:
    eng = Engagement.find()
    cfg = load_config(eng.root if eng else None)
    checks = preflight.run(cfg, identity=not args.no_identity, mcp=not args.no_mcp)
    ready = preflight.readiness(checks)
    if args.json:
        print(json.dumps({"checks": checks, "readiness": ready}, indent=2))
    else:
        mark = {"ok": "✓", "warn": "!", "fail": "✗", "info": "·"}
        area = ""
        for c in checks:
            if c["area"] != area:
                area = c["area"]
                print(f"\n[{area}]")
            print(f"  {mark[c['status']]} {c['name']:<28} {c['detail'][:150]}")
            if c["fix"] and c["status"] in ("warn", "fail"):
                print(f"      fix: {c['fix']}")
        print("\nreadiness: " + "   ".join(f"{p}: {s}" for p, s in ready.items()))
    if eng:
        util.atomic_write(eng.path("preflight.md"), preflight.render(checks, ready))
        if not args.json:
            print(f"\nwritten to {os.path.relpath(eng.path('preflight.md'), eng.root)}: every gap a run proceeds without is coverage debt")
    return 1 if any(c["status"] == "fail" for c in checks) else 0


def cmd_config(args: argparse.Namespace) -> int:
    eng = Engagement.find()
    cfg = load_config(eng.root if eng else None)
    if args.ccmd == "get":
        v = cfg.get(args.key)
        if v is None:
            raise SystemExit(f"sieve config: {args.key} is not set")
        print(json.dumps(v) if isinstance(v, (dict, list)) else v)
    else:
        print(json.dumps(cfg.raw, indent=2, default=str))
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("preflight", help="exercise every tool an audit depends on (Burp, CloakBrowser identity, MCP servers, KB, hook) and print the fixes")
    p.add_argument("--no-identity", action="store_true", help="skip opening the browser profile (faster)")
    p.add_argument("--no-mcp", action="store_true", help="skip `claude mcp list`")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("config", help="read a setting (e.g. `sieve config get external.v12.max_cost_cents`)")
    cs = p.add_subparsers(dest="ccmd", required=True)
    q = cs.add_parser("get")
    q.add_argument("key")
    cs.add_parser("show")
    p.set_defaults(func=cmd_config)
