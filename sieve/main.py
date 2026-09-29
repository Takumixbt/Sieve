"""`sieve` command line. Each feature module contributes its own subcommands via register()."""
from __future__ import annotations

import argparse
import importlib
import sys
from typing import List

from . import __version__

MODULES = [
    "sieve.cli_core",
    "sieve.cli_kb",
    "sieve.cli_vault",
    "sieve.cli_xray",
    "sieve.cli_findings",
    "sieve.cli_report",
    "sieve.cli_setup",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sieve",
        description="Sieve — web3 / web / binary audit engine. Run `sieve status` for the next step.",
    )
    p.add_argument("--version", action="version", version=f"sieve {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="<command>")
    for name in MODULES:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name == name:  # module not written yet during development
                continue
            raise
        mod.register(sub)
    return p


def main(argv: List[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        rc = args.func(args)
    except BrokenPipeError:
        return 0
    return int(rc or 0)


if __name__ == "__main__":
    sys.exit(main())
