"""Sieve — multi-domain audit skill: web3, web, binary.

Pure standard library. Python >= 3.9.
"""
from __future__ import annotations

import os

__all__ = ["__version__", "repo_root"]


def repo_root() -> str:
    """Directory that holds SKILL.md (the skill home)."""
    env = os.environ.get("SIEVE_HOME")
    if env and os.path.isfile(os.path.join(env, "SKILL.md")):
        return os.path.abspath(env)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _read_version() -> str:
    try:
        with open(os.path.join(repo_root(), "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "0.0.0"


__version__ = _read_version()
