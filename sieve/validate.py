"""Deterministic validation — a finding is CONFIRMED by a machine check, never by narration.

The failure this exists to prevent: an agent writes `status: confirmed` (or files a "proof receipt"
that says "trust me") and the report prints it as verified. Here the confirmation is *computed*:

    cites     every file:line the finding cites is re-read by code (`cites.py`); the receipt pins the
              SHA-256 of each cited file, so a later change to that code marks the finding STALE
    executed  the proof is a command the tool itself runs — repeated, with a NEGATIVE CONTROL that
              must NOT show the exploit signature (a proof that also "passes" on the patched or
              unprivileged path is vacuous and is failed) — and stable across repeats
    judged    a verifier who is not the discoverer cleared Gates 0-5 (`judging.md`), by quorum when
              the finding is complex, with confidence at or above the threshold
    sealed    every receipt and verdict carries an HMAC and joins an append-only hash chain, so an
              edited, deleted or hand-written receipt is detected instead of believed

`assess()` combines them into one tier per finding — confirmed | trace-verified | unvalidated | stale |
tampered | rejected | lead — and the report prints exactly that, ignoring whatever the finding file's
own `status:` line claims. The seal is tamper-*evident*, not tamper-proof: it stops accidents and
narrated shortcuts, and any forgery needs a deliberate read of `.seal-key` that shows in the transcript.
"""
from __future__ import annotations

import glob
import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from . import cites as citelib
from . import kb_store, util, yamlish
from .config import load_config
from .fence import Fence
from .state import Engagement

CONTROLLED_SEVERITIES = ("critical", "high", "medium")
NETWORK_ORACLES = {"oast-hit", "two-identity-diff", "http-replay", "timing-diff", "race-replay",
                   "ssrf-callback", "browser-replay", "api-replay"}
