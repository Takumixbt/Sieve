"""Engagement state: the `.sieve/` directory that survives context resets.

Everything an audit needs to resume lives on disk here, never in a model's memory.
"""
from __future__ import annotations

import os
import secrets
import time
from typing import Any, Callable, Dict, List, Optional

from . import util

PHASES = ["init", "xray", "prime", "hunt", "converge", "gate", "prove", "report", "learn", "done"]
SUBDIRS = ["xray", "raw", "bundles", "findings", "proofs", "deadends", "logs", "report"]


class Engagement:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.dir = os.path.join(self.root, ".sieve")

    # ------------------------------------------------------------ discovery
    @classmethod
    def find(cls, start: Optional[str] = None) -> Optional["Engagement"]:
        cur = os.path.abspath(start or os.getcwd())
        while True:
            if os.path.isfile(os.path.join(cur, ".sieve", "state.json")):
                return cls(cur)
            parent = os.path.dirname(cur)
            if parent == cur:
                return None
            cur = parent

    @classmethod
    def require(cls, start: Optional[str] = None) -> "Engagement":
        e = cls.find(start)
        if e is None:
            raise SystemExit("sieve: no engagement here (run `sieve init` first)")
        return e

    @classmethod
    def create(cls, root: str, packs: List[str], name: Optional[str] = None,
               passes: int = 3, mode: str = "deep") -> "Engagement":
        e = cls(root)
        if os.path.isfile(e.state_path):
            raise SystemExit(f"sieve: engagement already exists at {e.dir}")
        os.makedirs(e.dir, exist_ok=True)
        for d in SUBDIRS:
            os.makedirs(os.path.join(e.dir, d), exist_ok=True)
        eid = f"SV-{util.today().replace('-', '')}-{secrets.token_hex(2)}"
        st: Dict[str, Any] = {
            "id": eid,
            "name": name or os.path.basename(e.root) or "target",
            "target": e.root,
            "packs": packs,
            "created": util.now_iso(),
            "updated": util.now_iso(),
            "started_epoch": time.time(),
            "phase": "init",
            "mode": mode,
            "passes_planned": passes,
            "pass_current": 0,
            "passes_done": [],
            "waiting": None,
            "counters": {"blocks_total": 0, "blocks_no_progress": 0, "last_progress": "",
                         "hook_calls": 0, "last_hook_epoch": 0},
            "halt_reason": None,
            "done": False,
        }
        util.write_json(e.state_path, st)
        util.atomic_write(os.path.join(e.dir, ".gitignore"), "*\n")
        return e

    # ------------------------------------------------------------ paths
    @property
    def state_path(self) -> str:
        return os.path.join(self.dir, "state.json")

    @property
    def lock_path(self) -> str:
        return os.path.join(self.dir, "state.lock")

    def path(self, *parts: str) -> str:
        return os.path.join(self.dir, *parts)

    # ------------------------------------------------------------ state I/O
    def load(self) -> Dict[str, Any]:
        st = util.read_json(self.state_path)
        if not isinstance(st, dict):
            raise SystemExit(f"sieve: corrupt state file {self.state_path}")
        return st

    def update(self, fn: Callable[[Dict[str, Any]], Any]) -> Any:
        """Locked read-modify-write. `fn` mutates the dict in place; its return value is returned."""
        with util.file_lock(self.lock_path):
            st = self.load()
            ret = fn(st)
            st["updated"] = util.now_iso()
            util.write_json(self.state_path, st)
            return ret

    def set_phase(self, phase: str) -> None:
        if phase not in PHASES:
            raise SystemExit(f"sieve: unknown phase {phase!r}; valid: {', '.join(PHASES)}")

        def fn(st: Dict[str, Any]) -> None:
            st["phase"] = phase
            if phase == "done":
                st["done"] = True
        self.update(fn)

    # ------------------------------------------------------------ convenience
    def case_path(self) -> str:
        return self.path("case.md")

    def frontier_path(self) -> str:
        return self.path("frontier.tsv")

    def elapsed_minutes(self, st: Optional[Dict[str, Any]] = None) -> float:
        st = st or self.load()
        return (time.time() - float(st.get("started_epoch", time.time()))) / 60.0
