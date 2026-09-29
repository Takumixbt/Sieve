"""Web x-ray: merge structured output that REAL tools already produced into one surface list.

This does not crawl, scan, or fingerprint anything itself — subfinder/httpx/katana/gau do
discovery, Burp does authenticated crawling and holds the ground truth for auth, and this just
normalises their exports (a URL list, an OpenAPI doc, a HAR capture) into `surface.tsv` so the
agent has one table instead of three formats. See references/local-tooling.md for the tool list
and the Burp extensions that make each phase concrete.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from . import util, yamlish

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}


def norm_path(p: str) -> str:
    """Collapse anything that varies per request to `{id}`, so the same route from different
    sources (OpenAPI's `{invoiceId}`, a HAR hit on `/invoices/482`) merges to one row."""
    import re
    p = re.sub(r"[?#].*$", "", p)
    p = re.sub(r"\{[^{}]*\}", "{id}", p)
    p = re.sub(r"/(?:\d+|[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}|[0-9a-fA-F]{24,})(?=/|$)", "/{id}", p)
    return re.sub(r"/+", "/", p) or "/"


def _row(method: str, path: str, source: str, where: str, auth: str = "unknown", **kw: Any) -> Dict[str, Any]:
    return {"method": method.upper(), "path": path if path.startswith("/") else "/" + path, "auth": auth,
            "sources": [source], "where": [where], **kw}


def scan_openapi(path: str) -> List[Dict[str, Any]]:
    """OpenAPI/Swagger 2/3, JSON or YAML. `security` at the operation level overrides the global one."""
    text = util.read_text(path)
    try:
        doc = json.loads(text)
    except ValueError:
        doc = yamlish.loads(text)
    if not isinstance(doc, dict):
        return []
    global_sec = bool(doc.get("security"))
    rows: List[Dict[str, Any]] = []
    for p, item in (doc.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for meth, op in item.items():
            if meth.upper() not in METHODS or not isinstance(op, dict):
                continue
            sec = op.get("security", None)
            auth = "yes" if (sec if sec is not None else global_sec) else "no"
            body_props: List[str] = []
            for ct in ((op.get("requestBody") or {}).get("content", {})).values():
                body_props += list(((ct or {}).get("schema") or {}).get("properties") or {})[:12]
            rows.append(_row(meth, str(p), "openapi", f"{os.path.basename(path)}#{meth}:{p}", auth,
                             body_params=body_props, deprecated=bool(op.get("deprecated"))))
    return rows


def scan_har(path: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """A Burp/DevTools/mitmproxy export. Presence of an auth header/cookie is the auth signal —
    it is what Burp actually sent, not a guess from source."""
    har = json.loads(util.read_text(path))
    rows: List[Dict[str, Any]] = []
    hosts = set()
    for e in (har.get("log") or {}).get("entries", []):
        req = e.get("request") or {}
        u = urlparse(req.get("url", ""))
        if not u.path:
            continue
        hosts.add(u.netloc)
        hdrs = {h.get("name", "").lower() for h in req.get("headers", [])}
        auth = "yes" if hdrs & {"authorization", "cookie", "x-api-key", "x-auth-token"} else "no"
        rows.append(_row(req.get("method", "GET"), norm_path(u.path), "har", f"{os.path.basename(path)}:{u.netloc}",
                         auth, host=u.netloc, status=(e.get("response") or {}).get("status")))
    return rows, sorted(hosts)


def scan_url_list(path: str) -> List[Dict[str, Any]]:
    """One URL per line: `httpx -silent` / `katana -silent` / `gau` output, piped to a file."""
    rows: List[Dict[str, Any]] = []
    for ln in util.read_text(path).split("\n"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        u = urlparse(ln if "://" in ln else "//" + ln)
        rows.append(_row("GET", norm_path(u.path or "/"), "urllist", f"{os.path.basename(path)}", "unknown", host=u.netloc))
    return rows


def merge(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    rank = {"yes": 2, "no": 1, "unknown": 0}
    for r in rows:
        key = (r["method"], norm_path(r["path"]))
        cur = merged.get(key)
        if cur is None:
            merged[key] = dict(r, path=key[1])
            continue
        cur["sources"] = sorted(set(cur["sources"]) | set(r["sources"]))
        cur["where"] = (cur["where"] + r["where"])[:6]
        if r["auth"] != cur["auth"]:
            cur.setdefault("auth_conflict", []).append(f"{r['sources'][0]} says {r['auth']}")
            if rank[r["auth"]] > rank[cur["auth"]] and cur["auth"] == "unknown":
                cur["auth"] = r["auth"]
        for k in ("host", "status", "body_params", "deprecated"):
            if k in r and k not in cur:
                cur[k] = r[k]
    return sorted(merged.values(), key=lambda x: (x["path"], x["method"]))


def run(openapi: Optional[List[str]] = None, har: Optional[List[str]] = None,
        url_lists: Optional[List[str]] = None) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    hosts: List[str] = []
    notes: List[str] = []
    for f in openapi or []:
        try:
            rows += scan_openapi(f)
        except Exception as exc:  # noqa: BLE001 — one bad input file must not sink the whole merge
            notes.append(f"openapi {f}: {exc}")
    for f in har or []:
        try:
            r, h = scan_har(f)
            rows += r
            hosts += h
        except Exception as exc:  # noqa: BLE001
            notes.append(f"har {f}: {exc}")
    for f in url_lists or []:
        try:
            rows += scan_url_list(f)
        except OSError as exc:
            notes.append(f"url list {f}: {exc}")
    surface = merge(rows)
    return {"pack": "web", "generated": util.now_iso(), "surface": surface,
            "counts": {"endpoints": len(surface), "auth_unknown_or_no": sum(1 for r in surface if r["auth"] != "yes")},
            "hosts": sorted(set(hosts)), "notes": notes}


def surface_tsv(facts: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]]]:
    header = ["method", "path", "auth", "sources", "where"]
    rows = [{"method": r["method"], "path": r["path"], "auth": r["auth"],
             "sources": ",".join(r["sources"]), "where": r["where"][0] if r["where"] else ""}
            for r in facts["surface"]]
    return header, rows
