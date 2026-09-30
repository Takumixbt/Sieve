"""Test harness: a golden fixture target and simulated agents.

The engine never calls a model, so a full campaign can be driven without one: this module plays every agent node
by writing the artifact its contract asks for, then lets the real engine validate, merge, judge, prove (with a real
executed proof and a real negative control), verify and report. What is being tested is the machinery, not the
model: contract validation, scheduling, merge rules, the gates, proof execution, tiering, the vault export.
"""
from __future__ import annotations

import contextlib
import difflib
import io
import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

VAULT_SOL = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract Vault {
    mapping(address => uint256) public bal;
    function deposit() external payable { bal[msg.sender] += msg.value; }
    function withdraw(uint256 a) external {
        (bool ok, ) = msg.sender.call{value: a}("");
        require(ok);
        bal[msg.sender] -= a;
    }
}
"""

POC = """import re, sys
src = open("src/Vault.sol").read()
body = re.search(r"function withdraw\\([^)]*\\)[^{]*\\{(.*?)\\n    \\}", src, re.S).group(1)
if body.index(".call{value") < body.index("bal[msg.sender] -="):
    print("REENTRANCY-CONFIRMED: the external call precedes the balance update")
"""

LONG = "x-ray narrative text describing the target, its trust model and the surfaces worth the first hour. " * 4


def fixed_source() -> str:
    lines = VAULT_SOL.split("\n")
    i = next(n for n, l in enumerate(lines) if "msg.sender.call" in l)
    j = next(n for n, l in enumerate(lines) if "bal[msg.sender] -= a" in l)
    lines[i], lines[i + 1], lines[j] = lines[j], lines[i], lines[i + 1]
    return "\n".join(lines)


def make_target(tmp: str, git: bool = True) -> str:
    root = os.path.join(tmp, "target")
    os.makedirs(os.path.join(root, "src"))
    with open(os.path.join(root, "src", "Vault.sol"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(VAULT_SOL)
    if git:
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "init", "-q"], cwd=root, env=env, check=False, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=False, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=root, env=env, check=False, capture_output=True)
    return root


def isolated_env(tmp: str) -> Dict[str, str]:
    """Environment that keeps a test run off the network, off the real KB and off the user's vault."""
    env = {"SIEVE_HOME": ROOT, "SIEVE_USER_HOME": os.path.join(tmp, "home"), "SIEVE_VAULT": os.path.join(tmp, "vault"),
           "SIEVE_OFFLINE": "1", "SIEVE_NO_STATIC": "1", "PYTHONIOENCODING": "utf-8",
           "SIEVE_BROWSER_HOME": os.path.join(tmp, "browser")}   # never the real test identity or its Burp proxy
    os.environ.update(env)
    return env


def tmpdir(case) -> str:
    """A temp dir removed after the test. Windows keeps SQLite files locked until the connection is collected,
    so removal ignores errors rather than failing an otherwise passing test."""
    import gc
    import shutil
    d = tempfile.mkdtemp(prefix="sieve-test-")
    case.addCleanup(lambda: (gc.collect(), shutil.rmtree(d, ignore_errors=True)))
    return d


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(text)


def cli(*argv: str, cwd: Optional[str] = None) -> Tuple[int, str]:
    """Run `sieve ...` in-process and capture what it printed."""
    from sieve.main import main
    buf = io.StringIO()
    old = os.getcwd()
    rc = 0
    try:
        if cwd:
            os.chdir(cwd)
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                rc = main(list(argv))
            except SystemExit as exc:
                rc = 1
                if exc.code not in (None, 0):
                    print(str(exc.code))
    finally:
        os.chdir(old)
    return int(rc or 0), buf.getvalue()


# ---------------------------------------------------------------------------- simulated agents

def _finding_block() -> str:
    return (
        "FINDING | pack: web3 | class: reentrancy | vector: W3-REENT-01 | component: Vault.withdraw\n"
        "group_key: Vault|withdraw|reentrancy\n"
        "path: attacker contract -> Vault.withdraw -> external call before balance update -> repeated withdrawal\n"
        "proof: src/Vault.sol:7 `msg.sender.call{value: a}(\"\")` runs before src/Vault.sol:9 `bal[msg.sender] -= a`, "
        "so a receive hook re-enters withdraw while bal is still the old value and drains the vault\n"
        "description: An attacker contract re-enters withdraw from its receive hook and takes more ether than it deposited.\n"
        "fix: Update bal[msg.sender] before the external call.\n"
        "severity: high\n"
        "confidence: 92\n")


