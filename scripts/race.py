#!/usr/bin/env python3
"""race.py — prove a check-then-act race with GENUINE concurrency.

Sieve requires real parallelism to confirm a race (a single Repeater send is not a
proof — agents/business-logic-agent.md). This fires N identical requests released at
the same instant via a barrier, so they hit the check-then-act window together, then
reports the response distribution. If a limited resource (a coupon, a balance, an
invite, a withdrawal) was granted more than once, the race is real. OPTIONAL adapter;
python3 stdlib only.

ACTIVE TESTING: this changes state. Run it only when the case card allows active
testing (shared-rules.md §8), and only against the in-scope target.

Usage:
  scripts/race.py <url> [-X POST] [-H "Cookie: a=b"]... [-d '{"amt":1}'] [-n 20]
"""
from __future__ import annotations

import argparse
import collections
import sys
import threading
import time
import urllib.error
import urllib.request


def parse(argv: list[str]):
    p = argparse.ArgumentParser(
        prog="race.py",
        description="Barrier-synced parallel requests to prove a check-then-act race.",
    )
    p.add_argument("url", help="In-scope URL to hit (http/https)")
    p.add_argument("-X", dest="method", default="GET", help="HTTP method (default GET)")
    p.add_argument("-H", dest="headers", action="append", default=[], metavar="K:V",
                   help="Request header, repeatable")
    p.add_argument("-d", dest="data", default=None, help="Request body")
    p.add_argument("-n", dest="n", type=int, default=20, help="Parallel requests (default 20)")
    return p.parse_args(argv)


def fence_gate(url: str) -> None:
    """Refuse unless the scope card lists this host AND allows active testing. Checked in code, through the same
    fence every Sieve oracle uses: a race changes state, so it never fires on the agent's say-so."""
    import os
    home = os.environ.get("SIEVE_HOME") or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
    sys.path.insert(0, home)
    from sieve.fence import require_host
    require_host(url, need_active=True)


def main(argv: list[str]) -> int:
    o = parse(argv)
    if "://" not in o.url:
        print("race.py: url must be http(s)://...", file=sys.stderr)
        return 2
    fence_gate(o.url)
    if o.n > 50:
        print("race.py: -n above 50 is a load test, not a race proof. Use 2 to 50.", file=sys.stderr)
        return 2
    if o.n < 2:
        print("race.py: -n must be >= 2", file=sys.stderr)
        return 2
    headers = {}
    for h in o.headers:
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()
    data = o.data.encode() if o.data is not None else None
    barrier = threading.Barrier(o.n)
    results = []
    lock = threading.Lock()

    def fire(_):
        req = urllib.request.Request(o.url, data=data, headers=headers, method=o.method)
        barrier.wait()
        t0 = time.time()
        try:
            r = urllib.request.urlopen(req, timeout=15)
            code, body = r.getcode(), r.read()
        except urllib.error.HTTPError as e:
            code, body = e.code, e.read()
        except Exception as e:
            code, body = "ERR", str(e).encode()
        with lock:
            results.append((code, len(body), round(time.time() - t0, 3)))

    print(f"# race: {o.n} parallel {o.method} {o.url}")
    threads = [threading.Thread(target=fire, args=(i,)) for i in range(o.n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    codes = collections.Counter(c for c, _, _ in results)
    lens = collections.Counter(l for _, l, _ in results)
    print("status codes:", dict(codes))
    print("body lengths:", dict(lens))
    ok = sum(v for k, v in codes.items() if isinstance(k, int) and 200 <= k < 300)
    print(f"\n2xx responses: {ok}/{o.n}")
    if ok > 1:
        print("=> If the resource was meant to be granted ONCE, this is a race:"
              "\n   the check-then-act window let %d requests through. Confirm the"
              "\n   server-side effect (balance/coupon/invite over-granted)." % ok)
    else:
        print("=> Only one success — no race on this endpoint (or the guard held).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
