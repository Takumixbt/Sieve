"""The scope fence. `case.md` frontmatter is the only authority on what may be touched.

Every oracle that sends traffic calls `require_host()` before it does. The fence fails closed:
no scope card, no traffic.
"""
from __future__ import annotations

import fnmatch
import ipaddress
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from . import yamlish
from .state import Engagement

CASE_TEMPLATE = """---
target: {name}
program: ""
packs: {packs}
scope:
  hosts: []              # exact hosts or wildcards, e.g. app.example.com, "*.api.example.com"
  urls: []               # optional URL prefixes, e.g. https://app.example.com/v1/
  contracts: []          # - {{chain: ethereum, address: "0x...", name: Vault}}
  paths: []              # local source paths in scope, relative to the target root
  binaries: []           # binary / package files in scope
out_of_scope:
  hosts: []
  vulns: []              # e.g. self-xss, missing-headers, dos
rules:
  active_testing: false  # true only when the program or contract allows it
  lab: false             # true for a local/lab target you own (allows localhost)
  max_rps: 2
  forbidden: [dos, social-engineering, physical, data-destruction]
  test_accounts: []      # env:NAME references only, never literal secrets
---

# Scope card — {name}

_Written at intake. Everything Sieve does is checked against this file. If it is wrong, fix it here first._

## Program rules (paste or summarise)

## Payout / severity table

## Known issues and prior audits

## Notes
"""


class Fence:
    def __init__(self, card: Dict[str, Any]):
        self.card = card or {}
        self.scope: Dict[str, Any] = self.card.get("scope") or {}
        self.oos: Dict[str, Any] = self.card.get("out_of_scope") or {}
        self.rules: Dict[str, Any] = self.card.get("rules") or {}

    @classmethod
    def load(cls, eng: Optional[Engagement] = None) -> Optional["Fence"]:
        eng = eng or Engagement.find()
        if eng is None or not os.path.isfile(eng.case_path()):
            return None
        with open(eng.case_path(), encoding="utf-8") as fh:
            meta, _ = yamlish.split_frontmatter(fh.read())
        return cls(meta)

    # ------------------------------------------------------------ predicates
    @property
    def active_testing(self) -> bool:
        return bool(self.rules.get("active_testing"))

    @property
    def lab(self) -> bool:
        return bool(self.rules.get("lab"))

    @staticmethod
    def _match_host(pattern: str, host: str) -> bool:
        pattern, host = pattern.lower().strip(), host.lower().strip().rstrip(".")
        if pattern.startswith("*."):
            return host.endswith(pattern[1:]) and host != pattern[2:]
        return fnmatch.fnmatch(host, pattern)

    def check_host(self, host: str) -> Tuple[bool, str]:
        host = (host or "").split("@")[-1].strip().lower()
        if host.startswith("["):  # IPv6 literal
            host = host[1:].split("]")[0]
        else:
            host = host.split(":")[0]
        if not host:
            return False, "empty host"
        for pat in self.oos.get("hosts") or []:
            if self._match_host(str(pat), host):
                return False, f"host {host} is explicitly out of scope ({pat})"
        loopback = host in ("localhost", "::1") or host.startswith("127.")
        if loopback and self.lab:
            return True, "lab target"
        for pat in self.scope.get("hosts") or []:
            if self._match_host(str(pat), host):
                return True, f"in scope ({pat})"
        try:
            ipaddress.ip_address(host)
            return False, f"IP {host} is not listed in scope.hosts"
        except ValueError:
            pass
        return False, f"host {host} is not listed in scope.hosts"

    def check_url(self, url: str) -> Tuple[bool, str]:
        u = urlparse(url if "://" in url else "//" + url)
        ok, why = self.check_host(u.netloc)
        if not ok:
            return ok, why
        prefixes = [str(p) for p in (self.scope.get("urls") or [])]
        if prefixes and not any(url.startswith(p) for p in prefixes):
            # host is in scope; URL prefixes narrow further only when the card lists any for this host
            same_host = [p for p in prefixes if urlparse(p).netloc.lower() == u.netloc.lower()]
            if same_host and not any(url.startswith(p) for p in same_host):
                return False, f"URL is outside the listed prefixes for {u.netloc}"
        return True, why

    def check_contract(self, chain: str, address: str) -> Tuple[bool, str]:
        want = address.lower()
        for c in self.scope.get("contracts") or []:
            if isinstance(c, dict) and str(c.get("address", "")).lower() == want:
                if not chain or str(c.get("chain", "")).lower() in ("", chain.lower()):
                    return True, f"in scope ({c.get('name', address)})"
        return False, f"contract {address} on {chain or '?'} is not listed in scope.contracts"

    def check_path(self, path: str, root: str) -> Tuple[bool, str]:
        rel = os.path.relpath(os.path.abspath(path), root)
        entries = [str(p) for p in (self.scope.get("paths") or [])] + \
                  [str(p) for p in (self.scope.get("binaries") or [])]
        if not entries:
            return True, "no path restriction on the scope card"
        for p in entries:
            p = p.rstrip("/")
            if rel == p or rel.startswith(p + os.sep):
                return True, f"in scope ({p})"
        return False, f"path {rel} is not under scope.paths / scope.binaries"


def require_host(url_or_host: str, eng: Optional[Engagement] = None, need_active: bool = True) -> None:
    """Exit non-zero unless the target is in scope (and active testing is permitted when needed)."""
    fence = Fence.load(eng)
    if fence is None:
        raise SystemExit("sieve fence: no scope card (.sieve/case.md) — refusing to send traffic")
    ok, why = fence.check_url(url_or_host)
    if not ok:
        raise SystemExit(f"sieve fence: BLOCKED — {why}")
    if need_active and not fence.active_testing and not fence.lab:
        raise SystemExit("sieve fence: BLOCKED — rules.active_testing is false on the scope card")