class Agents:
    """Plays every agentic node of a campaign. `finder` is the roster agent that raises the reentrancy finding."""

    def __init__(self, eng: Any, finder: Optional[str] = None):
        self.eng = eng
        self.finder = finder
        self.log: List[str] = []

    def _w(self, rel: str, text: str) -> None:
        p = self.eng.path(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def write(self, node: Dict[str, Any]) -> str:
        from sieve import campaign_schema as schema
        spec = node["spec"]
        out = node["outputs"][0] if node["outputs"] else {}
        fn = getattr(self, "do_" + spec.replace("-", "_"), None)
        if fn is None:
            ex = schema.CONTRACTS.get(str(out.get("schema")), {}).get("example")
            if ex is None:
                raise AssertionError(f"no simulated agent for node {node['id']} ({spec})")
            data = json.loads(json.dumps(ex))
            if spec == "lens":
                data["lens"] = node["vars"]["lens"]
            self._w(out["path"], json.dumps(data, indent=2))
            return "example"
        fn(node)
        return spec

    # ---- x-ray narratives
    def do_narrative_web3(self, node: Dict[str, Any]) -> None:
        self._w("xray/x-ray.md", "# X-ray\n\n" + LONG)
        self._w("xray/entry-points.md", "# Entry points\n\n- Vault.deposit: payable, anyone\n- Vault.withdraw: anyone with a balance. " * 3)
        self._w("xray/invariants.md", "# Invariants\n\n- INV-1: the vault balance never falls below the sum of all bal entries.\n"
                                       "- INV-2: a caller can only withdraw what it deposited.\n")
        self._w("xray/architecture.json", json.dumps({"nodes": [{"id": "vault", "label": "Vault", "kind": "contract"}], "edges": [], "groups": []}))

    # ---- the hunt
    def do_hunt(self, node: Dict[str, Any]) -> None:
        agent, loop = node["vars"]["agent_id"], int(node["vars"]["loop"])
        slug = node["vars"]["slug"]
        if self.finder is None:
            self.finder = agent          # the first roster agent to report is the one that finds the bug
        blocks = "HYPOTHESIS | pack: web3 | class: reentrancy | component: Vault.withdraw\nquestion: does withdraw update state before the call?\nnext_step: read withdraw\n\n"
        if agent == self.finder and loop == 1:
            blocks += _finding_block() + "\n"
        self._w(node["outputs"][0]["path"], f"# {agent} pass {loop}\n\n{blocks}\n## COVERAGE\n\nSIEVE-AGENT-DONE {slug} pass {loop}\n")

    def do_roaming(self, node: Dict[str, Any]) -> None:
        loop = int(self.eng.load().get("pass_current") or 1)
        self._w(node["outputs"][0]["path"], f"# roaming\n\nHYPOTHESIS | pack: web3 | class: business-logic | component: Vault\n"
                                            f"question: can deposits be double counted?\nnext_step: trace deposit the way a stranger would, from a fresh contract\n\n"
                                            f"## COVERAGE\n\nThe roaming pass looked at accounting, ordering and trust with no lens.\n\nSIEVE-AGENT-DONE roaming pass {loop}\n")

    def do_drain(self, node: Dict[str, Any]) -> None:
        from sieve import frontier
        from sieve.config import load_config
        cfg = load_config(self.eng.root)
        for r in frontier.load(self.eng):
            if r["status"] in frontier.OPEN:
                frontier.dead(self.eng, r["id"], [("layer", "read the layer"), ("sibling", "compared the sibling"),
                                                   ("precedent", "searched the KB")], cfg)
        self._w("campaign/artifacts/drain.md", "# Drain\n\nEvery remaining row was closed dead with three rungs each.\n")

    def do_triage(self, node: Dict[str, Any]) -> None:
        from sieve.flow import _unjudged
        panelist = node["vars"]["panelist"]
        verdicts = []
        for fid in _unjudged(self.eng):
            verdicts.append({"finding_id": fid, "verdict": "cleared", "complexity": "straightforward",
                             "gates": {k: "pass" for k in ("g0", "g1", "g2", "g3", "g4", "g5")},
                             "refutation": "searched for a reentrancy guard or checks-effects-interactions ordering: none in withdraw",
                             "reasoning": "withdraw sends ether to the caller before it decrements the caller's balance, so a receive hook re-enters",
                             "confidence": 92, "severity": "high"})
        self._w(node["outputs"][0]["path"], json.dumps({"panelist": f"triage-{panelist}", "verdicts": verdicts}, indent=2))

    def do_prove(self, node: Dict[str, Any]) -> None:
        from sieve import validate as V
        proofs = []
        for fid, j in V.load_judged(self.eng).items():
            if j.get("gates") == "cleared" and j.get("verdict") == "cleared":
                d = self.eng.path("proofs", fid)
                os.makedirs(d, exist_ok=True)
                poc = os.path.join(d, "poc.py")
                with open(poc, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(POC)
                orig = VAULT_SOL.split("\n")
                fixed = fixed_source().split("\n")
                diff = "\n".join(difflib.unified_diff(orig, fixed, "a/src/Vault.sol", "b/src/Vault.sol", lineterm="")) + "\n"
                patch = os.path.join(d, "fix.diff")
                with open(patch, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(diff)
                proofs.append({"finding_id": fid, "oracle": "custom-script", "cmd": f'"{sys.executable}" "{poc}"'.replace(chr(92), "/"),
                               "expect": "REENTRANCY-CONFIRMED", "control": {"kind": "patch", "patch_file": patch},
                               "rationale": "the script reads Vault.withdraw and reports the call-before-effect ordering; the patch reorders it"})
        self._w(node["outputs"][0]["path"], json.dumps({"proofs": proofs}, indent=2))


def drive(root: str, max_steps: int = 60, log: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run the campaign to completion with simulated agents. Returns a summary; raises with the engine's own output
    if it stalls, so a failing test shows what the engine said."""
    from sieve import campaign as C
    from sieve.state import Engagement
    eng = Engagement(root)
    agents = Agents(eng)
    trail: List[str] = log if log is not None else []
    for step in range(max_steps):
        rc, out = cli("campaign", "run", cwd=root)
        trail.append(f"[run {step}] rc={rc}\n{out.strip()[-1500:]}")
        topo, nodes, st = C.load(eng, allow_drift=True)
        sts = C.statuses(eng, nodes, st)
        if all(v in C.DONE_LIKE for v in sts.values()):
            return {"steps": step, "nodes": len(nodes), "status": sts}
        if any(v == "failed" for v in sts.values()):
            raise AssertionError("a node failed:\n" + "\n".join(trail[-3:]))
        ready = [n for n in nodes if sts[n["id"]] == "ready" and n["kind"] == "agentic"]
        if not ready:
            raise AssertionError("campaign stalled with no ready agent node:\n" + "\n".join(trail[-3:]))
        rc, out = cli("campaign", "next", cwd=root)
        trail.append(f"[next {step}]\n{out.strip()[-600:]}")
        for n in ready:
            agents.write(n)
            args = ["campaign", "submit", n["id"]]
            if n.get("builder") in ("bundle", "roaming"):
                args += ["--accept", "simulated agent, below the completeness quota"]
            rc, out = cli(*args, cwd=root)
            trail.append(f"[submit {n['id']}] rc={rc} {out.strip()[-400:]}")
    raise AssertionError("campaign did not finish within %d steps:\n%s" % (max_steps, "\n".join(trail[-4:])))


def new_engagement(tmp: str, profile: str = "lite") -> str:
    """scan + campaign init on a fresh fixture; returns the target root."""
    isolated_env(tmp)
    root = make_target(tmp)
    rc, out = cli("scan", root, "--offline", "--quiet")
    assert rc == 0, out
    rc, out = cli("campaign", "init", "--profile", profile, cwd=root)
    assert rc == 0, out
    return root
