"""Knowledge-base storage: markdown cards with YAML frontmatter, a SQLite FTS5 index, and the
sanitizer that stops secrets and personal data from ever reaching a card.

Cards are plain files. Obsidian (or any editor) can open the vault folder, but nothing here
depends on it. The index is a cache: `reindex` rebuilds it from the files at any time.
"""
from __future__ import annotations

import glob
import hashlib
import os
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import util, yamlish

DOMAIN_CODE = {"web3": "W3", "web": "WEB", "binary": "BIN"}
STATUS_RANK = {"confirmed": 4, "curated": 3, "seed": 2, "raw": 1}
CARD_ORDER = ["id", "title", "source", "source_ref", "domain", "class", "vector", "severity",
              "protocol_type", "stack", "tell", "status", "confidence", "firm", "tags",
              "first_seen", "last_used", "used_in", "redactions"]
STOP = set("the a an of to in on for and or is are be by with from this that it as at not no".split())

# ---------------------------------------------------------------- sanitizer

_SECRET_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("private-key-header", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("gcp-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe-key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}")),
    ("wallet-secret", re.compile(r"(?i)(?:priv(?:ate)?[ _-]?key|secret|mnemonic|seed)\D{0,20}(?:0x)?[0-9a-f]{64}\b")),
    ("generic-secret", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9/_+=\-]{16,}")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("private-ip", re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|"
                              r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")),
    ("home-path", re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/")),
]


def sanitize(text: str) -> Tuple[str, List[str]]:
    """Replace secrets/PII with [REDACTED:kind]. Returns (clean_text, kinds_found)."""
    kinds: List[str] = []
    for kind, rx in _SECRET_PATTERNS:
        def _sub(_m: "re.Match[str]", k: str = kind) -> str:
            kinds.append(k)
            return f"[REDACTED:{k}]"
        text = rx.sub(_sub, text)
    return text, kinds


def scan_secrets(text: str) -> List[str]:
    return sorted({kind for kind, rx in _SECRET_PATTERNS if rx.search(text)})


# ---------------------------------------------------------------- cards

def card_id(domain: str, source: str, source_ref: str, title: str) -> str:
    h = hashlib.sha1(f"{source}|{source_ref}|{title.strip().lower()}".encode()).hexdigest()[:8]
    return f"KB-{DOMAIN_CODE.get(domain, 'GEN')}-{h}"


def card_path(vault: str, meta: Dict[str, Any]) -> str:
    klass = util.slug(str(meta.get("class") or "unclassified"), 40)
    name = util.slug(str(meta.get("title") or meta["id"]), 48)
    return os.path.join(vault, str(meta.get("domain") or "general"), klass, f"{name}-{meta['id'][-8:]}.md")


def _ordered(meta: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: meta[k] for k in CARD_ORDER if k in meta and meta[k] not in (None, "", [])}
    for k, v in meta.items():
        if k not in out and v not in (None, "", []):
            out[k] = v
    return out


def read_card(path: str) -> Tuple[Dict[str, Any], str]:
    return yamlish.split_frontmatter(util.read_text(path))


def write_card(vault: str, meta: Dict[str, Any], body: str, sanitize_on: bool = True) -> Tuple[str, str]:
    """Create or merge a card. Never downgrades status, never drops `used_in`. Returns (path, action)."""
    meta = dict(meta)
    if sanitize_on:
        red = 0
        for key in ("title", "tell", "source_ref"):
            if isinstance(meta.get(key), str):
                meta[key], k = sanitize(meta[key])
                red += len(k)
        body, k = sanitize(body)
        red += len(k)
        if red:
            meta["redactions"] = int(meta.get("redactions", 0)) + red
    meta.setdefault("domain", "general")
    meta.setdefault("status", "raw")
    meta.setdefault("first_seen", util.today())
    if not meta.get("id"):
        meta["id"] = card_id(meta["domain"], str(meta.get("source", "own")),
                             str(meta.get("source_ref", "")), str(meta.get("title", "")))
    path = card_path(vault, meta)
    action = "created"
    if os.path.isfile(path):
        old, old_body = read_card(path)
        merged = dict(old)
        merged.update({k: v for k, v in meta.items() if v not in (None, "", [])})
        if STATUS_RANK.get(str(old.get("status")), 0) > STATUS_RANK.get(str(meta.get("status")), 0):
            merged["status"] = old["status"]
        used = list(old.get("used_in") or [])
        for u in (meta.get("used_in") or []):
            if u not in used:
                used.append(u)
        if used:
            merged["used_in"] = used
        merged["first_seen"] = old.get("first_seen", meta["first_seen"])
        if merged == old and body.strip() == old_body.strip():
            return path, "unchanged"
        meta, body, action = merged, (body if body.strip() else old_body), "updated"
    util.atomic_write(path, yamlish.join_frontmatter(_ordered(meta), body))
    return path, action


def iter_card_files(*dirs: str) -> Iterable[str]:
    for d in dirs:
        if d and os.path.isdir(d):
            for p in sorted(glob.glob(os.path.join(d, "**", "*.md"), recursive=True)):
                yield p


# ---------------------------------------------------------------- index

