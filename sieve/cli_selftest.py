"""`sieve selftest`: the skill's own test suite, run from the installed skill.

Covers the verdict rules, the scope fence, proof execution with negative controls, tamper detection, the campaign
topology for every profile, the knowledge-base tiers, the vault export and two full simulated engagements. Nothing
here touches a real target, the network, your knowledge base or your vault.
"""
from __future__ import annotations

import argparse
import os
import sys
import unittest
from typing import Any

from . import repo_root


def cmd_selftest(args: argparse.Namespace) -> int:
    root = repo_root()
    tests = os.path.join(root, "tests")
    if not os.path.isdir(tests):
        print("sieve selftest: this install has no tests/ directory")
        return 1
    if args.fast:
        os.environ["SIEVE_FAST_TESTS"] = "1"
    if args.no_browser:
        os.environ["SIEVE_NO_BROWSER_TEST"] = "1"
    if root not in sys.path:
        sys.path.insert(0, root)
    suite = unittest.defaultTestLoader.discover(tests, top_level_dir=root, pattern=args.pattern)
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


def register(sub: Any) -> None:
    p = sub.add_parser("selftest", help="run the skill's own test suite (no network, no real target)")
    p.add_argument("--fast", action="store_true", help="skip the 71-node full-profile engagement (about a minute)")
    p.add_argument("--no-browser", action="store_true", help="skip the live CloakBrowser test")
    p.add_argument("--pattern", default="test*.py")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_selftest)
