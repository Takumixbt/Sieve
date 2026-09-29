"""Shared test helpers."""
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)
BIN = os.path.join(ROOT, "bin", "sieve")


@contextlib.contextmanager
def tmpdir():
    d = tempfile.mkdtemp(prefix="sieve-test-")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sieve(*args, cwd=None, env=None, input_text=None, check=False):
    e = dict(os.environ)
    e["SIEVE_HOME"] = ROOT
    e.setdefault("SIEVE_USER_HOME", tempfile.mkdtemp(prefix="sieve-uh-"))
    if env:
        e.update(env)
    p = subprocess.run([BIN, *args], cwd=cwd, env=e, input=input_text,
                       capture_output=True, text=True)
    if check and p.returncode != 0:
        raise AssertionError(f"sieve {' '.join(args)} failed rc={p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def make_engagement(d, packs=("web3",), scope=True, passes=3):
    """Create an engagement with a filled scope card, in-process."""
    from sieve import util
    from sieve.fence import CASE_TEMPLATE
    from sieve.state import Engagement
    eng = Engagement.create(d, list(packs), name="fixture", passes=passes)
    card = CASE_TEMPLATE.format(name="fixture", packs="[" + ",".join(packs) + "]")
    if scope:
        card = card.replace("hosts: []              #", "hosts: [app.example.com]  #", 1)
        card = card.replace("paths: []              #", "paths: [src]  #", 1)
    util.atomic_write(eng.case_path(), card)
    return eng