class Index:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS cards(id TEXT PRIMARY KEY, path TEXT, source TEXT, source_ref TEXT,
        domain TEXT, class TEXT, vector TEXT, severity TEXT, title TEXT, protocol_type TEXT, stack TEXT,
        tell TEXT, status TEXT, confidence INTEGER, firm TEXT, tags TEXT, body TEXT, updated TEXT);
    CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, source TEXT, fetched REAL, ttl REAL, payload TEXT);
    CREATE TABLE IF NOT EXISTS ratelimit(source TEXT, ts REAL);
    CREATE INDEX IF NOT EXISTS rl_idx ON ratelimit(source, ts);
    CREATE TABLE IF NOT EXISTS hits(ref TEXT PRIMARY KEY, source TEXT, payload TEXT, seen REAL);
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    """

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self.con = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA busy_timeout=30000")
        self.con.executescript(self.SCHEMA)
        self.fts = True
        try:
            self.con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5("
                             "id UNINDEXED, title, class, tags, stack, body, tokenize='porter unicode61')")
        except sqlite3.OperationalError:
            self.fts = False

    def close(self) -> None:
        self.con.close()

    # ------------------------------------------------------------ writes
    def upsert(self, meta: Dict[str, Any], body: str, path: str = "") -> None:
        tags = " ".join(str(t) for t in (meta.get("tags") or []))
        row = (meta["id"], path, meta.get("source", ""), meta.get("source_ref", ""), meta.get("domain", ""),
               meta.get("class", ""), meta.get("vector", ""), meta.get("severity", ""), meta.get("title", ""),
               meta.get("protocol_type", ""), meta.get("stack", ""), meta.get("tell", ""),
               meta.get("status", "raw"), int(meta.get("confidence") or 0), meta.get("firm", ""), tags, body,
               util.now_iso())
        self.con.execute("INSERT OR REPLACE INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
        if self.fts:
            self.con.execute("DELETE FROM cards_fts WHERE id=?", (meta["id"],))
            self.con.execute("INSERT INTO cards_fts(id,title,class,tags,stack,body) VALUES (?,?,?,?,?,?)",
                             (meta["id"], meta.get("title", ""), meta.get("class", ""), tags,
                              meta.get("stack", ""), body))

    def reindex(self, dirs: List[str], extra: Optional[List[Tuple[Dict[str, Any], str]]] = None) -> int:
        self.con.execute("BEGIN")
        self.con.execute("DELETE FROM cards")
        if self.fts:
            self.con.execute("DELETE FROM cards_fts")
        n = 0
        for p in iter_card_files(*dirs):
            try:
                meta, body = read_card(p)
            except Exception:  # noqa: BLE001 — a bad card must not block indexing the rest
                continue
            if not meta.get("id"):
                continue
            self.upsert(meta, body, p)
            n += 1
        for meta, body in extra or []:
            self.upsert(meta, body, "")
            n += 1
        self.con.execute("COMMIT")
        return n

    # ------------------------------------------------------------ reads
    def get(self, cid: str) -> Optional[Dict[str, Any]]:
        r = self.con.execute("SELECT * FROM cards WHERE id=?", (cid,)).fetchone()
        return dict(r) if r else None

    def search(self, query: str, domain: Optional[str] = None, klass: Optional[str] = None,
               limit: int = 8, min_status: Optional[str] = None) -> List[Dict[str, Any]]:
        tokens = [t for t in re.findall(r"[A-Za-z0-9_]{2,}", query.lower()) if t not in STOP][:14]
        if not tokens:
            return []
        filt, args = [], []  # type: List[str], List[Any]
        if domain:
            filt.append("c.domain = ?")
            args.append(domain)
        if klass:
            filt.append("c.class = ?")
            args.append(klass)
        if min_status:
            ranks = [s for s, r in STATUS_RANK.items() if r >= STATUS_RANK[min_status]]
            filt.append("c.status IN (%s)" % ",".join("?" * len(ranks)))
            args.extend(ranks)
        where = (" AND " + " AND ".join(filt)) if filt else ""
        if self.fts:
            q = " OR ".join(f'"{t}"' for t in tokens)
            sql = ("SELECT c.*, bm25(cards_fts, 0.0, 6.0, 4.0, 3.0, 2.0, 1.0) AS score FROM cards_fts "
                   "JOIN cards c ON c.id = cards_fts.id WHERE cards_fts MATCH ?" + where +
                   " ORDER BY score LIMIT ?")
            rows = self.con.execute(sql, [q] + args + [limit * 3]).fetchall()
            hits = [dict(r) for r in rows]
            for h in hits:
                h["rank"] = -float(h.pop("score")) + STATUS_RANK.get(h["status"], 0) * 0.4
        else:
            like = " OR ".join("(lower(c.title) LIKE ? OR lower(c.body) LIKE ?)" for _ in tokens)
            params: List[Any] = []
            for t in tokens:
                params += [f"%{t}%", f"%{t}%"]
            rows = self.con.execute(f"SELECT c.* FROM cards c WHERE ({like}){where} LIMIT ?",
                                    params + args + [limit * 3]).fetchall()
            hits = [dict(r) for r in rows]
            for h in hits:
                blob = (h["title"] + " " + h["body"]).lower()
                h["rank"] = sum(blob.count(t) for t in tokens) + STATUS_RANK.get(h["status"], 0) * 0.4
        hits.sort(key=lambda h: -h["rank"])
        return hits[:limit]

    def stats(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"cards": self.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0],
                               "fts5": self.fts}
        for col in ("status", "domain", "source"):
            out[f"by_{col}"] = {r[0] or "?": r[1] for r in
                                self.con.execute(f"SELECT {col}, COUNT(*) FROM cards GROUP BY {col}")}
        out["cached_responses"] = self.con.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        return out
