"""Online knowledge sources behind one broker.

Twelve agents must never each hammer a rate-limited API. Every online call goes through the
Broker: a response cache plus a sliding-window limiter that lives in SQLite, so it holds
across processes (`BEGIN IMMEDIATE` is the cross-process lock).

Response schemas of third-party APIs are read defensively: unknown fields are ignored and
`sieve kb doctor <source>` shows the raw shape so a mismatch is visible, not silent.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import __version__
from .config import Config
from .kb_store import Index


class KBError(Exception):
    pass


class AuthError(KBError):
    pass


class RateLimited(KBError):
    def __init__(self, wait: float):
        super().__init__(f"rate limited; retry in {wait:.0f}s")
        self.wait = wait


def http_json(method: str, url: str, headers: Optional[Dict[str, str]] = None, body: Any = None,
              timeout: float = 25.0) -> Tuple[int, Dict[str, str], Any]:
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"User-Agent": f"sieve/{__version__}", "Accept": "application/json"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status, rh = resp.status, dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace") if exc.fp else ""
        status, rh = exc.code, dict(exc.headers.items()) if exc.headers else {}
    except (urllib.error.URLError, OSError) as exc:
        raise KBError(f"network error contacting {urllib.parse.urlparse(url).netloc}: {exc}") from exc
    try:
        parsed: Any = json.loads(raw) if raw.strip() else None
    except ValueError:
        parsed = raw
    return status, rh, parsed


class Broker:
    def __init__(self, index: Index, offline: bool = False):
        self.ix = index
        self.offline = offline or os.environ.get("SIEVE_OFFLINE") == "1"

    # ------------------------------------------------------------ cache
    def cache_get(self, key: str, ttl: float) -> Optional[Any]:
        r = self.ix.con.execute("SELECT fetched, ttl, payload FROM cache WHERE key=?", (key,)).fetchone()
        if r is not None and time.time() - r["fetched"] < min(ttl, r["ttl"]):
            return json.loads(r["payload"])
        return None

    def cache_put(self, key: str, source: str, ttl: float, data: Any) -> None:
        self.ix.con.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?)",
                            (key, source, time.time(), ttl, json.dumps(data)))

    # ------------------------------------------------------------ limiter
    def acquire(self, source: str, limit: int, per: float, max_wait: float = 90.0) -> float:
        """Take one slot from the sliding window. Blocks up to max_wait, then raises RateLimited."""
        waited = 0.0
        con = self.ix.con
        while True:
            con.execute("BEGIN IMMEDIATE")
            try:
                now = time.time()
                con.execute("DELETE FROM ratelimit WHERE source=? AND ts<?", (source, now - per))
                n, oldest = con.execute("SELECT COUNT(*), MIN(ts) FROM ratelimit WHERE source=?",
                                        (source,)).fetchone()
                if n < limit:
                    con.execute("INSERT INTO ratelimit VALUES (?,?)", (source, now))
                    con.execute("COMMIT")
                    return waited
                wait = float(oldest) + per - now
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            if waited + wait > max_wait:
                raise RateLimited(wait)
            step = min(max(wait, 0.05) + 0.02, 5.0)
            time.sleep(step)
            waited += step

    def penalise(self, source: str, limit: int, seconds: float) -> None:
        """Server said 429: fill the window so every process backs off."""
        now = time.time()
        self.ix.con.execute("BEGIN IMMEDIATE")
        self.ix.con.executemany("INSERT INTO ratelimit VALUES (?,?)", [(source, now)] * limit)
        self.ix.con.execute("COMMIT")
        self.ix.con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (f"penalty:{source}", str(now + seconds)))

    # ------------------------------------------------------------ the one entry point
    def call(self, source: str, cfg: Dict[str, Any], key: str, ttl: float,
             fn: Callable[[], Tuple[int, Dict[str, str], Any]], max_wait: float = 90.0) -> Tuple[Any, bool]:
        cached = self.cache_get(f"{source}:{key}", ttl)
        if cached is not None:
            return cached, True
        if self.offline:
            raise KBError(f"offline mode: {source} not contacted")
        rl = cfg.get("rate_limit") or {}
        limit, per = int(rl.get("requests", 20)), float(rl.get("per_seconds", 60))
        attempt = 0
        while True:
            self.acquire(source, limit, per, max_wait=max_wait)
            status, headers, data = fn()
            if status == 429:
                retry = float(headers.get("Retry-After") or headers.get("retry-after") or per)
                self.penalise(source, limit, retry)
                attempt += 1
                if attempt > 2:
                    raise RateLimited(retry)
                continue
            if status in (401, 403):
                raise AuthError(f"{source}: HTTP {status} — check the API key ({cfg.get('api_key_env', '')})")
            if status >= 500 and attempt < 3:
                attempt += 1
                time.sleep(2 ** attempt)
                continue
            if status >= 400:
                raise KBError(f"{source}: HTTP {status}: {str(data)[:300]}")
            self.cache_put(f"{source}:{key}", source, ttl, data)
            return data, False


# ---------------------------------------------------------------- normalisation helpers

def pick(obj: Any, *names: str, default: Any = "") -> Any:
    """First present, non-empty value among dotted names."""
    for n in names:
        cur = obj
        for part in n.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        if cur not in (None, "", [], {}):
            return cur
    return default


def _items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in ("findings", "results", "data", "items", "issues", "vulns", "vulnerabilities"):
            v = data.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
            if isinstance(v, dict):
                inner = _items(v)
                if inner:
                    return inner
    return []


def _str_list(v: Any) -> List[str]:
    out: List[str] = []
    for x in v if isinstance(v, list) else []:
        if isinstance(x, dict):
            x = pick(x, "value", "name", "title", "label")
        if x:
            out.append(str(x))
    return out


# ---------------------------------------------------------------- Solodit

def _solodit_filters(keywords: str, impact: Optional[List[str]], tags: Optional[List[str]],
                     firms: Optional[List[str]], categories: Optional[List[str]],
                     languages: Optional[List[str]], sort: str) -> Dict[str, Any]:
    f: Dict[str, Any] = {}
    if keywords:
        f["keywords"] = keywords
    if impact:
        f["impact"] = [i.upper() for i in impact]
    for name, vals in (("firms", firms), ("tags", tags), ("protocol_categories", categories),
                       ("languages", languages)):
        if vals:
            f[name] = [{"value": v} for v in vals]
    f["sortField"] = sort
    f["sortDirection"] = "Desc"
    return f


def norm_solodit(item: Dict[str, Any]) -> Dict[str, Any]:
    slug = str(pick(item, "slug", "id", "_id", "finding_id", "uuid"))
    url = str(pick(item, "url", "link", "source_link"))
    if not url and slug:
        url = f"https://solodit.cyfrin.io/issues/{slug}"
    return {
        "ref": f"solodit:{slug or pick(item, 'title')}",
        "source": "solodit",
        "title": str(pick(item, "title", "name", "issue_title", default="(untitled)")),
        "severity": str(pick(item, "impact", "severity", default="")).lower(),
        "body": str(pick(item, "content", "body", "description", "summary", "details", default="")),
        "firm": str(pick(item, "firm_name", "firm", "auditfirm_name", "audit_firm", "firm.name", default="")),
        "protocol": str(pick(item, "protocol_name", "protocol", "protocol.name", default="")),
        "tags": _str_list(pick(item, "tags", "issues_tags", "issue_tags", default=[])),
        "url": url,
        "quality": pick(item, "quality_score", "qualityScore", "quality", default=""),
    }


def solodit_search(broker: Broker, cfg: Config, keywords: str, impact: Optional[List[str]] = None,
                   tags: Optional[List[str]] = None, firms: Optional[List[str]] = None,
                   categories: Optional[List[str]] = None, languages: Optional[List[str]] = None,
                   page: int = 1, page_size: Optional[int] = None, sort: str = "Quality") -> List[Dict[str, Any]]:
    sc = cfg.source("solodit")
    if not sc.get("enabled", True):
        raise KBError("solodit is disabled in sieve.yaml")
    key_env = str(sc.get("api_key_env", "CYFRIN_API_KEY"))
    api_key = os.environ.get(key_env, "")
    if not api_key:
        raise AuthError(f"set {key_env}: solodit.cyfrin.io -> profile menu -> API Keys -> generate")
    size = int(page_size or sc.get("page_size", 20))
    filters = _solodit_filters(keywords, impact, tags, firms, categories, languages, sort)
    cache_key = json.dumps([page, size, filters], sort_keys=True)
    ttl = float((sc.get("cache_ttl") or {}).get("search", 300))
    first = broker.ix.con.execute("SELECT v FROM meta WHERE k='solodit_shape'").fetchone()
    shapes = [first["v"]] if first else [str(sc.get("request_shape", "nested"))]
    shapes.append("flat" if shapes[0] == "nested" else "nested")
    last_err: Optional[Exception] = None
    for shape in shapes:
        body = ({"page": page, "pageSize": size, "filters": filters} if shape == "nested"
                else dict({"page": page, "pageSize": size}, **filters))

        def do(body: Dict[str, Any] = body) -> Tuple[int, Dict[str, str], Any]:
            return http_json("POST", str(sc["endpoint"]), {"X-Cyfrin-API-Key": api_key}, body)
        try:
            data, _cached = broker.call("solodit", sc, f"{shape}:{cache_key}", ttl, do)
        except KBError as exc:
            last_err = exc
            if "HTTP 400" in str(exc) or "HTTP 422" in str(exc):
                continue  # wrong request shape: try the other one
            raise
        broker.ix.con.execute("INSERT OR REPLACE INTO meta VALUES ('solodit_shape', ?)", (shape,))
        hits = [norm_solodit(i) for i in _items(data)]
        store_hits(broker.ix, hits)
        return hits
    raise KBError(f"solodit rejected both request shapes: {last_err}")


# ---------------------------------------------------------------- OSV / NVD

def norm_osv(v: Dict[str, Any]) -> Dict[str, Any]:
    vid = str(pick(v, "id"))
    sev = str(pick(v, "database_specific.severity", default="")).lower()
    return {"ref": f"osv:{vid}", "source": "osv", "title": str(pick(v, "summary", default=vid)) or vid,
            "severity": sev, "body": str(pick(v, "details", default="")), "firm": "", "protocol": "",
            "tags": [str(a) for a in (v.get("aliases") or [])], "url": f"https://osv.dev/vulnerability/{vid}",
            "quality": ""}


def osv_query(broker: Broker, cfg: Config, package: str, ecosystem: str,
              version: Optional[str] = None) -> List[Dict[str, Any]]:
    sc = cfg.source("osv")
    if not sc.get("enabled", True):
        raise KBError("osv is disabled in sieve.yaml")
    body: Dict[str, Any] = {"package": {"name": package, "ecosystem": ecosystem}}
    if version:
        body["version"] = version
    ttl = float((sc.get("cache_ttl") or {}).get("search", 3600))

    def do() -> Tuple[int, Dict[str, str], Any]:
        return http_json("POST", str(sc["endpoint"]), None, body)
    data, _ = broker.call("osv", sc, json.dumps(body, sort_keys=True), ttl, do)
    hits = [norm_osv(v) for v in _items(data)]
    store_hits(broker.ix, hits)
    return hits


def norm_nvd(entry: Dict[str, Any]) -> Dict[str, Any]:
    cve = entry.get("cve", entry)
    cid = str(pick(cve, "id"))
    desc = ""
    for d in cve.get("descriptions") or []:
        if d.get("lang") == "en":
            desc = str(d.get("value", ""))
            break
    sev = str(pick(cve, "metrics.cvssMetricV31.0.cvssData.baseSeverity", default="")).lower()
    return {"ref": f"nvd:{cid}", "source": "nvd", "title": cid, "severity": sev, "body": desc, "firm": "",
            "protocol": "", "tags": [], "url": f"https://nvd.nist.gov/vuln/detail/{cid}", "quality": ""}


def nvd_search(broker: Broker, cfg: Config, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
    sc = cfg.source("nvd")
    if not sc.get("enabled", False):
        raise KBError("nvd is disabled in sieve.yaml (set kb.sources.nvd.enabled: true)")
    url = f"{sc['endpoint']}?{urllib.parse.urlencode({'keywordSearch': keyword, 'resultsPerPage': limit})}"
    headers: Dict[str, str] = {}
    key = os.environ.get(str(sc.get("api_key_env", "NVD_API_KEY")), "")
    if key:
        headers["apiKey"] = key
    ttl = float((sc.get("cache_ttl") or {}).get("search", 3600))

    def do() -> Tuple[int, Dict[str, str], Any]:
        return http_json("GET", url, headers)
    data, _ = broker.call("nvd", sc, url, ttl, do)
    hits = [norm_nvd(v) for v in _items(data)]
    store_hits(broker.ix, hits)
    return hits


# ---------------------------------------------------------------- hit store (feeds `kb use`)

def store_hits(ix: Index, hits: List[Dict[str, Any]]) -> None:
    now = time.time()
    for h in hits:
        ix.con.execute("INSERT OR REPLACE INTO hits VALUES (?,?,?,?)", (h["ref"], h["source"], json.dumps(h), now))


def get_hit(ix: Index, ref: str) -> Optional[Dict[str, Any]]:
    r = ix.con.execute("SELECT payload FROM hits WHERE ref=?", (ref,)).fetchone()
    return json.loads(r["payload"]) if r else None
