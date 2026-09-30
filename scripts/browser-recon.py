#!/usr/bin/env python3
"""browser-recon.py: autonomous live-browser observation through CloakBrowser.

Captures what only a running client shows: every XHR/fetch, every WebSocket frame, the console, page errors,
the DOM, forms, and localStorage/sessionStorage/cookies, without a human opening DevTools. CloakBrowser exposes
the Playwright Page/Context API on a stealth Chromium, so pages that challenge a plain headless browser still
render. Sieve runs it as the `browser-recon` campaign node, which checks every URL against the scope fence
before this script is ever launched, and passes the fence's host list as --allow-host so a click cannot
navigate the main frame off-scope.

The authorized test identity (a dedicated test mailbox and, for a dApp, a dedicated test wallet) lives in a
persistent profile that survives sessions. One headed `--setup` pass signs in; later runs reuse it. The script
never takes a private key as a flag and never reads a wallet seed.

Usage:
  browser-recon.py --setup [--extension DIR] ...          # headed identity pass
  browser-recon.py --save-login https://app/login
  browser-recon.py https://app/dashboard --click "a#admin" --allow-host app.example.com
"""
from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import os
import re
import socket
import sys
import time
from urllib.parse import urlparse

DEFAULT_OUT = ".sieve/xray/browser-observations.md"

SNAPSHOT_JS = """() => ({
    local: Object.fromEntries(Object.entries(localStorage)),
    session: Object.fromEntries(Object.entries(sessionStorage)),
    cookies: document.cookie,
    title: document.title,
    links: [...document.querySelectorAll('a[href]')].map(a=>a.href).slice(0,300),
    forms: [...document.querySelectorAll('form')].map(f=>({action:f.action, method:f.method,
            inputs:[...f.querySelectorAll('input,select,textarea')].map(i=>i.name).filter(Boolean)})),
})"""


def user_home() -> str:
    return os.path.abspath(os.path.expanduser(os.environ.get("SIEVE_USER_HOME", "~/.sieve")))


