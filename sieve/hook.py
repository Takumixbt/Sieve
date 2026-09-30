"""Stop hook: the harness-enforced half of the anti-laziness design.

Claude Code runs this when the agent is about to stop. If the engagement is not finished it
returns {"decision": "block", "reason": ...} and the agent is told exactly what to do next.

Termination is guaranteed by *our* caps (max_blocks, max_minutes, consecutive no-progress
blocks), not by `stop_hook_active`. A block only repeats while real work is being done: a stalled
agent is released and the report records the halt honestly. Never an infinite loop, never a
silent early stop.

Only the Stop event is enforced. SubagentStop is deliberately not: the orchestrator's roll call
(`sieve rollcall`) machine-checks every subagent's coverage instead, which does not depend on
harness fields we cannot verify.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, Dict, Optional

from . import frontier, util
from .config import load_config
from .flow import next_action
from .state import Engagement

PERMISSION_PATTERNS = [
    r"would you like( me)? to",
    r"shall i\b",
    r"should i (proceed|continue|go ahead|start|begin|run|move)",
    r"do you want me to",
    r"want me to\b",
    r"let me know (if|whether|how|which|when)",
    r"please (confirm|advise|let me know|tell me)",
    r"which (option|approach|one|direction) (would|do|should) you",
    r"ready (for me )?to proceed",
    r"if you('d| would) like",
    r"awaiting (your|further)",
    r"waiting for (your|further)",
    r"i('ll| will) wait (for|until)",
    r"once you (confirm|approve|give)",
]
_PERM_RE = re.compile("|".join(PERMISSION_PATTERNS), re.I)

ACTIVE_PHASES = {"xray", "prime", "hunt", "converge", "gate", "prove", "report", "learn"}


def permission_ending(message: str) -> bool:
    tail = (message or "").strip()[-700:]
    return bool(_PERM_RE.search(tail))


def _reason(eng: Engagement, st: Dict[str, Any], perm: bool) -> str:
    head, detail = next_action(eng)
    fs = frontier.stats(eng)
    rows = frontier.next_rows(eng, n=5)
    lines = [
        f"SIEVE persistence guard — the engagement is not finished "
        f"(phase {st['phase']}, pass {st.get('pass_current', 0)}/{st.get('passes_planned', 1)}, "
        f"{fs['open']} frontier row(s) open, {fs['closed_pct']}% closed).",
        f"NEXT: {head} — {detail}",
    ]
    if rows:
        lines.append("Open rows, highest priority first:")
        for r in rows:
            lines.append(f"  {r['id']} [{r['kind']}] {r['component']} (lens {r['lens']}, prio {r['prio']})")
    lines.append(
        "Do not ask permission and do not wait for instructions: decide, record the assumption in "
        ".sieve/assumptions.md, and continue. If a row resists, climb the ladder (`sieve ladder`), "
        "then close it with `sieve frontier dead` (>=3 attempts on >=3 different rungs). "
        "The only honest early stops are `sieve halt --reason scope|credentials|irreversible --note ...`."
    )
    if perm:
        lines.append("Your last message ended by asking for permission. Nothing here needs it. Proceed.")
    return "\n".join(lines)


def decide(eng: Engagement, payload: Dict[str, Any], now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Pure decision function (testable). Returns a block dict or None to allow the stop."""
    now = now or time.time()
    cfg = load_config(eng.root)
    p_max_blocks = int(cfg.get("persistence.max_blocks", 60))
    p_release = int(cfg.get("persistence.no_progress_release", 4))
    p_minutes = float(cfg.get("persistence.max_minutes", 240))
    p_wait = float(cfg.get("persistence.wait_release_minutes", 45))
    p_perm = bool(cfg.get("persistence.block_permission_endings", True))

    def heartbeat(st: Dict[str, Any]) -> None:
        c = st.setdefault("counters", {})
        c["hook_calls"] = int(c.get("hook_calls", 0)) + 1
        c["last_hook_epoch"] = now

    st0 = eng.load()
    if st0.get("done") or st0.get("halt_reason") or st0.get("phase") not in ACTIVE_PHASES:
        eng.update(heartbeat)
        return None

    # Legitimately idle: background agents are running.
    waiting = st0.get("waiting")
    if waiting and (now - float(waiting.get("since", now))) / 60.0 < p_wait:
        eng.update(heartbeat)
        return None

    message = str(payload.get("last_assistant_message") or "")
    perm = p_perm and permission_ending(message)
    phash = frontier.progress_hash(eng)
    result: Dict[str, Any] = {}

    def fn(st: Dict[str, Any]) -> None:
        heartbeat(st)
        c = st["counters"]
        if eng.elapsed_minutes(st) > p_minutes:
            st["halt_reason"] = f"time budget exhausted ({p_minutes:.0f} min)"
            return
        if int(c.get("blocks_total", 0)) >= p_max_blocks:
            st["halt_reason"] = f"block budget exhausted ({p_max_blocks})"
            return
        if phash == c.get("last_progress"):
            c["blocks_no_progress"] = int(c.get("blocks_no_progress", 0)) + 1
        else:
            c["blocks_no_progress"] = 0
            c["last_progress"] = phash
        if int(c["blocks_no_progress"]) >= p_release:
            st["halt_reason"] = (f"stalled: {p_release} consecutive stop attempts with no measurable "
                                 "progress (frontier, attempts, raw files, findings, proofs all unchanged)")
            return
        c["blocks_total"] = int(c.get("blocks_total", 0)) + 1
        result["block"] = True

    eng.update(fn)
    st = eng.load()
    if st.get("halt_reason"):
        _log(eng, f"RELEASE {st['halt_reason']}")
        return None
    if result.get("block"):
        reason = _reason(eng, st, perm)
        _log(eng, f"BLOCK phase={st['phase']} open={frontier.stats(eng)['open']} perm={perm}")
        return {"decision": "block", "reason": reason}
    return None


