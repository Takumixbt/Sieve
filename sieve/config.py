"""Layered configuration: repo defaults <- user file <- engagement file, plus path expansion."""
from __future__ import annotations

import copy
import os
from typing import Any, Dict, Optional

from . import repo_root, yamlish


def user_home() -> str:
    return os.path.abspath(os.path.expanduser(os.environ.get("SIEVE_USER_HOME", "~/.sieve")))


def expand(p: str) -> str:
    return os.path.abspath(os.path.expanduser(os.path.expandvars(p)))


def deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class Config:
    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw

    def get(self, path: str, default: Any = None) -> Any:
        cur: Any = self.raw
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur

    def path(self, dotted: str, default: Optional[str] = None) -> str:
        v = self.get(dotted, default)
        if v is None:
            raise KeyError(dotted)
        uh = user_home()
        s = str(v)
        if s.startswith("~/.sieve"):
            s = uh + s[len("~/.sieve"):]
        return expand(s)

    def source(self, name: str) -> Dict[str, Any]:
        return dict(self.get(f"kb.sources.{name}", {}) or {})


def _load(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    data = yamlish.load_file(path)
    return data if isinstance(data, dict) else {}


def load_config(engagement_root: Optional[str] = None) -> Config:
    raw = _load(os.path.join(repo_root(), "sieve.yaml"))
    raw = deep_merge(raw, _load(os.path.join(user_home(), "sieve.yaml")))
    if engagement_root:
        raw = deep_merge(raw, _load(os.path.join(engagement_root, ".sieve", "sieve.yaml")))
    return Config(raw)
