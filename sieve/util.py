"""Small shared helpers: atomic writes, locking, hashing, time, slugs."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

try:  # POSIX advisory locking; absent on Windows.
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def epoch() -> float:
    return time.time()


def slug(text: str, maxlen: int = 60) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (s[:maxlen].rstrip("-")) or "x"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def atomic_write(path: str, data: str, mode: str = "w") -> None:
    """Write via temp file + rename so readers never see a half-written file."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        # Never translate LF to CRLF. Receipts and the ledger are hashed as written, and a Windows text-mode write
        # would change the bytes after the hash was taken (every proof would then read back as tampered).
        binary = "b" in mode
        with os.fdopen(fd, mode, encoding=None if binary else "utf-8", newline=None if binary else "\n") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def write_json(path: str, obj: Any) -> None:
    atomic_write(path, json.dumps(obj, indent=2, sort_keys=False, ensure_ascii=False) + "\n")


def read_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


@contextlib.contextmanager
def file_lock(path: str) -> Iterator[None]:
    """Exclusive cross-process lock on `path` (created if missing)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fh = open(path, "a+")
    try:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def run(cmd: Sequence[str], timeout: int = 60, cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    """Run a command, never raise on failure. Returns (rc, stdout, stderr)."""
    try:
        p = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout,
                           cwd=cwd, env=env, errors="replace")
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s: {' '.join(cmd)}"


def which(name: str) -> Optional[str]:
    import shutil
    return shutil.which(name)


def eprint(*a: Any) -> None:
    print(*a, file=sys.stderr)


def tsv_escape(s: Any) -> str:
    return str(s).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def read_tsv(path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    if not os.path.isfile(path):
        return [], []
    with open(path, encoding="utf-8") as fh:
        lines = [ln.rstrip("\n") for ln in fh if ln.strip()]
    if not lines:
        return [], []
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        cells = ln.split("\t")
        cells += [""] * (len(header) - len(cells))
        rows.append(dict(zip(header, cells)))
    return header, rows


def write_tsv(path: str, header: List[str], rows: List[Dict[str, Any]]) -> None:
    out = ["\t".join(header)]
    for r in rows:
        out.append("\t".join(tsv_escape(r.get(h, "")) for h in header))
    atomic_write(path, "\n".join(out) + "\n")


def count_lines(path: str) -> int:
    try:
        with open(path, "rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0