def browser_home() -> str:
    """Where the test identity lives: $SIEVE_BROWSER_HOME, else ~/.sieve/browser, else an identity a previous
    tool already set up in ~/.helix (adopted in place, never copied)."""
    env = os.environ.get("SIEVE_BROWSER_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    mine = os.path.join(user_home(), "browser")
    if os.path.isdir(mine):
        return mine
    legacy = os.path.join(os.path.expanduser("~"), ".helix")
    if os.path.isfile(os.path.join(legacy, "browser-config.json")) or os.path.isdir(os.path.join(legacy, "browser-profile")):
        return legacy
    return mine


def default_profile() -> str:
    return os.environ.get("SIEVE_BROWSER_PROFILE") or os.path.join(browser_home(), "browser-profile")


def config_path() -> str:
    return os.path.join(browser_home(), "browser-config.json")


EXT_ID = re.compile(r"(?<![a-p])[a-p]{32}(?![a-p])")


def chrome_roots():
    home = os.path.expanduser("~")
    return [p for p in (
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data"),
        os.path.join(home, "Library", "Application Support", "Google", "Chrome"),
        os.path.join(home, ".config", "google-chrome"),
        os.path.join(home, ".config", "chromium")) if p and os.path.isdir(p)]


def _version_key(name: str):
    return [int(x) if x.isdigit() else 0 for x in re.split(r"[._-]", name)]


def resolve_extension(spec: str) -> str:
    """An unpacked-extension directory, given either that directory or just the extension ID. Chrome auto-updates
    wallets into a new versioned folder, so a saved path goes stale; the ID does not (a store extension's manifest
    carries a fixed key, so the ID and the state a profile holds under it are stable). Resolves to the newest
    installed version."""
    m = EXT_ID.search(spec)
    if not m:
        return spec
    ext_id = m.group(0)
    best = None
    for root in chrome_roots():
        for cand in glob.glob(os.path.join(root, "*", "Extensions", ext_id, "*")):
            if os.path.isfile(os.path.join(cand, "manifest.json")):
                if best is None or _version_key(os.path.basename(cand)) > _version_key(os.path.basename(best)):
                    best = cand
    if best and os.path.abspath(best) != os.path.abspath(spec):
        print(f"browser-recon: extension {ext_id} resolved to the newest installed version: {best}", file=sys.stderr)
        return best
    return spec if os.path.isdir(spec) else (best or spec)


def proxy_reachable(proxy: str) -> bool:
    try:
        u = urlparse(proxy if "://" in proxy else "http://" + proxy)
        with socket.create_connection((u.hostname, u.port or 8080), timeout=2):
            return True
    except OSError:
        return False


def check_identity(o) -> int:
    """Non-invasive health check of the test identity: opens the persistent profile, reads (never navigates) its cookies
    and lists which extensions loaded. Prints one JSON object; exit 0 when the identity is usable."""
    launch, launch_persistent_context = _import_cloak()
    report = {"profile": os.path.abspath(o.profile), "profile_exists": os.path.isdir(o.profile), "proxy": o.proxy or None,
              "proxy_reachable": (proxy_reachable(o.proxy) if o.proxy else None), "extensions_requested": o.extension,
              "extensions_missing": [e for e in o.extension if not os.path.isdir(e)]}
    if not report["profile_exists"]:
        report["error"] = "no persistent profile yet: run `python scripts/browser-recon.py --setup` once"
        print(json.dumps(report, indent=2))
        return 2
    try:
        browser, ctx = _open(launch, launch_persistent_context, o, headless=not _headed(o, False))
    except Exception as exc:                      # noqa: BLE001
        report["error"] = f"could not open the profile: {str(exc).splitlines()[0][:200]}"
        print(json.dumps(report, indent=2))
        return 2
    try:
        time.sleep(2)
        cookies = ctx.cookies()
        domains = {}
        for c in cookies:
            d = c.get("domain", "").lstrip(".")
            domains[d] = domains.get(d, 0) + 1
        google_session = any(c.get("name") in ("SID", "__Secure-1PSID", "SAPISID") and "google" in c.get("domain", "") for c in cookies)
        workers = [w.url for w in getattr(ctx, "service_workers", [])]
        pages = [p.url for p in ctx.pages]
        loaded = sorted({m.group(0) for u in workers + pages for m in [EXT_ID.search(u)] if m})
        report.update(cookie_count=len(cookies), top_cookie_domains=sorted(domains, key=lambda k: -domains[k])[:8],
                      google_session=google_session, extensions_loaded=loaded)
    finally:
        _close(browser, ctx)
    print(json.dumps(report, indent=2))
    return 0


def parse(argv):
    p = argparse.ArgumentParser(prog="browser-recon.py", description="Live-browser capture via CloakBrowser.")
    p.add_argument("url", nargs="?", help="Target URL to observe")
    p.add_argument("--setup", action="store_true", help="Headed identity pass: test mailbox + test wallet into the persistent profile")
    p.add_argument("--save-login", metavar="URL", help="Headed login at URL, then save the profile")
    p.add_argument("--profile", default=None, help="Persistent profile directory (default: <browser home>/browser-profile)")
    p.add_argument("--session", help="Optional extra storage_state JSON snapshot")
    p.add_argument("--ephemeral", action="store_true", help="No persistent profile (fresh, incognito-style context)")
    p.add_argument("--headful", action="store_true", help="Show the window")
    p.add_argument("--click", action="append", default=[], metavar="SELECTOR", help="Click a selector after load (repeatable)")
    p.add_argument("--out", default=DEFAULT_OUT, help="Observation markdown path")
    p.add_argument("--wait", type=float, default=3.0, help="Seconds to wait after load/click")
    p.add_argument("--allow-host", action="append", default=[], metavar="PATTERN",
                   help="Host pattern the main frame may navigate to (repeatable, fnmatch). Anything else is aborted.")
    p.add_argument("--humanize", dest="humanize", action="store_true", default=True)
    p.add_argument("--no-humanize", dest="humanize", action="store_false")
    p.add_argument("--human-preset", default="default", choices=("default", "careful"))
    p.add_argument("--extension", action="append", default=[], metavar="DIR_OR_ID",
                   help="Unpacked Chrome extension dir or its 32-letter ID (wallet); an ID resolves to the newest installed version. Repeatable.")
    p.add_argument("--proxy", help="Proxy URL, e.g. http://127.0.0.1:8080 (Burp)")
    p.add_argument("--no-proxy", action="store_true", help="Ignore a proxy saved in the browser config for this run")
    p.add_argument("--check", action="store_true", help="Health-check the test identity (profile, cookies, extensions, proxy) and exit")
    p.add_argument("--geoip", action="store_true", help="Match timezone/locale to the proxy exit IP (needs cloakbrowser[geoip])")
    p.add_argument("--timezone", help="IANA timezone, e.g. America/New_York")
    p.add_argument("--locale", help="BCP 47 locale, e.g. en-US")
    p.add_argument("--license-key", default=None, help="CloakBrowser key (else CLOAKBROWSER_LICENSE_KEY / ~/.cloakbrowser/license.key)")
    return p.parse_args(argv)


def _import_cloak():
    try:
        from cloakbrowser import launch, launch_persistent_context
        return launch, launch_persistent_context
    except ImportError:
        print("browser-recon: cloakbrowser not installed\n  pip install cloakbrowser\n"
              "  (the first launch downloads the Chromium build)", file=sys.stderr)
        sys.exit(3)


def _load_config() -> dict:
    path = config_path()
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _save_config(cfg: dict) -> None:
    path = os.path.join(user_home(), "browser", "browser-config.json") if browser_home() == os.path.join(
        os.path.expanduser("~"), ".helix") else config_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")


def _merged(o):
    """CLI wins; the saved browser-config.json fills the rest from the setup pass."""
    cfg = _load_config()
    if o.profile is None:
        o.profile = cfg.get("profile") or default_profile()
    if not o.extension:
        o.extension = list(cfg.get("extensions") or [])
    if o.no_proxy:
        o.proxy = None
    elif not o.proxy:
        o.proxy = cfg.get("proxy")
    if not o.geoip:
        o.geoip = bool(cfg.get("geoip"))
    o.extension = [resolve_extension(e) for e in o.extension]
    o.timezone = o.timezone or cfg.get("timezone")
    o.locale = o.locale or cfg.get("locale")
    if o.human_preset == "default" and cfg.get("human_preset"):
        o.human_preset = cfg["human_preset"]
    if o.license_key is None:
        o.license_key = cfg.get("license_key")
    return o


def _launch_kwargs(o, *, headless: bool) -> dict:
    kw = {"headless": headless, "humanize": o.humanize, "human_preset": o.human_preset, "stealth_args": True}
    if o.proxy:
        kw["proxy"] = o.proxy
    if o.geoip:
        if not o.proxy:
            print("browser-recon: --geoip ignored without --proxy", file=sys.stderr)
        else:
            kw["geoip"] = True
    if o.timezone:
        kw["timezone"] = o.timezone
    if o.locale:
        kw["locale"] = o.locale
    if o.extension:
        kw["extension_paths"] = o.extension
    if o.license_key:
        kw["license_key"] = o.license_key
    return kw


def _open(launch, launch_persistent_context, o, *, headless: bool):
    kw = _launch_kwargs(o, headless=headless)
    if o.ephemeral:
        browser = launch(**kw)
        ctx_args = {}
        if o.session and os.path.exists(o.session):
            ctx_args["storage_state"] = o.session
        return browser, browser.new_context(**ctx_args)
    os.makedirs(o.profile, exist_ok=True)
    return None, launch_persistent_context(o.profile, **kw)


def _close(browser, ctx):
    for thing in (ctx, browser):
        if thing is not None:
            try:
                thing.close()
            except Exception:
                pass


def _host_ok(url: str, patterns) -> bool:
    if not patterns:
        return True
    if url.startswith(("about:", "data:", "blob:")):
        return True
    host = (urlparse(url).hostname or "").lower()
    for pat in patterns:
        pat = pat.lower().strip()
        if pat.startswith("*."):
            if host.endswith(pat[1:]) and host != pat[2:]:
                return True
        elif fnmatch.fnmatch(host, pat):
            return True
    return False


def _guard_navigation(ctx, patterns, blocked):
    """Abort any main-frame navigation to a host the fence did not list. Sub-resources (CDNs, analytics) load as
    the page asks: the page is in scope, the third parties it pulls in are just what it fetches."""
    if not patterns:
        return

    def handler(route):
        req = route.request
        try:
            nav = req.is_navigation_request() and req.frame.parent_frame is None
        except Exception:
            nav = False
        if nav and not _host_ok(req.url, patterns):
            blocked.append(req.url)
            # 204 No Content: a navigation answered this way leaves the current document in place, so the page under
            # observation is not replaced by an error page (which would destroy its JS context mid-capture).
            route.fulfill(status=204, body="")
        else:
            route.continue_()
    ctx.route("**/*", handler)


def _attach(pg, reqs, resps, ws_frames, console, errors):
    pg.on("request", lambda r: reqs.append({"m": r.method, "u": r.url, "h": dict(r.headers), "body": (r.post_data or "")[:2000]}))

    def on_resp(r):
        body = ""
        try:
            ct = r.headers.get("content-type", "")
            if any(t in ct for t in ("json", "text", "javascript", "xml")):
                body = r.text()[:4000]
        except Exception:
            pass
        resps.append({"s": r.status, "u": r.url, "ct": r.headers.get("content-type", ""), "body": body})
    pg.on("response", on_resp)

    def on_ws(ws):
        ws.on("framesent", lambda f: ws_frames.append(("->", ws.url, str(f)[:500])))
        ws.on("framereceived", lambda f: ws_frames.append(("<-", ws.url, str(f)[:500])))
    pg.on("websocket", on_ws)
    pg.on("console", lambda m: console.append(f"{m.type}: {m.text[:300]}"))
    pg.on("pageerror", lambda e: errors.append(str(e)[:300]))


def _headed(o, setup: bool) -> bool:
    return bool(setup or o.extension or o.headful)


def _persist_config(o) -> None:
    _save_config({"profile": o.profile, "extensions": o.extension, "proxy": o.proxy, "geoip": bool(o.geoip and o.proxy),
                  "timezone": o.timezone, "locale": o.locale, "humanize": True, "human_preset": o.human_preset})


def setup_pass(o) -> int:
    launch, launch_persistent_context = _import_cloak()
    start = o.save_login or o.url or "about:blank"
    browser, ctx = _open(launch, launch_persistent_context, o, headless=False)
    pg = ctx.new_page()
    pg.goto(start, wait_until="domcontentloaded")
    print(f"\n[browser-recon] Headed CloakBrowser at {start}")
    print(f"[browser-recon] Profile: {os.path.abspath(o.profile)}")
    if o.extension:
        print("[browser-recon] Extensions: " + ", ".join(o.extension))
    print("[browser-recon] In this window, using the DEDICATED TEST identity only:")
    print("  1. Sign in to the test mailbox (or the app's test login).")
    print("  2. For a dApp: unlock the test wallet extension and connect it.")
    print("  3. Press Enter here when the identity is ready.")
    print("[browser-recon] Sieve never reads a wallet seed. Import it by hand.")
    try:
        input()
    except EOFError:
        time.sleep(60)
    _persist_config(o)
    if o.session:
        os.makedirs(os.path.dirname(o.session) or ".", exist_ok=True)
        ctx.storage_state(path=o.session)
        print(f"[browser-recon] Extra storage_state snapshot: {o.session}")
    print(f"[browser-recon] Identity saved. Later runs reuse --profile {o.profile}")
    _close(browser, ctx)
    return 0


def capture(o) -> int:
    launch, launch_persistent_context = _import_cloak()
    reqs, resps, ws_frames, console, errors, blocked = [], [], [], [], [], []
    headed = _headed(o, setup=False)
    browser, ctx = _open(launch, launch_persistent_context, o, headless=not headed)
    _guard_navigation(ctx, o.allow_host, blocked)
    pg = ctx.new_page()
    _attach(pg, reqs, resps, ws_frames, console, errors)
    pg.goto(o.url, wait_until="domcontentloaded")
    time.sleep(o.wait)
    for sel in o.click:
        before = len(blocked)
        try:
            pg.click(sel, timeout=5000)
            time.sleep(o.wait)
        except Exception as e:
            errors.append(f"click {sel} failed: {e}")
        if len(blocked) > before:            # the guard refused an off-scope navigation: return to the page we are observing
            errors.append(f"click {sel}: navigation off-scope was refused ({blocked[-1]})")
            try:
                pg.goto(o.url, wait_until="domcontentloaded")
                time.sleep(o.wait)
            except Exception as e:
                errors.append(f"could not return to {o.url}: {e}")
    try:
        pg.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    storage = {}
    for attempt in range(3):
        try:
            storage = pg.evaluate(SNAPSHOT_JS)
            break
        except Exception as e:                # a navigation destroyed the context: go back and retry
            errors.append(f"snapshot failed: {e}")
            try:
                pg.goto(o.url, wait_until="domcontentloaded")
                time.sleep(max(1.0, o.wait))
            except Exception:
                break
    try:
        dom_len = len(pg.content())
        title = storage.get("title") or pg.title()
    except Exception:
        dom_len, title = 0, storage.get("title", "")
    _close(browser, ctx)

    os.makedirs(os.path.dirname(o.out) or ".", exist_ok=True)
    auth = "profile" if not o.ephemeral else ("session" if o.session else "none")
    xhr = [r for r in reqs if r["u"] != o.url]
    with open(o.out, "w", encoding="utf-8") as f:
        w = f.write
        w(f"# Live-browser observation: {o.url}\n\n")
        w(f"engine: CloakBrowser | identity: {auth} | title: {title} | DOM {dom_len} bytes | {len(reqs)} requests | "
          f"{len(ws_frames)} WS frames | humanize: {o.humanize} | headed: {headed}\n\n")
        w("## Endpoints the app actually calls (feed the authorization model)\n")
        seen = set()
        for r in reqs:
            key = (r["m"], r["u"].split("?")[0])
            if key in seen:
                continue
            seen.add(key)
            w(f"  {r['m']} {r['u']}\n")
        w("\n## Responses (status, content-type)\n")
        for r in resps[:120]:
            w(f"  {r['s']} {r['ct']} {r['u']}\n")
        if ws_frames:
            w("\n## WebSocket frames (realtime, invisible to curl)\n")
            for d, u, fr in ws_frames[:80]:
                w(f"  {d} {u}  {fr}\n")
        w("\n## Storage / session (client-side trust surface)\n")
        w(f"  localStorage keys: {list(storage.get('local', {}).keys())}\n")
        w(f"  sessionStorage keys: {list(storage.get('session', {}).keys())}\n")
        w(f"  cookies: {storage.get('cookies', '')[:400]}\n")
        w("\n## Forms (action, method, inputs)\n")
        for fm in storage.get("forms", []):
            w(f"  {fm['method']} {fm['action']}  inputs={fm['inputs']}\n")
        if console:
            w("\n## Console (leaks, debug endpoints, errors)\n" + "".join(f"  {c}\n" for c in console[:40]))
        if errors:
            w("\n## Page errors\n" + "".join(f"  {e}\n" for e in errors[:20]))
        if blocked:
            w("\n## Navigations refused (outside the scope fence)\n" + "".join(f"  {b}\n" for b in blocked[:20]))
        w("\nEvery endpoint, WebSocket frame and storage item above is a LEAD for the hunters, never a finding.\n")
    print(f"browser-recon: wrote {o.out}: {len(reqs)} requests, {len(ws_frames)} WS frames, {len(xhr)} XHR")
    return 0


def main(argv) -> int:
    o = _merged(parse(argv))
    if o.check:
        return check_identity(o)
    if o.setup or o.save_login:
        return setup_pass(o)
    if not o.url:
        parse(["-h"])
        return 2
    return capture(o)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
