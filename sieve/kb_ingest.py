"""Bulk precedent ingestion from public, keyless sources into the local knowledge index.

The knowledge base has two tiers. The *vault* holds cards a human or an engagement wrote (curated, confirmed,
lessons): few, high signal, an Obsidian graph. The *precedent tier* holds the public record: thousands of
disclosed reports and exploit write-ups, searchable but never written into the vault as files, so the graph stays
readable. `sieve kb ingest` fills the second tier; `sieve kb search` and `sieve kb prime` read both, and `sieve kb
use` promotes a precedent that helped into a curated card.

Every source here needs no account and no API key. Third-party response shapes are parsed defensively: a source
that changes format reports zero rows and an error, never a crash and never fabricated data.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Any, Callable, Dict, Iterable, List, Optional

from . import __version__

UA = f"sieve/{__version__} (+https://github.com/Takumixbt/Sieve)"
BODY_CAP = 6000
FRESH_DAYS = 7


class IngestError(Exception):
    pass


# ---------------------------------------------------------------- transport

def http_get(url: str, timeout: float = 90.0, headers: Optional[Dict[str, str]] = None) -> bytes:
    if os.environ.get("SIEVE_OFFLINE") == "1":
        raise IngestError("offline mode: no network access")
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA}, **(headers or {})))
    last: Optional[Exception] = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise IngestError(f"HTTP {exc.code} for {url}") from exc
            last = exc
        except (urllib.error.URLError, OSError) as exc:     # resets and timeouts are routine on a long crawl
            last = exc
        time.sleep(1.5 * (attempt + 1))
    raise IngestError(f"network error for {urllib.parse.urlparse(url).netloc}: {last}")


def http_text(url: str, **kw: Any) -> str:
    return http_get(url, **kw).decode("utf-8", "replace")


_TOKEN: Optional[str] = None


def github_token() -> str:
    """A GitHub token raises the API limit from 60/hour. Optional: taken from the environment or an
    authenticated `gh`, never required and never stored."""
    global _TOKEN
    if _TOKEN is not None:
        return _TOKEN
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not tok and shutil.which("gh"):
        try:
            tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            tok = ""
    _TOKEN = tok
    return tok


def github_json(url: str) -> Any:
    headers = {"Accept": "application/vnd.github+json"}
    tok = github_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    return json.loads(http_text(url, headers=headers))


# ---------------------------------------------------------------- normalisation

_CLASSES = [
    # Native memory safety first: "heap buffer overflow" must not fall through to integer overflow.
    (r"use.after.free|double free|\buaf\b", "use-after-free"),
    (r"buffer overflow|heap[- ]?(?:buffer)?|out.of.bounds|\boob\b|stack overflow|memory corruption|stack[- ]based|buffer over-?read", "memory-corruption"),
    (r"type confusion|uninitiali[sz]ed", "type-confusion"),
    # Web classes, most specific first.
    (r"sql ?inject|\bsqli\b", "sql-injection"), (r"cross.site scripting|\bxss\b", "xss"), (r"csrf|cross.site request forgery", "csrf"),
    (r"ssrf|server.side request", "ssrf"), (r"xxe|xml external", "xxe"), (r"open redirect", "open-redirect"),
    (r"path traversal|directory traversal|zip slip", "path-traversal"), (r"deserial", "deserialization"),
    (r"prototype pollution", "prototype-pollution"), (r"request smuggling|desync", "request-smuggling"),
    (r"idor|insecure direct object", "idor"),
    (r"remote code execution|command injection|\brce\b|code injection", "rce"),
    (r"race condition|toctou|time.of.check", "race-condition"),
    (r"authentication bypass|auth bypass|broken auth|\bjwt\b|session fixation", "authentication"),
    # Smart-contract classes.
    (r"reentran", "reentrancy"), (r"price manipulat|oracle|\btwap\b|spot price|flash.?loan", "oracle-manipulation"),
    (r"rounding|precision|inflation attack|share (?:price|inflation)|donation", "math-precision"),
    (r"integer (?:overflow|underflow)|arithmetic (?:overflow|underflow)|\boverflow\b|\bunderflow\b", "integer-overflow"),
    (r"signature|replay attack|ecrecover|\bpermit\(|eip-?2612", "signature"), (r"front.?run|sandwich|\bmev\b", "frontrunning"),
    (r"governance|voting|proposal", "governance"), (r"bridge|cross.chain", "cross-chain"),
    (r"upgrad|proxy|initiali[sz]", "upgradeability"),
    (r"access control|unauthori[sz]ed|missing (?:auth|check|modifier)|onlyowner|permission|privilege", "access-control"),
    # Generic last.
    (r"denial of service|\bdos\b|resource exhaustion", "dos"),
    (r"information disclosure|info leak|sensitive data|exposure", "information-disclosure"),
    (r"logic|business|validation|improper input", "business-logic"),
]
_MEM = re.compile(r"overflow|out.of.bounds|use.after.free|heap|memory|underflow|double free|uninitiali[sz]ed|type confusion", re.I)


def classify(text: str, default: str = "other") -> str:
    low = (text or "").lower()
    for rx, cls in _CLASSES:
        if re.search(rx, low):
            return cls
    return default


def _row(source: str, domain: str, title: str, url: str, body: str, klass: str = "", severity: str = "",
         protocol: str = "", fix: str = "", tags: Optional[List[str]] = None, date: str = "") -> Dict[str, Any]:
    key = hashlib.sha1(f"{source}|{url}|{title}".encode()).hexdigest()[:10]
    return {"id": f"PR-{source}-{key}", "source": source, "domain": domain, "class": klass or classify(title + " " + body),
            "title": title.strip()[:240], "severity": severity, "protocol": protocol, "url": url, "fix": fix,
            "tags": " ".join(tags or []), "body": re.sub(r"[ \t]+\n", "\n", body).strip()[:BODY_CAP], "date": date}


# ---------------------------------------------------------------- sources

def src_defihacklabs(opts: Dict[str, Any], log: Callable[[str], None]) -> Iterable[Dict[str, Any]]:
    base = "https://raw.githubusercontent.com/SunWeb3Sec/DeFiHackLabs/main"
    this_year = int(time.strftime("%Y"))
    for year in range(2020, this_year + 1):
        try:
            text = http_text(f"{base}/past/{year}/README.md")
        except IngestError:
            continue
        for block in re.split(r"(?m)^### (?=\d{8}\s)", text)[1:]:
            head, _, rest = block.partition("\n")
            m = re.match(r"(\d{8})\s+(.+)$", head.strip())
            if not m:
                continue
            date, name_type = m.groups()
            name, _, kind = name_type.rpartition(" - ")
            name, kind = (name or name_type).strip(), (kind if name else "").strip()
            lost = re.search(r"### Lost:\s*(.+)", rest)
            poc = re.search(r"\[([\w.\-]+_exp\.sol)\]\(([^)]+)\)", rest)
            links = re.findall(r"https?://[^\s)>\]]+", rest.split("Link reference")[-1])
            url = links[0] if links else (f"https://github.com/SunWeb3Sec/DeFiHackLabs/blob/main/{poc.group(2).replace('../../', '')}" if poc else "")
            body = (f"{name} was exploited on {date} ({kind or 'root cause not stated'}). "
                    f"Lost: {lost.group(1).strip() if lost else 'unknown'}. "
                    + (f"A runnable Foundry reproduction exists in DeFiHackLabs: {poc.group(1)}. " if poc else "")
                    + ("References: " + " ".join(links[:4]) if links else ""))
            yield _row("defihacklabs", "web3", f"{name}: {kind}" if kind else name, url, body,
                       klass=classify(kind + " " + name), severity="critical", date=date,
                       tags=["exploit", "real-incident", str(year)])


def src_web3_vulns(opts: Dict[str, Any], log: Callable[[str], None]) -> Iterable[Dict[str, Any]]:
    base = "https://raw.githubusercontent.com/kadenzipfel/smart-contract-vulnerabilities/master"
    index = http_text(f"{base}/README.md")
    for rel in dict.fromkeys(re.findall(r"\(\.?/?(vulnerabilities/[\w\-]+\.md)\)", index)):
        try:
            text = http_text(f"{base}/{rel}")
        except IngestError as exc:
            log(f"  skip {rel}: {exc}")
            continue
        title = (re.search(r"(?m)^#{1,2}\s+(.+)$", text) or [None, rel])[1].strip()
        yield _row("web3-vulns", "web3", title, f"https://github.com/kadenzipfel/smart-contract-vulnerabilities/blob/master/{rel}",
                   text, klass=classify(title + " " + rel, default=os.path.basename(rel)[:-3]),
                   tags=["reference", "vulnerability-class"])


def src_c4(opts: Dict[str, Any], log: Callable[[str], None]) -> Iterable[Dict[str, Any]]:
    limit = int(opts.get("limit") or 40)
    q = urllib.parse.quote("org:code-423n4 findings in:name")
    repos: List[str] = []
    page = 1
    while page <= 4:                      # the whole list is ~400 repos; contests are named YYYY-MM-name, so sort by name
        data = github_json(f"https://api.github.com/search/repositories?q={q}&sort=updated&per_page=100&page={page}")
        names = [i["name"] for i in data.get("items", []) if str(i.get("name", "")).endswith("-findings")]
        if not names:
            break
        repos += names
        page += 1
    repos = sorted(set(repos), reverse=True)
    for name in repos[:limit]:
        try:
            report = http_text(f"https://raw.githubusercontent.com/code-423n4/{name}/main/report.md", timeout=120)
        except IngestError:
            continue
        contest = name[:-len("-findings")]
        parts = re.split(r"(?m)^## (?=\[\[?[HM]-\d+\])", report)[1:]
        for part in parts:
            head, _, body = part.partition("\n")
            m = re.match(r"\[\[?([HM])-(\d+)\]\s*(.+?)\]?(?:\((https?://[^)]+)\))?\s*$", head.strip())
            if not m:
                continue
            sev, _n, title, url = m.groups()
            title = re.sub(r"\]\(https?://.*$", "", title).strip("[] ")
            yield _row("c4", "web3", title, url or f"https://github.com/code-423n4/{name}", body,
                       severity="high" if sev == "H" else "medium", protocol=contest,
                       tags=["code4rena", "contest", contest])
        log(f"  {name}")


def src_hackerone(opts: Dict[str, Any], log: Callable[[str], None]) -> Iterable[Dict[str, Any]]:
    text = http_text("https://raw.githubusercontent.com/reddelexc/hackerone-reports/master/data.csv", timeout=120)
    for r in csv.DictReader(io.StringIO(text)):
        title, weak = (r.get("title") or "").strip(), (r.get("vuln_type") or "").strip()
        if not title:
            continue
        link = (r.get("link") or "").strip()
        bounty = r.get("bounty") or "0"
        domain = "binary" if _MEM.search(title + " " + weak) else "web"
        body = (f"HackerOne report to {r.get('program', '?')}: {title}. Weakness: {weak or 'unspecified'}. "
                f"Upvotes: {r.get('upvotes', '0')}. Bounty: ${bounty}.")
        yield _row("hackerone", domain, title, "https://" + link if link and not link.startswith("http") else link, body,
                   klass=classify(weak + " " + title), protocol=r.get("program", ""),
                   tags=["disclosed", "bounty" if bounty not in ("0", "0.0", "") else "no-bounty"])


def src_cisa_kev(opts: Dict[str, Any], log: Callable[[str], None]) -> Iterable[Dict[str, Any]]:
    data = json.loads(http_text("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"))
    for v in data.get("vulnerabilities", []):
        cve = v.get("cveID", "")
        desc = f"{v.get('vulnerabilityName', '')}. {v.get('shortDescription', '')}"
        domain = "binary" if _MEM.search(desc) else "web"
        yield _row("cisa-kev", domain, f"{cve} {v.get('vendorProject', '')} {v.get('product', '')}".strip(),
                   f"https://nvd.nist.gov/vuln/detail/{cve}",
                   f"{desc} Exploited in the wild (CISA KEV, added {v.get('dateAdded', '')}). "
                   f"Known ransomware use: {v.get('knownRansomwareCampaignUse', 'Unknown')}. CWE: {', '.join(v.get('cwes') or [])}.",
                   klass=classify(desc), severity="critical", protocol=str(v.get("vendorProject", "")),
                   tags=["exploited-in-the-wild"] + [str(c) for c in v.get("cwes") or []], date=str(v.get("dateAdded", "")))


def src_exploitdb(opts: Dict[str, Any], log: Callable[[str], None]) -> Iterable[Dict[str, Any]]:
    text = http_text("https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv", timeout=180)
    for r in csv.DictReader(io.StringIO(text)):
        desc = (r.get("description") or "").strip()
        if not desc:
            continue
        typ, plat = (r.get("type") or ""), (r.get("platform") or "")
        domain = "web" if typ == "webapps" or plat in ("php", "asp", "jsp", "multiple") and typ == "webapps" else "binary"
        yield _row("exploitdb", domain, desc, f"https://www.exploit-db.com/exploits/{r.get('id')}",
                   f"{desc}. Platform: {plat}. Type: {typ}. Codes: {r.get('codes', '')}. Published {r.get('date_published', '')}.",
                   klass=classify(desc), protocol=plat, tags=["exploit", typ, plat], date=r.get("date_published", ""))


OSV_DOMAIN = {"OSS-Fuzz": "binary", "Linux": "binary", "Debian": "binary", "Ubuntu": "binary", "Android": "binary"}


def src_osv(opts: Dict[str, Any], log: Callable[[str], None]) -> Iterable[Dict[str, Any]]:
    """OSV bulk dumps. Each record carries its fix commits, which is what the "what changed" method wants."""
    ecos = [e.strip() for e in str(opts.get("osv_ecosystem") or "OSS-Fuzz").split(",") if e.strip()]
    cap = int(opts.get("limit") or 0)
    for eco in ecos:
        blob = http_get(f"https://osv-vulnerabilities.storage.googleapis.com/{urllib.parse.quote(eco)}/all.zip", timeout=300)
        n = 0
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                try:
                    v = json.loads(zf.read(name))
                except ValueError:
                    continue
                vid = str(v.get("id", ""))
                summary = str(v.get("summary") or vid)
                details = str(v.get("details") or "")
                pkgs = sorted({str((a.get("package") or {}).get("name", "")) for a in v.get("affected", []) if a.get("package")})
                fixes: List[str] = []
                for ref in v.get("references", []):
                    url = str(ref.get("url", ""))
                    if ref.get("type") == "FIX" or re.search(r"/commit/[0-9a-f]{7,40}", url):
                        fixes.append(url)
                for a in v.get("affected", []):
                    for rg in a.get("ranges", []):
                        if rg.get("type") == "GIT" and rg.get("repo"):
                            for ev in rg.get("events", []):
                                if ev.get("fixed"):
                                    fixes.append(f"{rg['repo']} @ {ev['fixed']}")
                sev = str((v.get("database_specific") or {}).get("severity", "")).lower()
                yield _row("osv", OSV_DOMAIN.get(eco, "web"), f"{vid} {summary}", f"https://osv.dev/vulnerability/{vid}",
                           f"{summary}\n{details}\nAffected: {', '.join(pkgs[:6])}. Ecosystem: {eco}.",
                           klass=classify(summary + " " + details), severity=sev, protocol=eco,
                           fix=" ".join(dict.fromkeys(fixes))[:600], tags=[eco, "advisory"] + [str(a) for a in v.get("aliases", [])[:4]],
                           date=str(v.get("published", ""))[:10])
                n += 1
                if cap and n >= cap:
                    break
        log(f"  osv/{eco}: {n} record(s)")


def src_payloads(opts: Dict[str, Any], log: Callable[[str], None]) -> Iterable[Dict[str, Any]]:
    repo = "swisskyrepo/PayloadsAllTheThings"
    listing = github_json(f"https://api.github.com/repos/{repo}/contents/")
    for item in listing:
        if item.get("type") != "dir" or item["name"].startswith((".", "_")):
            continue
        name = item["name"]
        try:
            text = http_text(f"https://raw.githubusercontent.com/{repo}/master/{urllib.parse.quote(name)}/README.md")
        except IngestError:
            continue
        yield _row("payloads", "web", name, f"https://github.com/{repo}/tree/master/{urllib.parse.quote(name)}", text,
                   klass=classify(name, default=re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")),
                   tags=["technique", "payloads", "reference"])


class Source:
    def __init__(self, name: str, domain: str, license_: str, desc: str, fn: Callable[..., Iterable[Dict[str, Any]]],
                 default: bool = True):
        self.name, self.domain, self.license, self.desc, self.fn, self.default = name, domain, license_, desc, fn, default


SOURCES: Dict[str, Source] = {s.name: s for s in [
    Source("defihacklabs", "web3", "Apache-2.0", "875+ real DeFi exploits with dates, losses, root-cause class, PoC links", src_defihacklabs),
    Source("web3-vulns", "web3", "MIT", "Smart-contract vulnerability class references (root cause, exploit, mitigation)", src_web3_vulns),
    Source("c4", "web3", "public contest reports", "Code4rena High/Medium findings, newest contests first (--limit N contests, default 40)", src_c4),
    Source("hackerone", "web", "community list of public disclosures", "~15k disclosed HackerOne reports: program, weakness, bounty", src_hackerone),
    Source("payloads", "web", "MIT", "PayloadsAllTheThings: per-class attack techniques and payloads", src_payloads),
    Source("cisa-kev", "web+binary", "public domain (US gov)", "Vulnerabilities exploited in the wild", src_cisa_kev),
    Source("exploitdb", "web+binary", "GPL-2.0 database, titles only", "Exploit-DB titles, platforms, CVE codes", src_exploitdb),
    Source("osv", "binary+web", "CC-BY-4.0 (OSV)", "Advisories with fix commits; default ecosystem OSS-Fuzz (native C/C++ bugs). "
           "--osv-ecosystem crates.io,Go,npm,PyPI,Maven,...", src_osv),
]}


# ---------------------------------------------------------------- run

def last_ingest(ix: Any, name: str) -> Optional[Dict[str, Any]]:
    r = ix.con.execute("SELECT v FROM meta WHERE k=?", (f"ingest:{name}",)).fetchone()
    return json.loads(r["v"]) if r else None


def ingest(ix: Any, names: List[str], opts: Dict[str, Any], log: Callable[[str], None],
           refresh: bool = False) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for name in names:
        src = SOURCES[name]
        prev = last_ingest(ix, name)
        if prev and not refresh and time.time() - float(prev.get("time", 0)) < FRESH_DAYS * 86400:
            summary[name] = {"rows": prev.get("rows", 0), "skipped": "fresh (ingested within %d days; --refresh to redo)" % FRESH_DAYS}
            log(f"{name}: fresh, skipped")
            continue
        log(f"{name}: fetching ({src.desc})")
        started = time.time()
        try:
            rows = list(src.fn(opts, log))
        except (IngestError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            summary[name] = {"rows": 0, "error": str(exc)}
            log(f"{name}: FAILED: {exc}")
            continue
        if not rows:
            summary[name] = {"rows": 0, "error": "source returned no rows (format changed, or nothing matched)"}
            log(f"{name}: no rows; leaving any earlier data in place")
            continue
        n = ix.replace_precedents(name, rows)
        ix.con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                       (f"ingest:{name}", json.dumps({"time": time.time(), "rows": n, "license": src.license})))
        summary[name] = {"rows": n, "seconds": round(time.time() - started, 1)}
        log(f"{name}: {n} row(s) in {summary[name]['seconds']}s")
    return summary
