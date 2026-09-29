"""Versioned artifact contracts for campaign nodes — the engine's "no free-form handoffs" rule.

Every agentic node in a campaign (`campaigns/*.yml`) declares an output and the contract it must
satisfy, as `name@version`. The engine validates the file an agent wrote *before* the node counts as
done and before anything downstream reads it. An artifact that fails is rejected with a list of
JSON-path errors the agent can fix — a plausible-looking blob is never accepted on faith.

The schema language is a small, dependency-free subset of JSON Schema (type, required, properties,
items, enum, pattern, minLength, minItems, minimum, maximum) plus two extensions used by the
contracts below: `atLeastOne` (an object needs a non-empty array under one of several keys) and
`anyItemWith` (some array item must carry given field values, e.g. at least one moonshot strategy).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

LENSES = ["accounting", "authority", "ordering-time", "equivalence", "bounds-monotonicity", "trust-boundary",
          "promise-vs-enforcement", "adversary-profit"]
SEV = ["critical", "high", "medium", "low", "informational"]
GATE = {"type": "string", "enum": ["pass", "fail", "na"]}


def _s(min_len: int = 1, **kw: Any) -> Dict[str, Any]:
    return dict({"type": "string", "minLength": min_len}, **kw)


def _arr(items: Dict[str, Any], min_items: int = 0) -> Dict[str, Any]:
    return {"type": "array", "items": items, "minItems": min_items}


CONTRACTS: Dict[str, Dict[str, Any]] = {
    "threat-model@1": {
        "doc": "Who can do what to which asset, and where the trust boundaries are. Written before any code is hunted.",
        "schema": {"type": "object", "required": ["assets", "actors", "trust_boundaries", "attack_goals", "assumptions"],
                   "properties": {
                       "assets": _arr({"type": "object", "required": ["name", "why_it_matters"],
                                       "properties": {"name": _s(2), "why_it_matters": _s(15)}}, 1),
                       "actors": _arr({"type": "object", "required": ["name", "privilege", "goal"],
                                       "properties": {"name": _s(2), "goal": _s(10),
                                                      "privilege": {"type": "string", "enum": [
                                                          "anonymous", "user", "privileged", "admin", "external-contract",
                                                          "validator", "oracle", "insider"]}}}, 1),
                       "trust_boundaries": _arr({"type": "object", "required": ["name", "between", "controls"],
                                                 "properties": {"name": _s(2), "between": _s(5), "controls": _s(10)}}, 1),
                       "attack_goals": _arr({"type": "object", "required": ["id", "goal", "actor", "asset"],
                                             "properties": {"id": _s(pattern=r"^G-\d+$"), "goal": _s(20),
                                                            "actor": _s(2), "asset": _s(2),
                                                            "preconditions": _arr(_s(3))}}, 3),
                       "assumptions": _arr(_s(10))}},
        "example": {"assets": [{"name": "Vault ETH", "why_it_matters": "all depositors' funds sit in one contract"}],
                    "actors": [{"name": "anyone", "privilege": "anonymous", "goal": "extract funds"}],
                    "trust_boundaries": [{"name": "Vault.sweep", "between": "any caller and the vault balance",
                                          "controls": "should require owner"}],
                    "attack_goals": [{"id": "G-1", "goal": "move the whole vault balance to an attacker-chosen address",
                                      "actor": "anyone", "asset": "Vault ETH", "preconditions": ["none"]}],
                    "assumptions": ["the owner key is honest and not compromised"]},
    },
    "goal-plan@1": {
        "doc": "The threat model turned into ranked, checkable goals — what the hunt must answer, and what it will not spend time on.",
        "schema": {"type": "object", "required": ["goals", "excluded"], "properties": {
            "goals": _arr({"type": "object", "required": ["id", "statement", "priority", "components", "first_checks"],
                           "properties": {"id": _s(pattern=r"^P-\d+$"), "statement": _s(25),
                                          "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                                          "components": _arr(_s(2), 1), "first_checks": _arr(_s(10), 1),
                                          "from_goal": _s(1)}}, 5),
            "excluded": _arr({"type": "object", "required": ["what", "why"], "properties": {"what": _s(3), "why": _s(10)}})}},
        "example": {"goals": [{"id": "P-1", "statement": "prove or refute that any caller can move funds out of the vault",
                               "priority": 5, "components": ["src/Vault.sol:sweep"], "first_checks": ["read every external function's guards"],
                               "from_goal": "G-1"}], "excluded": [{"what": "gas optimisation", "why": "out of scope per case.md"}]},
    },
    "properties@1": {
        "doc": "One lens's invariants, derived cold (no sight of the other lenses). Say 'nothing here' explicitly if the lens is empty.",
        "schema": {"type": "object", "required": ["lens", "invariants", "nothing_here"],
                   "atLeastOne": [["invariants", "nothing_here"]],
                   "properties": {
                       "lens": {"type": "string", "enum": LENSES},
                       "invariants": _arr({"type": "object", "required": ["id", "statement", "derived_from", "violators", "test"],
                                           "properties": {"id": _s(pattern=r"^L-[a-z\-]+-\d+$|^INV-[A-Za-z\-]*\d+$"),
                                                          "statement": _s(20), "derived_from": _s(8),
                                                          "violators": _arr(_s(3)), "test": _s(15),
                                                          "on_chain": {"type": "boolean"}}}),
                       "nothing_here": _arr(_s(10))}},
        "example": {"lens": "accounting", "invariants": [{"id": "L-accounting-1", "statement": "totalSupply equals the sum of all balances",
                                                          "derived_from": "src/Vault.sol:10-11", "violators": ["sweep"],
                                                          "test": "call sweep then compare balance to totalSupply"}],
                    "nothing_here": []},
    },
    "properties-merged@1": {
        "doc": "The eight lenses fanned in: duplicates merged, weak statements dropped, ranked by how badly a break would hurt.",
        "schema": {"type": "object", "required": ["invariants", "dropped"], "properties": {
            "invariants": _arr({"type": "object", "required": ["id", "statement", "derived_from", "sources", "violators", "test", "rank"],
                                "properties": {"id": _s(pattern=r"^INV-\d+$"), "statement": _s(20), "derived_from": _s(8),
                                               "sources": _arr({"type": "string", "enum": LENSES}, 1),
                                               "violators": _arr(_s(3)), "test": _s(15),
                                               "rank": {"type": "integer", "minimum": 1},
                                               "on_chain": {"type": "boolean"}}}, 1),
            "dropped": _arr({"type": "object", "required": ["statement", "reason"], "properties": {"statement": _s(5), "reason": _s(10)}})}},
        "example": {"invariants": [{"id": "INV-1", "statement": "balance of the vault is never below totalSupply", "derived_from": "src/Vault.sol:7",
                                    "sources": ["accounting", "adversary-profit"], "violators": ["sweep"], "test": "fork test: sweep then withdraw",
                                    "rank": 1, "on_chain": False}], "dropped": []},
    },
    "strategy@1": {
        "doc": "The dynamic strategy generator: hypotheses no roster lens owns, chosen after seeing the threat model, invariants and what earlier loops found.",
        "schema": {"type": "object", "required": ["strategies"], "anyItemWith": {"strategies": {"moonshot": True}},
                   "properties": {"strategies": _arr({"type": "object",
                                                      "required": ["id", "hypothesis", "technique", "targets", "why_unseen", "cheapest_test", "moonshot"],
                                                      "properties": {"id": _s(pattern=r"^S-\d+$"), "hypothesis": _s(25),
                                                                     "technique": _s(3), "targets": _arr(_s(2), 1),
                                                                     "why_unseen": _s(15), "cheapest_test": _s(15),
                                                                     "moonshot": {"type": "boolean"}}}, 5)}},
        "example": {"strategies": [{"id": "S-1", "hypothesis": "the owner variable is never initialised so the admin path is unreachable and sweep is the only exit",
                                    "technique": "inversion-of-intent", "targets": ["src/Vault.sol"], "why_unseen": "reviewers read sweep as admin-only",
                                    "cheapest_test": "grep every write to owner", "moonshot": True}]},
    },
    "triage@1": {
        "doc": "One panelist's independent verdict on every candidate (Gates 0-5 of judging.md). Panelists never see each other's output.",
        "schema": {"type": "object", "required": ["panelist", "verdicts"], "properties": {
            "panelist": _s(2),
            "verdicts": _arr({"type": "object",
                              "required": ["finding_id", "verdict", "complexity", "gates", "refutation", "reasoning", "confidence"],
                              "properties": {"finding_id": _s(pattern=r"^F-\d+$"),
                                             "verdict": {"type": "string", "enum": ["cleared", "demoted", "rejected"]},
                                             "complexity": {"type": "string", "enum": ["straightforward", "complex"]},
                                             "gates": {"type": "object", "required": ["g0", "g1", "g2", "g3", "g4", "g5"],
                                                       "properties": {k: GATE for k in ("g0", "g1", "g2", "g3", "g4", "g5")}},
                                             "refutation": _s(15), "reasoning": _s(30),
                                             "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                                             "severity": {"type": "string", "enum": SEV}}})}},
        "example": {"panelist": "triage-1", "verdicts": [{"finding_id": "F-001", "verdict": "cleared", "complexity": "straightforward",
                                                          "gates": {"g0": "pass", "g1": "pass", "g2": "pass", "g3": "pass", "g4": "pass", "g5": "pass"},
                                                          "refutation": "searched every modifier on sweep: none — no guard blocks the call",
                                                          "reasoning": "sweep is external, unguarded, and transfers the full balance to a caller-chosen address",
                                                          "confidence": 92, "severity": "critical"}]},
    },
    "proofs@1": {
        "doc": "How each cleared finding is to be proven — the PoC files are written by the prover; the engine runs them (repeated, with a negative control).",
        "schema": {"type": "object", "required": ["proofs"], "properties": {"proofs": _arr({
            "type": "object", "required": ["finding_id", "oracle", "rationale"],
            "properties": {"finding_id": _s(pattern=r"^F-\d+$"), "oracle": _s(3), "cmd": _s(3), "expect": _s(3),
                           "trace_only": {"type": "boolean"},
                           "control": {"type": "object", "required": ["kind"], "properties": {
                               "kind": {"type": "string", "enum": ["patch", "command", "waived"]},
                               "patch_file": _s(1), "cmd": _s(1), "waiver": _s(15)}},
                           "capture": _arr(_s(3)), "repeat": {"type": "integer", "minimum": 2, "maximum": 10},
                           "cwd": _s(1), "target": _arr(_s(3)), "env": _arr(_s(1)), "rationale": _s(20)}})}},
        "example": {"proofs": [{"finding_id": "F-001", "oracle": "fork-test", "cmd": "forge test --match-test testSweep -vv",
                                "expect": "\\[PASS\\] testSweep", "control": {"kind": "patch", "patch_file": ".sieve/proofs/F-001/fix.diff"},
                                "rationale": "a permissionless sweep drains the vault; the patch adds an owner check"}]},
    },
    "audit@1": {
        "doc": "Differential-reference independence audit: is the oracle a proof leans on independent of the code it judges?",
        "schema": {"type": "object", "required": ["audits"], "properties": {"audits": _arr({
            "type": "object", "required": ["finding_id", "oracle_independent", "shares_code_with_target", "reason"],
            "properties": {"finding_id": _s(pattern=r"^F-\d+$"), "oracle_independent": {"type": "boolean"},
                           "shares_code_with_target": {"type": "boolean"}, "reason": _s(20)}})}},
        "example": {"audits": [{"finding_id": "F-001", "oracle_independent": True, "shares_code_with_target": False,
                                "reason": "the expected value is computed from the deposit amounts, not by calling the vault's own accounting"}]},
    },
}

def _grow(example: Dict[str, Any], key: str, n: int, idkey: str = "id") -> None:
    """Examples must satisfy their own contract (checked by `sieve lint`); repeat the first item to meet minItems."""
    first = example[key][0]
    example[key] = [dict(first, **{idkey: re.sub(r"\d+$", str(i), first[idkey])}) for i in range(1, n + 1)]


_grow(CONTRACTS["threat-model@1"]["example"], "attack_goals", 3)
_grow(CONTRACTS["goal-plan@1"]["example"], "goals", 5)
_grow(CONTRACTS["strategy@1"]["example"], "strategies", 5)

_CORE_XRAY = {"x-ray.md": {"min": 300}, "entry-points.md": {"min": 120},
              "invariants.md": {"min": 80, "match": [r"INV-\d+"]}, "architecture.json": {"min": 40, "match": [r'"nodes"']}}

MARKDOWN: Dict[str, Dict[str, Any]] = {
    "xray-narrative@1": {"doc": "The x-ray narrative files: verdict paragraph, classified entry points, numbered invariants, architecture map JSON.",
                         "files": dict(_CORE_XRAY)},
    "authz-model@1": {"doc": "The web authorization model: identities x endpoints x objects with the empty cells named, plus the core x-ray files.",
                      "files": dict(_CORE_XRAY, **{"authz-matrix.md": {"min": 200, "match": [r"\|"]}})},
    "attack-surface@1": {"doc": "The binary/mobile attack surface: every input boundary with its trust level, plus the core x-ray files.",
                         "files": dict(_CORE_XRAY, **{"attack-surface.md": {"min": 250}})},
}


# ---------------------------------------------------------------------------- validation

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int, "number": (int, float)}


def _check(v: Any, sch: Dict[str, Any], path: str, errs: List[str]) -> None:
    t = sch.get("type")
    if t:
        pt = _TYPES[t]
        ok = isinstance(v, pt) and not (t in ("integer", "number") and isinstance(v, bool))
        if not ok:
            errs.append(f"{path}: expected {t}, got {type(v).__name__}")
            return
    if isinstance(v, str):
        if len(v.strip()) < int(sch.get("minLength", 0)):
            errs.append(f"{path}: string has {len(v.strip())} chars, needs at least {sch['minLength']}")
        if "enum" in sch and v not in sch["enum"]:
            errs.append(f"{path}: {v!r} is not one of {sch['enum']}")
        if "pattern" in sch and not re.search(sch["pattern"], v):
            errs.append(f"{path}: {v!r} does not match {sch['pattern']}")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if "minimum" in sch and v < sch["minimum"]:
            errs.append(f"{path}: {v} is below the minimum {sch['minimum']}")
        if "maximum" in sch and v > sch["maximum"]:
            errs.append(f"{path}: {v} is above the maximum {sch['maximum']}")
    if isinstance(v, list):
        if len(v) < int(sch.get("minItems", 0)):
            errs.append(f"{path}: {len(v)} item(s), needs at least {sch['minItems']}")
        if "items" in sch:
            for i, it in enumerate(v):
                _check(it, sch["items"], f"{path}[{i}]", errs)
    if isinstance(v, dict):
        for k in sch.get("required", []):
            if k not in v:
                errs.append(f"{path}: missing required field `{k}`")
        for k, sub in (sch.get("properties") or {}).items():
            if k in v:
                _check(v[k], sub, f"{path}.{k}", errs)
        for group in sch.get("atLeastOne", []):
            if not any(isinstance(v.get(k), list) and v.get(k) for k in group):
                errs.append(f"{path}: needs a non-empty array under at least one of {group}")
        for key, want in (sch.get("anyItemWith") or {}).items():
            items = v.get(key) or []
            if isinstance(items, list) and not any(isinstance(i, dict) and all(i.get(a) == b for a, b in want.items()) for i in items):
                errs.append(f"{path}.{key}: at least one item must have {want}")


def validate_json(name: str, data: Any) -> List[str]:
    if name not in CONTRACTS:
        return [f"unknown contract {name!r} (known: {', '.join(sorted(CONTRACTS))})"]
    errs: List[str] = []
    _check(data, CONTRACTS[name]["schema"], "$", errs)
    return errs


def validate_file(name: str, path: str) -> Tuple[List[str], Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        return [f"cannot read {path}: {exc}"], None
    except ValueError as exc:
        return [f"{path} is not valid JSON: {exc}"], None
    return validate_json(name, data), data


def validate_markdown(name: str, base_dir: str) -> List[str]:
    import os
    spec = MARKDOWN.get(name)
    if spec is None:
        return [f"unknown markdown contract {name!r}"]
    errs: List[str] = []
    for fn, rule in spec["files"].items():
        p = os.path.join(base_dir, fn)
        if not os.path.isfile(p):
            errs.append(f"{fn}: file is missing")
            continue
        text = open(p, encoding="utf-8", errors="replace").read()
        if len(text.strip()) < rule.get("min", 1):
            errs.append(f"{fn}: {len(text.strip())} chars, needs at least {rule['min']}")
        for rx in rule.get("match", []):
            if not re.search(rx, text):
                errs.append(f"{fn}: must contain a match for {rx}")
    return errs


def describe(name: str) -> str:
    """Human/agent-readable statement of a contract, embedded in every node prompt that outputs it."""
    if name in MARKDOWN:
        spec = MARKDOWN[name]
        lines = [f"**Contract `{name}`** — {spec['doc']}", "", "Files (under `.sieve/xray/`):"]
        for fn, rule in spec["files"].items():
            extra = f", must match `{'`, `'.join(rule['match'])}`" if rule.get("match") else ""
            lines.append(f"- `{fn}` — at least {rule.get('min', 1)} characters{extra}")
        return "\n".join(lines)
    c = CONTRACTS[name]
    lines = [f"**Contract `{name}`** — {c['doc']}", "", "Write **valid JSON** (no comments, no trailing commas, no prose around it) with these fields:", ""]

    def walk(sch: Dict[str, Any], indent: int, label: str) -> None:
        pad = "  " * indent
        t = sch.get("type", "any")
        bits = [t]
        if "enum" in sch:
            bits.append("one of " + " | ".join(map(str, sch["enum"])))
        if "pattern" in sch:
            bits.append(f"matches `{sch['pattern']}`")
        if sch.get("minLength", 0) > 1:
            bits.append(f"≥{sch['minLength']} chars")
        if sch.get("minItems", 0):
            bits.append(f"≥{sch['minItems']} item(s)")
        if "minimum" in sch:
            bits.append(f"{sch['minimum']}..{sch.get('maximum', '∞')}")
        lines.append(f"{pad}- `{label}`: {', '.join(bits)}")
        if t == "array" and "items" in sch:
            walk(sch["items"], indent + 1, label + "[]")
        if t == "object":
            req = set(sch.get("required", []))
            for k, sub in (sch.get("properties") or {}).items():
                walk(sub, indent + 1, k + ("" if k in req else "?"))
        for grp in sch.get("atLeastOne", []) or []:
            lines.append(f"{pad}  (at least one of {grp} must be non-empty)")
        for k, want in (sch.get("anyItemWith") or {}).items():
            lines.append(f"{pad}  (at least one `{k}` item must have {want})")

    walk(c["schema"], 0, "$")
    shown = {k: (v[:1] if isinstance(v, list) and len(v) > 1 else v) for k, v in c["example"].items()}
    lines += ["", "Example (arrays shortened to one item — repeat items as needed to meet the minimums above):",
              "```json", json.dumps(shown, indent=2), "```"]
    return "\n".join(lines)


def known() -> List[str]:
    return sorted(list(CONTRACTS) + list(MARKDOWN))
