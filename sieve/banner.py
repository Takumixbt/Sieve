"""The SIEVE banner. Printed first, every run (SKILL.md Turn 0), and by `sieve banner`."""
from __future__ import annotations

import os
import sys

from . import __version__, repo_root

TAGLINE = "what survives the sieve is real"
DOMAINS = "web3  ·  web  ·  binary"


def art() -> str:
    path = os.path.join(repo_root(), "assets", "banner-art.txt")
    with open(path, encoding="utf-8") as fh:
        return fh.read().rstrip("\n")


def banner_text(bold: bool = False) -> str:
    a = art()
    width = max(len(line) for line in a.split("\n"))
    sub = f"  {DOMAINS}"
    ver = f"v{__version__}"
    sub_line = sub + " " * max(2, width - len(sub) - len(ver)) + ver
    tag_line = f"  {TAGLINE}"
    if bold:
        b, r, c = "\033[1m", "\033[0m", "\033[36m"
        return f"\n{b}{c}{a}{r}\n{b}{sub_line}{r}\n{tag_line}\n"
    return f"\n{a}\n{sub_line}\n{tag_line}\n"


def print_banner(force_color: bool = False) -> None:
    color = force_color or (sys.stdout.isatty() and "NO_COLOR" not in os.environ)
    sys.stdout.write(banner_text(bold=color))
    sys.stdout.flush()
