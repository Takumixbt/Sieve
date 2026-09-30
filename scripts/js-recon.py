#!/usr/bin/env python3
"""js-recon.py — extract the recon surface from JavaScript, deterministically.

The one web-recon step an LLM does badly by hand: reading minified JS bundles for
endpoints, API paths, secrets, and source-map references. This does it as a receipt
(regex over the bytes, same output every run). OPTIONAL adapter (agents/recon-agent.md
-> secret_scan / JS analysis); needs only python3, no third-party packages.

Usage:  scripts/js-recon.py <file-or-dir> [file-or-dir ...]
Every hit is a LEAD (shared-rules.md): confirm each endpoint is live and each
"secret" is real+in-scope before reporting. A leaked signer/deployer key is a
CROSSOVER lead, not "info disclosure, low".
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ENDPOINT = re.compile(r"""["'`](/[A-Za-z0-9._~!$&'()*+,;=:@%/-]{2,}|https?://[^"'`\s]{6,})["'`]""")
SECRET   = re.compile(r"""(?i)(secret|token|api[_-]?key|password|private[_-]?key|mnemonic|aws_access|bearer|authorization)["'`:=\s]{1,4}([A-Za-z0-9/+_.\-]{16,})""")
SMAP     = re.compile(r"""sourceMappingURL=([^\s*]+)""")
JWT      = re.compile(r"""eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}""")


def files(args):
    for a in args:
        if os.path.isdir(a):
            for root, _, fs in os.walk(a):
                if any(s in root for s in ("node_modules", ".git")):
                    continue
                for f in fs:
                    if f.endswith((".js", ".mjs", ".ts", ".map", ".html")):
                        yield os.path.join(root, f)
        elif os.path.isfile(a):
            yield a


def parse(argv: list[str]):
    p = argparse.ArgumentParser(
        prog="js-recon.py",
        description="Extract endpoints, source maps, secrets, JWTs from JS/HTML.",
    )
    p.add_argument("paths", nargs="+", help="File or directory to scan")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    o = parse(argv)
    eps, secs, smaps, jwts = set(), set(), set(), set()
    scanned = 0
    for path in files(o.paths):
        scanned += 1
        try:
            txt = open(path, "r", errors="ignore").read()
        except Exception:
            continue
        for m in ENDPOINT.finditer(txt):
            v = m.group(1)
            if not re.fullmatch(r"/[a-z]", v or "") and "/" in (v or ""):
                eps.add(v)
        for m in SECRET.finditer(txt):
            v = m.group(2)
            if not re.search(r"(?i)example|sample|dummy|xxxx|your[_-]?|placeholder", v):
                secs.add(f"{path}: {m.group(1)}={v[:40]}")
        for m in SMAP.finditer(txt):
            smaps.add(f"{path}: {m.group(1)}")
        for m in JWT.finditer(txt):
            jwts.add(f"{path}: {m.group(0)[:48]}...")

    def block(title, items, cap=200):
        print(f"\n## {title} ({len(items)})")
        for x in sorted(items)[:cap]:
            print(f"  {x}")

    print(f"# js-recon over {scanned} file(s) — LEADS, verify each")
    block("Endpoints / API paths", eps)
    block("Source maps (recover original source + routes)", smaps)
    block("Possible secrets", secs)
    block("JWTs found", jwts)
    print("\nNext: fire each endpoint into the web-gates.md grid; check each source"
          "\nmap for original routes; verify each secret is live + in-scope (a signing"
          "\nkey is a crossover lead, not info-disclosure-low).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