URL_RX = re.compile(r"https?://[^\s'\"<>|;&)\\]+", re.I)
DESTRUCTIVE = [
    (re.compile(r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+(/|~|\$HOME|\*|\.\s|\.$)"), "recursive delete"),
    (re.compile(r"\bmkfs(\.\w+)?\b|\bdd\s+[^|;]*\bof=/dev/"), "disk overwrite"),
    (re.compile(r":\(\)\s*\{"), "fork bomb"),
    (re.compile(r"\b(shutdown|reboot|halt|poweroff)\b"), "host power control"),
    (re.compile(r"(-X|--request)\s+(DELETE)\b", re.I), "HTTP DELETE against a target"),
    (re.compile(r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b", re.I), "destructive SQL"),
]
_SAFE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "USER", "SHELL",
             # Windows: without these a child process cannot find its runtime, temp dir or profile
             "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
             "PATHEXT", "COMSPEC", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "HOMEDRIVE", "HOMEPATH")
_SAFE_ENV_PREFIX = ("XDG_", "FOUNDRY_", "CARGO_", "RUSTUP_", "NVM_", "PYENV_", "GOPATH", "GOROOT", "JAVA_HOME",
                    "ANDROID_", "SIEVE_")
_REDACT_KINDS = {"private-key-block", "private-key-header", "aws-access-key", "gcp-api-key", "github-token",
                 "slack-token", "stripe-key", "jwt", "bearer-token", "wallet-secret", "generic-secret"}


# ---------------------------------------------------------------------------- sealing

def _key(eng: Engagement) -> bytes:
    p = eng.path(".seal-key")
    if not os.path.isfile(p):
        util.atomic_write(p, secrets.token_hex(32))
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
    return util.read_text(p).strip().encode()


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def seal(eng: Engagement, body: Dict[str, Any]) -> str:
    clean = {k: v for k, v in body.items() if k != "seal"}
    return hmac.new(_key(eng), _canon(clean), hashlib.sha256).hexdigest()


def seal_ok(eng: Engagement, body: Dict[str, Any]) -> bool:
    return bool(body.get("seal")) and hmac.compare_digest(str(body["seal"]), seal(eng, body))


def _ledger(eng: Engagement) -> str:
    return eng.path("proofs", "ledger.jsonl")


def _ledger_lines(eng: Engagement) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if os.path.isfile(_ledger(eng)):
        for ln in util.read_text(_ledger(eng)).split("\n"):
            if ln.strip():
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    out.append({"_corrupt": ln[:80]})
    return out


def _line_hash(entry: Dict[str, Any]) -> str:
    return hashlib.sha256(_canon({k: v for k, v in entry.items() if k != "mac"})).hexdigest()


def _append_ledger(eng: Engagement, fname: str, data: bytes) -> None:
    with util.file_lock(eng.path("proofs", ".ledger.lock")):
        lines = _ledger_lines(eng)
        prev = _line_hash(lines[-1]) if lines else "genesis"
        entry = {"seq": len(lines) + 1, "file": fname, "sha256": hashlib.sha256(data).hexdigest(), "prev": prev,
                 "time": util.now_iso()}
        entry["mac"] = hmac.new(_key(eng), _canon(entry), hashlib.sha256).hexdigest()
        with open(_ledger(eng), "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")


def write_receipt(eng: Engagement, fid: str, name: str, body: Dict[str, Any]) -> str:
    body = dict(body, finding=fid, time=util.now_iso(), ts_ns=time.time_ns())
    body["seal"] = seal(eng, body)
    fname = f"{fid}--{util.slug(name)}.json"
    path = eng.path("proofs", fname)
    data = (json.dumps(body, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    os.makedirs(eng.path("proofs"), exist_ok=True)
    if os.path.exists(path):  # never overwrite a receipt: keep history, name the new one
        n = 2
        while os.path.exists(eng.path("proofs", f"{fid}--{util.slug(name)}-{n}.json")):
            n += 1
        fname = f"{fid}--{util.slug(name)}-{n}.json"
        path = eng.path("proofs", fname)
    util.atomic_write(path, data.decode("utf-8"))
    _append_ledger(eng, fname, data)
    return path


def ledger_problems(eng: Engagement) -> List[str]:
    """Chain, MAC and file-hash check of the whole proofs ledger."""
    probs: List[str] = []
    prev = "genesis"
    listed = set()
    for i, e in enumerate(_ledger_lines(eng), 1):
        if "_corrupt" in e:
            probs.append(f"ledger line {i} is corrupt")
            continue
        mac = hmac.new(_key(eng), _canon({k: v for k, v in e.items() if k != "mac"}), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, str(e.get("mac", ""))):
            probs.append(f"ledger entry {e.get('seq')} ({e.get('file')}): MAC mismatch — the ledger was edited")
        if e.get("prev") != prev or e.get("seq") != i:
            probs.append(f"ledger entry {e.get('seq')}: chain broken (an entry was removed or reordered)")
        prev = _line_hash(e)
        listed.add(e.get("file"))
        p = eng.path("proofs", str(e.get("file")))
        if not os.path.isfile(p):
            probs.append(f"receipt {e.get('file')} is listed in the ledger but missing")
        elif util.sha256_file(p) != e.get("sha256"):
            probs.append(f"receipt {e.get('file')} was modified after it was written")
    for p in glob.glob(eng.path("proofs", "F-*--*.json")):
        if os.path.basename(p) not in listed:
            probs.append(f"receipt {os.path.basename(p)} is not in the ledger (hand-written, not produced by `sieve`)")
    return probs


# ---------------------------------------------------------------------------- findings I/O

def finding_meta(eng: Engagement, fid: str) -> Tuple[Dict[str, Any], str]:
    p = eng.path("findings", f"{fid}.md")
    if not os.path.isfile(p):
        raise SystemExit(f"sieve: no such finding {fid} (see .sieve/findings/ledger.md)")
    meta, body = yamlish.split_frontmatter(util.read_text(p))
    return meta, body


def write_finding_meta(eng: Engagement, fid: str, updates: Dict[str, Any]) -> None:
    meta, body = finding_meta(eng, fid)
    meta.update({k: v for k, v in updates.items() if v is not None})
    util.atomic_write(eng.path("findings", f"{fid}.md"), yamlish.join_frontmatter(meta, body))


def all_finding_ids(eng: Engagement) -> List[str]:
    return [os.path.basename(f)[:-3] for f in sorted(glob.glob(eng.path("findings", "F-*.md")))]


def _order(r: Dict[str, Any]) -> Tuple[int, str]:
    """Chronological order of receipts: nanosecond stamp (second-resolution `time` ties within one command)."""
    return int(r.get("ts_ns") or 0), str(r.get("time", ""))


def receipts(eng: Engagement, fid: str) -> List[Dict[str, Any]]:
    out = []
    for p in sorted(glob.glob(eng.path("proofs", f"{fid}--*.json"))):
        body = util.read_json(p, None)
        if isinstance(body, dict):
            ok = seal_ok(eng, body)          # before annotating: the seal covers exactly what was written
            body["_file"] = os.path.basename(p)
            body["_seal_ok"] = ok
            out.append(body)
    return out


# ---------------------------------------------------------------------------- judgments (sealed)

def load_judged(eng: Engagement) -> Dict[str, Any]:
    return util.read_json(eng.path("findings", "judged.json"), {}) or {}


def save_judgment(eng: Engagement, fid: str, entry: Dict[str, Any]) -> None:
    j = load_judged(eng)
    entry = dict(entry, finding=fid)
    entry["seal"] = seal(eng, entry)
    j[fid] = entry
    util.write_json(eng.path("findings", "judged.json"), j)


# ---------------------------------------------------------------------------- redaction

def redact(text: str) -> str:
    for kind, rx in kb_store._SECRET_PATTERNS:
        if kind in _REDACT_KINDS:
            text = rx.sub(f"[REDACTED:{kind}]", text)
    return text


def has_secret(text: str) -> List[str]:
    return sorted(k for k, rx in kb_store._SECRET_PATTERNS if k in _REDACT_KINDS and rx.search(text))


# ---------------------------------------------------------------------------- 1. citations

def verify_cites(eng: Engagement, fid: str) -> Dict[str, Any]:
    meta, body = finding_meta(eng, fid)
    pack = str(meta.get("pack") or "")
    text = "\n".join([str(meta.get("component", "")), body])
    rep = citelib.verify_text(eng.root, text, hard_missing=(pack == "web3"))
    good = [r for r in rep["results"] if r["ok"]]
    need = pack == "web3" and str(meta.get("kind")) == "FINDING"
    ok = rep["ok"] and (bool(good) or not need)
    rec = {"kind": "cites", "ok": ok, "claim_hash": meta.get("claim_hash"), "checked": rep["count"],
           "cites": [{"cite": r["cite"], "file": r.get("file"), "sha256": r.get("sha256"), "ok": r["ok"],
                      "why": r["why"]} for r in rep["results"]],
           "failures": [r["cite"] + " — " + r["why"] for r in rep["failures"]],
           "no_citations": (rep["count"] == 0)}
    write_receipt(eng, fid, "cites", rec)
    return rec


# ---------------------------------------------------------------------------- 2. executed proof

def _env_for(names: List[str]) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV or k.startswith(_SAFE_ENV_PREFIX)}
    for n in names:
        if n not in os.environ:
            raise SystemExit(f"sieve prove: --env {n} is not set in this shell")
        env[n] = os.environ[n]
    env["SIEVE_PROOF"] = "1"
    return env


def check_cmd(eng: Engagement, cmd: str, oracle: str, targets: List[str], infra: List[str]) -> Dict[str, Any]:
    """The seatbelt: refuse destructive verbs, literal secrets, and traffic to anything outside the fence."""
    for rx, what in DESTRUCTIVE:
        if rx.search(cmd):
            raise SystemExit(f"sieve prove: refused — {what}. Prove the same bug non-destructively "
                             f"(on an object you created, on a fork, or in a lab copy).")
    leaked = has_secret(cmd)
    if leaked:
        raise SystemExit("sieve prove: refused — the command contains what looks like a literal credential "
                         f"({', '.join(leaked)}). Put it in an environment variable and pass `--env NAME`.")
    fence = Fence.load(eng)
    touched: List[str] = []
    urls = URL_RX.findall(cmd)
    hosts = list(targets) + [u for u in urls if (urlparse(u).hostname or "") not in infra]
    if oracle in NETWORK_ORACLES and not hosts:
        raise SystemExit(f"sieve prove: oracle {oracle!r} sends traffic — declare every host it talks to with "
                         f"--target HOST_OR_URL so the scope fence can check it")
    if hosts:
        if fence is None:
            raise SystemExit("sieve fence: no scope card (.sieve/case.md) — refusing to send traffic")
        for h in hosts:
            ok, why = fence.check_url(h)
            if not ok:
                raise SystemExit(f"sieve fence: BLOCKED — {why} (from `{h}`)")
            touched.append(h)
        if not fence.active_testing and not fence.lab:
            raise SystemExit("sieve fence: BLOCKED — rules.active_testing is false on the scope card, so no traffic "
                             "may be sent. File captured evidence with `sieve prove add` instead.")
    return {"targets": touched, "infra": infra}


_COSMETIC = re.compile(r"^\s*(echo|printf|true|:|cat\s*<<)\b", re.I)


def _refuse_cosmetic(cmd: str) -> None:
    """A proof command that only prints text proves nothing: it must exercise the target."""
    segs = [x for x in re.split(r"&&|\|\||;|\n", cmd) if x.strip()]
    if segs and all(_COSMETIC.match(x) for x in segs):
        raise SystemExit("sieve prove: refused — that command only prints text. A proof must exercise the target "
                         "(a test run, a script that calls it, a request replay). Put the PoC in a file and run it.")


def poc_files(cmd: str, workdir: str, root: str) -> Dict[str, str]:
    """SHA-256 of every file the command names that exists under the target — so editing the PoC after it
    was proven marks the receipt stale instead of leaving a proof for code that no longer exists."""
    out: Dict[str, str] = {}
    try:
        toks = shlex.split(cmd)
    except ValueError:
        toks = cmd.split()
    for t in toks:
        for base in (workdir, root):
            cand = os.path.abspath(os.path.join(base, t))
            if os.path.isfile(cand) and (cand == root or cand.startswith(root + os.sep)):
                out[os.path.relpath(cand, root)] = util.sha256_file(cand)
                break
    return out


def _patched_copy(eng: Engagement, patch: str) -> Tuple[str, List[str]]:
    """A throwaway copy of the target with the fix applied — the mutation the control runs against."""
    if not os.path.isfile(patch):
        raise SystemExit(f"sieve prove run: --control-patch {patch} is not a file")
    total = 0
    for base, dirs, files in os.walk(eng.root):
        dirs[:] = [d for d in dirs if d not in (".git", ".sieve", "__pycache__")]
        for f in files:
            try:
                total += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
        if total > 400 * 1024 * 1024:
            raise SystemExit("sieve prove run: the target is over 400 MB — use --control-cmd instead of --control-patch")
    tmp = tempfile.mkdtemp(prefix="sieve-control-")
    dst = os.path.join(tmp, "target")
    shutil.copytree(eng.root, dst, symlinks=True, ignore=shutil.ignore_patterns(".git", ".sieve", "__pycache__"))
    rc, out, err = util.run(["git", "apply", "--whitespace=nowarn", os.path.abspath(patch)], cwd=dst, timeout=60)
    if rc != 0:
        rc2, out2, err2 = util.run(["patch", "-p1", "-i", os.path.abspath(patch)], cwd=dst, timeout=60)
        if rc2 != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            raise SystemExit("sieve prove run: the control patch does not apply to the target:\n  "
                             + (err or out or err2 or out2).strip()[:400])
    changed = []
    for base, _d, files in os.walk(dst):
        for f in files:
            pth = os.path.join(base, f)
            rel = os.path.relpath(pth, dst)
            orig = os.path.join(eng.root, rel)
            if not os.path.isfile(orig) or util.sha256_file(orig) != util.sha256_file(pth):
                changed.append(rel)
    if not changed:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit("sieve prove run: the control patch changed nothing")
    return dst, sorted(changed)[:20]


def _cited_hashes(eng: Engagement, fid: str) -> Dict[str, str]:
    """Hashes of the source files the finding cites, at the moment the proof ran."""
    meta, body = finding_meta(eng, fid)
    rep = citelib.verify_text(eng.root, "\n".join([str(meta.get("component", "")), body]), hard_missing=False)
    return {r["file"]: r["sha256"] for r in rep["results"] if r.get("ok") and r.get("file") and r.get("sha256")}


def shell_argv(cmd: str) -> List[str]:
    """The shell a proof command runs under. PoC commands are written for a POSIX shell, so on Windows that means
    the sh/bash that ships with Git for Windows (or WSL's), never cmd.exe."""
    if os.name != "nt":
        return ["/bin/sh", "-c", cmd]
    for name in ("sh", "bash"):
        hit = shutil.which(name)
        if hit:
            return [hit, "-c", cmd]
    for cand in (r"C:\Program Files\Git\bin\sh.exe", r"C:\Program Files\Git\usr\bin\sh.exe",
                 r"C:\Program Files (x86)\Git\bin\sh.exe"):
        if os.path.isfile(cand):
            return [cand, "-c", cmd]
    raise SystemExit("sieve prove: no POSIX shell found. Proof commands run under sh: install Git for Windows "
                     "(Git Bash) or WSL and make sure `sh` is on PATH.")


def _run_once(cmd: str, cwd: str, env: Dict[str, str], timeout: int) -> Dict[str, Any]:
    t0 = time.time()
    try:
        p = subprocess.run(shell_argv(cmd), capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           env=env, errors="replace")
        rc, out = p.returncode, (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        rc, timed_out = 124, True
        out = ((exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")) + \
              "\n[timeout]"
    return {"rc": rc, "out": out[:1_000_000], "sec": round(time.time() - t0, 2), "timeout": timed_out}


def _judge_run(res: Dict[str, Any], expect: "re.Pattern[str]", captures: Dict[str, "re.Pattern[str]"],
               expect_rc: Optional[str]) -> Dict[str, Any]:
    m = expect.search(res["out"])
    rc_ok = True
    if expect_rc == "nonzero":
        rc_ok = res["rc"] != 0
    elif expect_rc not in (None, "any"):
        rc_ok = res["rc"] == int(expect_rc)
    group = m.groups() if m else ()
    caps = {}
    for name, rx in captures.items():
        cm = rx.search(res["out"])
        caps[name] = (cm.group(1) if cm and cm.groups() else (cm.group(0) if cm else None))
    return {"rc": res["rc"], "matched": bool(m), "rc_ok": rc_ok, "group": list(group), "captures": caps,
            "sec": res["sec"], "timeout": res["timeout"], "out_sha256": util.sha256_bytes(res["out"].encode()),
            "excerpt": redact(res["out"][-1500:])}


def target_rev(root: str) -> Dict[str, Any]:
    rc, out, _ = util.run(["git", "-C", root, "rev-parse", "HEAD"], timeout=10)
    if rc != 0:
        return {"git": False}
    _, dirty, _ = util.run(["git", "-C", root, "status", "--porcelain"], timeout=10)
    return {"git": True, "head": out.strip(), "dirty": bool(dirty.strip())}


def run_proof(eng: Engagement, fid: str, oracle: str, cmd: str, expect: str, control_cmd: Optional[str],
              control_waiver: Optional[str], repeat: int = 3, timeout: int = 300, cwd: Optional[str] = None,
              env_names: Optional[List[str]] = None, captures: Optional[List[str]] = None,
              expect_rc: Optional[str] = "0", targets: Optional[List[str]] = None,
              infra: Optional[List[str]] = None, control_patch: Optional[str] = None) -> Dict[str, Any]:
    finding_meta(eng, fid)  # must exist
    if repeat < 2:
        raise SystemExit("sieve prove run: --repeat must be >= 2 — a single run cannot show determinism")
    if len((expect or "").strip()) < 3:
        raise SystemExit("sieve prove run: --expect needs a real regex naming the exploit signature")
    _refuse_cosmetic(cmd)
    if not control_cmd and not control_patch and not control_waiver:
        raise SystemExit("sieve prove run: a negative control is required. Either\n"
                         "  --control-patch FIX.diff   re-run the SAME command against a copy of the target with the fix applied "
                         "(strongest: a PoC that ignores the target cannot pass it), or\n"
                         "  --control-cmd \"...\"       a command with the precondition removed (unprivileged caller / benign "
                         "input / other identity), or\n"
                         "  --control-waiver \"why\"     no control is possible — the proof is then uncontrolled and cannot "
                         "reach `confirmed`.\n"
                         "The signature must NOT appear in the control.")
    if control_waiver and len(control_waiver.strip()) < 15:
        raise SystemExit("sieve prove run: --control-waiver needs a real reason (>= 15 chars)")
    try:
        rx = re.compile(expect, re.M | re.S)
        caps = {}
        for c in captures or []:
            name, _, pat = c.partition("=")
            if not name or not pat:
                raise SystemExit("sieve prove run: --capture NAME=REGEX")
            caps[name.strip()] = re.compile(pat, re.M)
    except re.error as exc:
        raise SystemExit(f"sieve prove run: bad regex — {exc}")
    fence_info = check_cmd(eng, cmd, oracle, targets or [], infra or [])
    if control_cmd:
        check_cmd(eng, control_cmd, oracle, targets or [], infra or [])
    workdir = os.path.abspath(cwd) if cwd else eng.root
    if not os.path.isdir(workdir):
        raise SystemExit(f"sieve prove run: --cwd {workdir} is not a directory")
    env = _env_for(env_names or [])
    max_rps = float(((Fence.load(eng) or Fence({})).rules.get("max_rps") or 2))
    pause = (1.0 / max_rps) if fence_info["targets"] else 0.0

    runs, reasons = [], []
    for i in range(repeat):
        if i and pause:
            time.sleep(pause)
        runs.append(_judge_run(_run_once(cmd, workdir, env, timeout), rx, caps, expect_rc))
    if not all(r["matched"] and r["rc_ok"] for r in runs):
        bad = [i + 1 for i, r in enumerate(runs) if not (r["matched"] and r["rc_ok"])]
        reasons.append(f"the exploit signature was not observed in run(s) {bad} of {repeat}")
    if len({json.dumps(r["group"]) for r in runs}) > 1 or any(
            len({json.dumps(r["captures"].get(k)) for r in runs}) > 1 for k in caps):
        reasons.append("nondeterministic: captured values differ between runs")
    control: Dict[str, Any] = {"cmd": control_cmd, "waiver": control_waiver, "runs": [], "kinds": []}
    control_ok: Optional[bool] = None
    if reasons:
        control_cmd = control_patch = None      # the exploit itself did not reproduce; a control adds nothing
        control["skipped"] = "the exploit did not reproduce, so no control was run"
    if control_cmd:
        for i in range(max(2, repeat - 1)):
            if i and pause:
                time.sleep(pause)
            control["runs"].append(_judge_run(_run_once(control_cmd, workdir, env, timeout), rx, caps, "any"))
        control["kinds"].append("command")
        control_ok = not any(r["matched"] for r in control["runs"])
        if not control_ok:
            reasons.append("VACUOUS: the negative control ALSO shows the exploit signature — this proof does not "
                           "distinguish the bug from its absence")
    if control_patch:
        os.makedirs(eng.path("proofs", fid), exist_ok=True)
        pinned_patch = eng.path("proofs", fid, "control.patch")
        if os.path.abspath(control_patch) != os.path.abspath(pinned_patch):
            shutil.copyfile(control_patch, pinned_patch)
        control_patch = pinned_patch
        copy_dir, changed = _patched_copy(eng, control_patch)
        try:
            rel_cwd = os.path.relpath(workdir, eng.root)
            pdir = os.path.join(copy_dir, rel_cwd)
            pruns = []
            for i in range(max(2, repeat - 1)):
                pruns.append(_judge_run(_run_once(cmd, pdir, env, timeout), rx, caps, "any"))
        finally:
            shutil.rmtree(os.path.dirname(copy_dir), ignore_errors=True)
        control["patch"] = {"sha256": util.sha256_file(control_patch), "files_changed": changed, "runs": pruns}
        control["kinds"].append("patched-target")
        patch_ok = not any(r["matched"] for r in pruns)
        control_ok = patch_ok if control_ok is None else (control_ok and patch_ok)
        if not patch_ok:
            reasons.append("VACUOUS: the exploit signature still appears with the fix applied — the PoC does not depend "
                           "on the bug (or the patch does not fix it)")
    if reasons:
        verdict = "fail"
    elif control_ok is None:
        verdict = "pass-uncontrolled"
    else:
        verdict = "pass"
    rec = {"kind": "exec", "oracle": oracle, "verdict": verdict, "reasons": reasons, "cmd": cmd, "expect": expect,
           "expect_rc": expect_rc, "capture_specs": list(captures or []), "poc_files": poc_files(cmd, workdir, eng.root),
           "cited_files": _cited_hashes(eng, fid), "cwd": os.path.relpath(workdir, eng.root), "repeat": repeat, "runs": runs,
           "control": control, "control_ok": control_ok,
           "measured": {k: runs[0]["captures"].get(k) for k in caps},
           "env_names": sorted(env_names or []), "targets": fence_info["targets"], "infra_hosts": infra or [],
           "target_rev": target_rev(eng.root), "claim_hash": finding_meta(eng, fid)[0].get("claim_hash")}
    path = write_receipt(eng, fid, f"exec-{oracle}", rec)
    rec["_path"] = path
    return rec


def rerun_proof(eng: Engagement, fid: str, rec: Dict[str, Any]) -> Dict[str, Any]:
    """Re-execute a stored exec receipt under the same command and expectation."""
    ctl = rec.get("control") or {}
    patch = None
    if "patched-target" in (ctl.get("kinds") or []):
        patch = eng.path("proofs", fid, "control.patch")
        if not os.path.isfile(patch):
            raise SystemExit(f"cannot re-run {rec.get('oracle')}: the pinned control patch {patch} is missing")
    return run_proof(eng, fid, rec["oracle"], rec["cmd"], rec["expect"], ctl.get("cmd"),
                     ctl.get("waiver"), control_patch=patch, repeat=int(rec.get("repeat") or 3),
                     cwd=os.path.join(eng.root, rec.get("cwd") or "."), env_names=rec.get("env_names"),
                     captures=rec.get("capture_specs"), expect_rc=rec.get("expect_rc"),
                     targets=rec.get("targets"), infra=rec.get("infra_hosts"))


# ---------------------------------------------------------------------------- 2b. captured evidence

def add_evidence(eng: Engagement, fid: str, oracle: str, evidence: str, expect: str, control: str) -> Dict[str, Any]:
    """Deterministic *evaluation* of captured artifacts (a saved request/response, a Burp export, a crash
    log): the evidence file must match the signature, the control file must not. Files are copied into
    .sieve/proofs/<id>/ and hash-pinned. Weaker than an executed proof — it caps at trace-verified."""
    finding_meta(eng, fid)
    try:
        rx = re.compile(expect, re.M | re.S)
    except re.error as exc:
        raise SystemExit(f"sieve prove add: bad regex — {exc}")
    dest = eng.path("proofs", fid)
    os.makedirs(dest, exist_ok=True)
    pinned = {}
    texts = {}
    for label, src in (("evidence", evidence), ("control", control)):
        if not os.path.isfile(src):
            raise SystemExit(f"sieve prove add: --{label} {src} is not a file")
        text = util.read_text(src)
        if len(text.strip()) < 20:
            raise SystemExit(f"sieve prove add: --{label} {src} is empty or trivial")
        leaked = has_secret(text)
        if leaked:
            text = redact(text)
        name = f"{label}-{util.sha256_bytes(text.encode())[:10]}-{os.path.basename(src)}"
        util.atomic_write(os.path.join(dest, name), text)
        pinned[label] = {"file": os.path.relpath(os.path.join(dest, name), eng.root),
                         "sha256": util.sha256_bytes(text.encode()), "redacted": leaked}
        texts[label] = text
    reasons = []
    if not rx.search(texts["evidence"]):
        reasons.append("the evidence does not match the expected signature")
    if rx.search(texts["control"]):
        reasons.append("VACUOUS: the control artifact also matches the signature")
    rec = {"kind": "evidence", "oracle": oracle, "verdict": "fail" if reasons else "pass", "reasons": reasons,
           "expect": expect, "pinned": pinned, "claim_hash": finding_meta(eng, fid)[0].get("claim_hash")}
    rec["_path"] = write_receipt(eng, fid, f"evidence-{oracle}", rec)
    return rec


# ---------------------------------------------------------------------------- assessment

def _cites_state(eng: Engagement, meta: Dict[str, Any], rs: List[Dict[str, Any]]) -> Tuple[str, str]:
    mine = [r for r in rs if r.get("kind") == "cites"]
    if not mine:
        return "missing", "no citation receipt (`sieve verify`)"
    latest = sorted(mine, key=_order)[-1]
    if not latest["_seal_ok"]:
        return "tampered", f"{latest['_file']} seal invalid"
    if not latest.get("ok"):
        return "fail", "; ".join(latest.get("failures", [])[:2]) or "citation check failed"
    for c in latest.get("cites", []):
        if c.get("ok") and c.get("file") and c.get("sha256"):
            p = os.path.join(eng.root, c["file"])
            if not os.path.isfile(p) or util.sha256_file(p) != c["sha256"]:
                return "stale", f"{c['file']} changed since the citations were verified"
    if latest.get("claim_hash") and meta.get("claim_hash") and latest["claim_hash"] != meta["claim_hash"]:
        return "stale", "the finding's claim text changed since it was verified"
    return "pass", ""


def _exec_state(rs: List[Dict[str, Any]]) -> Tuple[str, str, Dict[str, Any]]:
    """State of the executable proof. Per oracle only the LATEST receipt counts, so a re-run that
    regresses (the exploit stopped working, the control started matching) overrides an earlier pass."""
    ex = [r for r in rs if r.get("kind") == "exec"]
    ev = [r for r in rs if r.get("kind") == "evidence"]
    for r in ex + ev:
        if not r["_seal_ok"]:
            return "tampered", f"{r['_file']} seal invalid", r
    latest: Dict[str, Dict[str, Any]] = {}
    for r in sorted(ex, key=_order):
        latest[str(r.get("oracle"))] = r
    for want, label, note in (("pass", "pass", ""),
                              ("pass-uncontrolled", "pass-uncontrolled", "executed, but no negative control")):
        for r in latest.values():
            if r.get("verdict") == want:
                return label, note, r
    ev_latest: Dict[str, Dict[str, Any]] = {}
    for r in sorted(ev, key=_order):
        ev_latest[str(r.get("oracle"))] = r
    for r in ev_latest.values():
        if r.get("verdict") == "pass":
            return "evidence", "captured evidence evaluated, not re-executed", r
    pool = list(latest.values()) + list(ev_latest.values())
    if pool:
        last = sorted(pool, key=_order)[-1]
        return "fail", "; ".join(last.get("reasons", [])) or "proof failed", last
    return "missing", "no executable proof", {}


def assess(eng: Engagement, fid: str) -> Dict[str, Any]:
    cfg = load_config(eng.root)
    threshold = int(cfg.get("audit.confidence_threshold", 75))
    meta, _body = finding_meta(eng, fid)
    rs = receipts(eng, fid)
    judged = load_judged(eng).get(fid)
    why: List[str] = []
    out: Dict[str, Any] = {"id": fid, "kind": meta.get("kind"), "claimed": meta.get("status"),
                           "severity": meta.get("severity"), "title": meta.get("title"), "measured": {}}
    tamper = False
    if judged and not seal_ok(eng, judged):
        tamper = True
        why.append("judged.json entry seal invalid")
    cst, cwhy = _cites_state(eng, meta, rs)
    est, ewhy, best = _exec_state(rs)
    if cst == "tampered" or est == "tampered":
        tamper = True
        why.append(cwhy if cst == "tampered" else ewhy)
    out.update(cites=cst, exec=est, judged=(judged or {}).get("verdict"), verifiers=(judged or {}).get("verifiers", []),
               confidence=(judged or {}).get("confidence"))
    if best:
        out["measured"] = best.get("measured") or {}
        out["oracle"] = best.get("oracle")
        out["repeat"] = best.get("repeat")
        out["control_kinds"] = (best.get("control") or {}).get("kinds") or (["waived"] if (best.get("control") or {}).get("waiver") else [])
        for kind, files in (("PoC file", best.get("poc_files") or {}), ("cited source", best.get("cited_files") or {})):
            for rel, sha in files.items():
                pth = os.path.join(eng.root, rel)
                if not os.path.isfile(pth) or util.sha256_file(pth) != sha:
                    est, ewhy = "stale", (f"the {kind} {rel} changed after the proof ran "
                                          f"(`sieve verify {fid} --rerun` re-executes it)")
                    out["exec"] = est
                    break
            if est == "stale":
                break
    sev = str((judged or {}).get("severity") or meta.get("severity") or "").lower()
    out["severity"] = sev or out["severity"]
    verdict = (judged or {}).get("verdict")
    not_independent = (util.read_json(eng.path("findings", "independence-failures.json"), {}) or {}).get(fid)
    if tamper:
        tier = "tampered"
    elif verdict == "rejected":
        tier = "rejected"
    elif meta.get("kind") != "FINDING" or verdict == "demoted":
        tier = "lead"
    elif cst == "stale":
        tier, why = "stale", why + [cwhy]
    elif est == "stale":
        tier, why = "stale", why + [ewhy]
    elif verdict in ("confirmed", "trace-only") and cst == "pass":
        conf = (judged or {}).get("confidence")
        if isinstance(conf, int) and conf < threshold:
            tier = "unvalidated"
            why.append(f"confidence {conf} is below the {threshold} threshold")
        elif est == "pass" and verdict == "confirmed" and not_independent:
            tier = "trace-verified"
            why.append("the proof's oracle is not independent of the code it judges: " + str(not_independent)[:160])
        elif est == "pass" and verdict == "confirmed":
            tier = "confirmed"
        elif verdict == "confirmed" and sev not in CONTROLLED_SEVERITIES:
            tier = "trace-verified"
            why.append("static proof (low/informational)")
        elif verdict == "trace-only" or est in ("pass-uncontrolled", "evidence"):
            tier = "trace-verified"
            why.append(ewhy or "no executable proof — trace only: " + str((judged or {}).get("trace_reason", "")))
        else:
            tier = "unvalidated"
            why.append(ewhy or "no controlled executable proof")
    else:
        tier = "unvalidated"
        if verdict not in ("confirmed", "trace-only"):
            why.append("not judged confirmed" if verdict != "cleared" else "gates cleared; proof pending")
        if cst != "pass":
            why.append(f"citations: {cst}" + (f" ({cwhy})" if cwhy else ""))
    out.update(tier=tier, why=[w for w in why if w])
    return out


def assess_all(eng: Engagement) -> List[Dict[str, Any]]:
    return [assess(eng, fid) for fid in all_finding_ids(eng)]


def blockers(eng: Engagement) -> List[str]:
    """What stops the report phase: candidates the machine cannot stand behind, and any tampering."""
    out: List[str] = []
    for p in ledger_problems(eng):
        out.append("TAMPER: " + p)
    for a in assess_all(eng):
        if a["kind"] != "FINDING" or a["tier"] in ("rejected", "lead"):
            continue
        if a["tier"] == "tampered":
            out.append(f"{a['id']}: receipts/verdict tampered")
        elif a["tier"] == "stale":
            out.append(f"{a['id']}: STALE — {'; '.join(a['why'])} (`sieve verify {a['id']} --rerun`)")
        elif a["tier"] == "unvalidated" and str(a.get("severity")) in CONTROLLED_SEVERITIES:
            out.append(f"{a['id']} ({a['severity']}): unvalidated — {'; '.join(a['why']) or 'not confirmed'}")
    return out


def pending_proof(eng: Engagement) -> List[str]:
    """Findings that cleared the gates but do not yet have a machine-accepted proof."""
    out = []
    for a in assess_all(eng):
        if a["kind"] == "FINDING" and a["judged"] in ("cleared", "confirmed", "trace-only") and \
                a["tier"] in ("unvalidated", "stale"):
            out.append(a["id"])
    return out
