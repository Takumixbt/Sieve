"""`sieve report` — assemble the deliverable from findings and their machine-computed validation tier."""
from __future__ import annotations

import argparse
import json
from typing import Any

from . import report
from .state import Engagement


def cmd_report(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    path = report.write(eng)
    _text, counts = report.build(eng)
    print(f"wrote {path}")
    print(json.dumps(counts, indent=2))
    if counts["broken"]:
        print(f"warning: {counts['broken']} finding file(s) failed to parse — see the report's warning block")
    if counts["unvalidated"] or counts["tampered"] or counts["stale"]:
        print(f"note: {counts['unvalidated']} unvalidated, {counts['stale']} stale, {counts['tampered']} tampered — "
              f"none of them is printed as a confirmed finding")
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("report", help="assemble the deliverable (prints only what the machine confirmed as confirmed)")
    p.set_defaults(func=cmd_report)
