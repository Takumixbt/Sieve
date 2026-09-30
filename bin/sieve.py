#!/usr/bin/env python3
"""Cross-platform Sieve launcher: `python bin/sieve.py <command>`. Used by sieve.cmd and the Stop hook on Windows."""
import os
import sys

HOME = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
os.environ.setdefault("SIEVE_HOME", HOME)
sys.path.insert(0, HOME)

from sieve.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