def _log(eng: Engagement, line: str) -> None:
    try:
        os.makedirs(eng.path("logs"), exist_ok=True)
        with open(eng.path("logs", "hook.log"), "a", encoding="utf-8") as fh:
            fh.write(f"{util.now_iso()} {line}\n")
    except OSError:
        pass


def main_stop(stdin_text: Optional[str] = None) -> int:
    """Entry point for `sieve hook stop`. Never raises: a broken guard must not break the session."""
    try:
        raw = stdin_text if stdin_text is not None else sys.stdin.read()
        payload = json.loads(raw) if raw and raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        eng = Engagement.find(payload.get("cwd") or os.getcwd())
        if eng is None:
            return 0
        out = decide(eng, payload)
        if out:
            sys.stdout.write(json.dumps(out))
        return 0
    except Exception as exc:  # noqa: BLE001 — fail open, loudly on stderr only
        print(f"sieve hook: ignored internal error: {exc}", file=sys.stderr)
        return 0


# ---------------------------------------------------------------- installation

HOOK_COMMAND_GUARDED = "sh -c 'command -v sieve >/dev/null 2>&1 && exec sieve hook stop || exit 0'"


def launcher(root: str) -> str:
    """The command that runs Sieve from a hook. Windows has no POSIX shell to run bin/sieve, so it goes
    through the Python launcher instead."""
    if os.name == "nt":
        return f'python "{os.path.join(root, "bin", "sieve.py")}"'
    return os.path.join(root, "bin", "sieve")


def install(scope: str, sieve_bin: str, dry_run: bool = False) -> str:
    """Register the Stop hook in Claude Code settings. Idempotent; preserves everything else."""
    if scope == "user":
        path = os.path.expanduser("~/.claude/settings.json")
    elif scope == "project":
        path = os.path.join(os.getcwd(), ".claude", "settings.json")
    else:
        raise SystemExit("sieve hooks: scope must be 'user' or 'project'")
    settings = util.read_json(path, {}) or {}
    cmd = f"{sieve_bin} hook stop"
    hooks = settings.setdefault("hooks", {})
    stop = hooks.setdefault("Stop", [])
    for entry in stop:
        for h in entry.get("hooks", []):
            if h.get("command") == cmd:
                return f"already installed in {path}"
    stop.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})
    if dry_run:
        return f"would write {path}:\n{json.dumps(settings, indent=2)}"
    util.write_json(path, settings)
    return f"installed Stop hook in {path}"


def installed(sieve_bin: Optional[str] = None) -> Dict[str, bool]:
    found = {"user": False, "project": False}
    for scope, path in (("user", os.path.expanduser("~/.claude/settings.json")),
                        ("project", os.path.join(os.getcwd(), ".claude", "settings.json"))):
        s = util.read_json(path, {}) or {}
        for entry in (s.get("hooks", {}) or {}).get("Stop", []):
            for h in entry.get("hooks", []):
                if "hook stop" in str(h.get("command", "")):
                    found[scope] = True
    return found
