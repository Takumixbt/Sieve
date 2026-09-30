"""`sieve kb ...` — search, add, use, prime, write back."""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from . import kb_net, kb_store, repo_root, util, vectors, yamlish
from .config import Config, load_config
from .state import Engagement


# ------------------------------------------------------------------ plumbing

def _ctx() -> "tuple[Config, kb_store.Index, str]":
    eng = Engagement.find()
    cfg = load_config(eng.root if eng else None)
    ix = kb_store.Index(cfg.path("kb.index"))
    vault = cfg.path("kb.vault")
    os.makedirs(vault, exist_ok=True)
    return cfg, ix, vault


def seed_dir() -> str:
    return os.path.join(repo_root(), "kb", "seed", "cards")


def _vector_pseudo_cards() -> List["tuple[Dict[str, Any], str]"]:
    """Vector cards are searchable knowledge too: index them as `seed` entries."""
    out = []
    for c in vectors.load_all():
        klass = c["group"].lower()
        meta = {"id": f"VEC-{c['id']}", "title": c["title"], "source": "seed", "source_ref": c["_src"],
                "domain": {"web3": "web3", "web": "web", "binary": "binary"}.get(c["pack"], c["pack"]),
                "class": klass, "vector": c["id"], "severity": c.get("sev", ""), "status": "seed",
                "tell": c.get("tell", "").strip("`"), "tags": [klass, c["pack"]]}
        body = "\n".join(f"{k}: {c[k]}" for k in ("signal", "attack", "proof", "fp", "sev", "chain", "kb")
                         if c.get(k))
        out.append((meta, body))
    return out


def _reindex(cfg: Config, ix: kb_store.Index, vault: str) -> int:
    return ix.reindex([vault, seed_dir()], extra=_vector_pseudo_cards())


def _ensure_index(cfg: Config, ix: kb_store.Index, vault: str) -> None:
    if ix.stats()["cards"] == 0:
        _reindex(cfg, ix, vault)


def _print_hit(h: Dict[str, Any], origin: str, n: int) -> None:
    sev = (h.get("severity") or "?")[:8]
    ref = h.get("ref") or h.get("id")
    print(f"{n:>2}. [{origin}] {h.get('title', '')}  ({sev}{', ' + h['firm'] if h.get('firm') else ''})")
    print(f"      ref: {ref}" + (f"   {h['url']}" if h.get("url") else ""))
    if h.get("fix"):
        print(f"      fix: {h['fix'][:160]}")
    body = re.sub(r"\s+", " ", str(h.get("body", ""))).strip()
    if body:
        print(f"      {body[:220]}{'…' if len(body) > 220 else ''}")


def search_all(cfg: Config, ix: kb_store.Index, query: str, domain: Optional[str], klass: Optional[str],
               limit: int, online: bool, impact: Optional[List[str]] = None,
               offline: bool = False) -> Dict[str, Any]:
    res: Dict[str, Any] = {"local": ix.search(query, domain=domain, klass=klass, limit=limit),
                           "online": [], "errors": []}
    if online:
        broker = kb_net.Broker(ix, offline=offline)
        try:
            if domain in (None, "web3"):
                res["online"] += kb_net.solodit_search(broker, cfg, query, impact=impact)[:limit]
            elif cfg.get("kb.sources.nvd.enabled", False):
                res["online"] += kb_net.nvd_search(broker, cfg, query, limit=limit)
            else:
                res["errors"].append("no online index for this domain: WebSearch/WebFetch the disclosed "
                                     "report, then `sieve kb add`")
        except kb_net.KBError as exc:
            res["errors"].append(str(exc))
    return res


# ------------------------------------------------------------------ commands

def cmd_index(args: argparse.Namespace) -> int:
    cfg, ix, vault = _ctx()
    n = _reindex(cfg, ix, vault)
    print(f"indexed {n} card(s) — vault {vault}")
    print(json.dumps(ix.stats(), indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    cfg, ix, vault = _ctx()
    _ensure_index(cfg, ix, vault)
    res = search_all(cfg, ix, args.query, args.domain, args.klass, args.limit, args.online,
                     impact=args.impact.split(",") if args.impact else None, offline=args.offline)
    if args.json:
        print(json.dumps(res, indent=2, default=str))
        return 0
    n = 0
    for h in res["local"]:
        n += 1
        _print_hit({**h, "ref": h["id"]}, f"local/{h['status']}", n)
    for h in res["online"]:
        n += 1
        _print_hit(h, h["source"], n)
    if n == 0:
        print("no hits")
    for e in res["errors"]:
        print(f"note: {e}")
    if res["online"]:
        print("\nUse a precedent that helps a finding:  sieve kb use <ref> --finding F-001")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    cfg, ix, _vault = _ctx()
    c = ix.get(args.ref)
    if c:
        print(json.dumps({k: v for k, v in c.items() if k != "body"}, indent=2))
        print("\n" + c["body"])
        return 0
    h = kb_net.get_hit(ix, args.ref)
    if h:
        print(json.dumps({k: v for k, v in h.items() if k != "body"}, indent=2))
        print("\n" + h.get("body", ""))
        return 0
    raise SystemExit(f"sieve kb get: nothing known as {args.ref!r}")


def cmd_osv(args: argparse.Namespace) -> int:
    cfg, ix, _vault = _ctx()
    hits = kb_net.osv_query(kb_net.Broker(ix, offline=args.offline), cfg, args.package, args.ecosystem, args.version)
    if args.json:
        print(json.dumps(hits, indent=2))
    else:
        for i, h in enumerate(hits[: args.limit], 1):
            _print_hit(h, "osv", i)
        if not hits:
            print("no known vulnerabilities for that package/version")
    return 0


def _hit_to_card(h: Dict[str, Any], domain: str, klass: str, eng: Optional[Engagement],
                 finding: str) -> "tuple[Dict[str, Any], str]":
    meta: Dict[str, Any] = {
        "title": h["title"], "source": h["source"], "source_ref": h.get("url") or h["ref"],
        "domain": domain, "class": klass, "severity": h.get("severity", ""), "status": "curated",
        "firm": h.get("firm", ""), "tags": h.get("tags", []), "protocol_type": h.get("protocol", ""),
        "last_used": util.today(),
    }
    if eng:
        meta["used_in"] = [f"{eng.load()['id']}:{finding}"] if finding else [eng.load()["id"]]
    body = f"# {h['title']}\n\n{h.get('body', '').strip()}\n"
    return meta, body


def cmd_use(args: argparse.Namespace) -> int:
    cfg, ix, vault = _ctx()
    eng = Engagement.find()
    wb = cfg.get("kb.writeback", {}) or {}
    h = kb_net.get_hit(ix, args.ref)
    if h is None:
        c = ix.get(args.ref)
        if c is None:
            raise SystemExit(f"sieve kb use: {args.ref!r} is not a known online hit or card "
                             "(run `sieve kb search --online` first)")
        h = {"ref": c["id"], "source": c["source"], "title": c["title"], "severity": c["severity"],
             "body": c["body"], "firm": c["firm"], "tags": c["tags"].split(), "url": c["source_ref"],
             "protocol": c["protocol_type"]}
    if not wb.get("curated", True):
        print("curated write-back disabled in sieve.yaml; nothing written")
        return 0
    domain = args.domain or (eng.load()["packs"][0] if eng else "web3")
    meta, body = _hit_to_card(h, domain, args.klass or "unclassified", eng, args.finding or "")
    path, action = kb_store.write_card(vault, meta, body, sanitize_on=bool(wb.get("sanitize", True)))
    m, b = kb_store.read_card(path)
    ix.upsert(m, b, path)
    print(f"{action} curated card: {path}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    cfg, ix, vault = _ctx()
    eng = Engagement.find()
    wb = cfg.get("kb.writeback", {}) or {}
    if args.from_json:
        data = json.load(open(args.from_json, encoding="utf-8")) if args.from_json != "-" else json.load(__import__("sys").stdin)
    else:
        data = {"title": args.title, "domain": args.domain, "class": args.klass, "source_ref": args.url,
                "severity": args.severity, "stack": args.stack, "tell": args.tell,
                "body": args.body or "", "tags": [t for t in (args.tags or "").split(",") if t]}
    for req in ("title", "domain", "class", "source_ref"):
        if not data.get(req):
            raise SystemExit(f"sieve kb add: missing {req!r}")
    meta = {k: data[k] for k in ("title", "domain", "class", "severity", "stack", "tell", "tags", "vector",
                                 "protocol_type", "firm") if data.get(k)}
    meta["source"] = data.get("source", "web")
    meta["source_ref"] = data["source_ref"]
    meta["status"] = "curated" if args.used_in else "raw"
    if args.used_in and eng:
        meta["used_in"] = [f"{eng.load()['id']}:{args.used_in}"]
    body = f"# {data['title']}\n\n{data.get('body', '').strip()}\n"
    path, action = kb_store.write_card(vault, meta, body, sanitize_on=bool(wb.get("sanitize", True)))
    m, b = kb_store.read_card(path)
    ix.upsert(m, b, path)
    print(f"{action}: {path}")
    return 0


def _sections(body: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    cur: Optional[str] = None
    buf: List[str] = []
    for ln in body.split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m:
            if cur is not None:
                out[cur.lower()] = "\n".join(buf).strip()
            cur, buf = m.group(1), []
        elif cur is not None:
            buf.append(ln)
    if cur is not None:
        out[cur.lower()] = "\n".join(buf).strip()
    return out


def cmd_writeback(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    cfg, ix, vault = _ctx()
    wb = cfg.get("kb.writeback", {}) or {}
    if not wb.get("confirmed", True):
        print("confirmed write-back disabled in sieve.yaml")
        return 0
    minc = int(wb.get("min_confidence", 75))
    eid = eng.load()["id"]
    written = skipped = 0
    from . import validate
    for f in sorted(glob.glob(eng.path("findings", "F-*.md"))):
        meta, body = yamlish.split_frontmatter(util.read_text(f))
        fid = meta.get("id", os.path.basename(f)[:-3])
        # The tier is computed from sealed receipts — a `status:` line an agent edited into the file is not trusted.
        tier = validate.assess(eng, fid)
        if tier["tier"] == "rejected":
            _false_positive_lesson(eng, cfg, ix, vault, meta, body, tier)
            skipped += 1
            continue
        if meta.get("kind", "FINDING") != "FINDING" or tier["tier"] not in ("confirmed", "trace-verified"):
            skipped += 1
            continue
        meta["confidence"] = tier.get("confidence") if tier.get("confidence") is not None else meta.get("confidence")
        if int(meta.get("confidence") or 0) < minc:
            skipped += 1
            print(f"skip {fid}: confidence {meta.get('confidence')} < {minc}")
            continue
        sec = _sections(body)
        domain = meta.get("pack", eng.load()["packs"][0])
        card_meta: Dict[str, Any] = {
            "title": meta.get("title", fid), "source": "own", "source_ref": f"{eid}:{fid}", "domain": domain,
            "class": meta.get("class", "unclassified"), "vector": meta.get("vector", ""),
            "severity": meta.get("severity", ""), "stack": meta.get("stack", ""), "tell": meta.get("tell", ""),
            "status": "confirmed" if tier["tier"] == "confirmed" else "curated",
            "confidence": meta.get("confidence"), "used_in": [f"{eid}:{fid}"],
            "tags": [meta.get("class", ""), domain], "last_used": util.today(),
        }
        parts = [f"# {meta.get('title', fid)}", ""]
        for h in ("Root cause", "Attack path", "Remediation"):
            if sec.get(h.lower()):
                parts += [f"## {h}", sec[h.lower()], ""]
        path, action = kb_store.write_card(vault, card_meta, "\n".join(parts), sanitize_on=bool(wb.get("sanitize", True)))
        m, b = kb_store.read_card(path)
        ix.upsert(m, b, path)
        written += 1
        print(f"{action}: {path}")
    lessons = _dead_end_lessons(eng, cfg, ix, vault)
    print(f"write-back: {written} confirmed card(s) written, {skipped} skipped, {lessons} dead-end lesson(s) recorded")
    return 0


LESSON_KINDS = ("false-positive", "miss", "revived", "technique", "dead-end")


def _lesson_card(kind: str, title: str, domain: str, body: str, source_ref: str, eng: Optional[Engagement],
                 stack: str = "") -> "tuple[Dict[str, Any], str]":
    meta: Dict[str, Any] = {"title": title, "source": "own", "source_ref": source_ref, "domain": domain,
                            "class": "lesson", "status": "curated", "stack": stack,
                            "tags": ["lesson", kind, domain], "last_used": util.today()}
    if eng:
        meta["used_in"] = [eng.load()["id"]]
    return meta, f"# {title}\n\n**kind:** {kind}\n\n{body.strip()}\n"


def cmd_lesson(args: argparse.Namespace) -> int:
    """A card for something the engagement taught you — the ledger `sieve kb prime` reads next time."""
    cfg, ix, vault = _ctx()
    eng = Engagement.find()
    wb = cfg.get("kb.writeback", {}) or {}
    domain = args.domain or (eng.load()["packs"][0] if eng else "web3")
    meta, body = _lesson_card(args.kind, args.title, domain, args.body, args.ref or (eng.load()["id"] if eng else "manual"),
                              eng, args.stack or "")
    path, action = kb_store.write_card(vault, meta, body, sanitize_on=bool(wb.get("sanitize", True)))
    m, b = kb_store.read_card(path)
    ix.upsert(m, b, path)
    print(f"{action} lesson card: {path}")
    return 0


def _false_positive_lesson(eng: Engagement, cfg: Config, ix: kb_store.Index, vault: str, meta: Dict[str, Any],
                           body: str, tier: Dict[str, Any]) -> None:
    """A candidate the verifiers killed is the cheapest lesson there is: what looked like a bug, and the guard or
    missing harm that showed it was not. Written so `kb prime` shows it before the next hunt in the same class."""
    wb = cfg.get("kb.writeback", {}) or {}
    if not wb.get("lessons", True):
        return
    from . import validate
    j = validate.load_judged(eng).get(meta.get("id", "")) or {}
    why = "\n".join(f"- {v['verifier']}: {v.get('reason')}" for v in j.get("votes", []))
    domain = meta.get("pack") or eng.load()["packs"][0]
    text = (f"Candidate `{meta.get('component')}` ({meta.get('class')}) was raised as a finding and rejected at the gates.\n\n"
            f"**Why it looked real:** {meta.get('title')}\n\n**Why it was not:**\n{why or '(no reason recorded)'}\n")
    m, t = _lesson_card("false-positive", f"False positive: {meta.get('class')} in {meta.get('component')}", domain, text,
                        f"{eng.load()['id']}:{meta.get('id')}", eng)
    path, _ = kb_store.write_card(vault, m, t, sanitize_on=bool(wb.get("sanitize", True)))
    mm, bb = kb_store.read_card(path)
    ix.upsert(mm, bb, path)


def _dead_end_lessons(eng: Engagement, cfg: Config, ix: kb_store.Index, vault: str) -> int:
    """Killed hypotheses are data: every frontier row closed `dead` becomes a lesson card carrying
    the ladder rungs that were tried, so the next engagement doesn't re-walk the same road."""
    from . import frontier
    wb = cfg.get("kb.writeback", {}) or {}
    if not wb.get("lessons", True):
        return 0
    eid = eng.load()["id"]
    n = 0
    for r in frontier.load(eng):
        if r["status"] != "dead":
            continue
        att = frontier.attempts(eng, r["id"])
        body = f"Component `{r['component']}`, lens `{r['lens']}`, pack `{r['pack']}`.\n\n" + \
               "\n".join(f"- `{a['rung']}`: {a['note']}" for a in att)
        meta, text = _lesson_card("dead-end", f"Dead end: {r['component']} ({r['lens']})", r["pack"] or
                                  eng.load()["packs"][0], body, f"{eid}:{r['id']}", eng)
        path, _ = kb_store.write_card(vault, meta, text, sanitize_on=bool(wb.get("sanitize", True)))
        m, b = kb_store.read_card(path)
        ix.upsert(m, b, path)
        n += 1
    return n


def cmd_prime(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    cfg, ix, vault = _ctx()
    _ensure_index(cfg, ix, vault)
    st = eng.load()
    lines = ["# Precedents", "",
             "_Leads, never findings: a precedent raises priority, the gate still decides. "
             "Generated by `sieve kb prime`._", ""]
    budget = args.max_online
    total_local = total_online = 0
    for pack in st["packs"]:
        cards = vectors.load_pack(pack)
        groups: Dict[str, List[Dict[str, str]]] = {}
        for c in cards:
            groups.setdefault(c["group"], []).append(c)
        lines.append(f"## {pack}")
        for g, cs in groups.items():
            query = " ".join(c.get("kb", "") for c in cs[:2])
            hits = ix.search(query, domain=pack, limit=3)
            hits = [h for h in hits if not h["id"].startswith("VEC-")]
            online: List[Dict[str, Any]] = []
            solodit_key = os.environ.get(str(cfg.get("kb.sources.solodit.api_key_env", "CYFRIN_API_KEY")), "")
            if budget > 0 and pack == "web3" and not args.offline and solodit_key:
                try:
                    online = kb_net.solodit_search(kb_net.Broker(ix), cfg, query, impact=["HIGH", "MEDIUM"])[:3]
                    budget -= 1
                except kb_net.KBError as exc:
                    lines.append(f"_(online lookup skipped: {exc})_")
                    budget = 0
            if not hits and not online:
                continue
            lines.append(f"### {g}")
            for h in hits:
                total_local += 1
                extra = ""
                if h["status"] == "precedent":
                    extra = (f" {h['source_ref']}" if h.get("source_ref") else "") + (f" (fix: {h['fix'][:90]})" if h.get("fix") else "")
                lines.append(f"- [{h['status']}] {h['title']} — `{h['id']}`{extra}")
            for h in online:
                total_online += 1
                lines.append(f"- [{h['source']}] {h['title']} ({h['severity'] or '?'}"
                             f"{', ' + h['firm'] if h['firm'] else ''}) — `{h['ref']}` {h['url']}")
        lines.append("")
    lessons = ix.con.execute("SELECT id, title, tags, stack FROM cards WHERE class='lesson' AND domain IN (%s) "
                             "ORDER BY updated DESC LIMIT 12" % ",".join("?" * len(st["packs"])),
                             list(st["packs"])).fetchall()
    if lessons:
        lines += ["## Your own lessons", "",
                  "_What earlier engagements taught you — read before hunting, not after (hypothesis-craft.md §4)._", ""]
        lines += [f"- {r['title']} — `{r['id']}`" + (f" ({r['stack']})" if r["stack"] else "") for r in lessons]
        lines.append("")
    util.atomic_write(eng.path("xray", "precedents.md"), "\n".join(lines) + "\n")
    print(f"wrote {eng.path('xray', 'precedents.md')} ({total_local} local, {total_online} online precedents, "
          f"{len(lessons)} lesson(s); {args.max_online - budget} online query(ies) used)")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    cfg, ix, vault = _ctx()
    _ensure_index(cfg, ix, vault)
    print(json.dumps(ix.stats(), indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg, ix, vault = _ctx()
    print(f"vault: {vault}\nindex: {ix.path}  fts5={ix.fts}")
    for name in ("solodit", "osv", "nvd"):
        sc = cfg.source(name)
        env = sc.get("api_key_env")
        have = bool(env and os.environ.get(str(env)))
        print(f"{name:<8} enabled={sc.get('enabled')}  key={'set' if have else ('n/a' if not env else 'MISSING (' + str(env) + ')')}"
              f"  limit={sc.get('rate_limit')}")
    if args.live:
        broker = kb_net.Broker(ix)
        try:
            hits = kb_net.solodit_search(broker, cfg, "reentrancy", impact=["HIGH"], page_size=2)
            print(f"solodit live: OK, {len(hits)} hit(s); first: {hits[0]['title'] if hits else '-'}")
            if hits:
                print("normalised sample:", json.dumps({k: (v[:60] if isinstance(v, str) else v)
                                                        for k, v in hits[0].items()}, indent=2))
        except kb_net.KBError as exc:
            print(f"solodit live: FAILED — {exc}")
            return 1
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    from . import kb_ingest
    cfg, ix, _vault = _ctx()
    print(f"{'SOURCE':<14} {'DOMAIN':<11} {'ROWS':>7}  {'LAST INGEST':<11} LICENSE / WHAT")
    for name, src in kb_ingest.SOURCES.items():
        prev = kb_ingest.last_ingest(ix, name)
        when = time.strftime("%Y-%m-%d", time.localtime(prev["time"])) if prev else "never"
        print(f"{name:<14} {src.domain:<11} {(prev or {}).get('rows', 0):>7}  {when:<11} {src.license}: {src.desc}")
    key = "set" if os.environ.get(str(cfg.get("kb.sources.solodit.api_key_env", "CYFRIN_API_KEY"))) else "not set (optional)"
    print(f"\nsolodit (online, optional): API key {key}. Every source above needs no key. "
          f"{ix.stats().get('precedents', 0)} precedent row(s) indexed locally.")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from . import kb_ingest
    cfg, ix, _vault = _ctx()
    if args.source in (None, "all"):
        names = [n for n, s in kb_ingest.SOURCES.items() if s.default]
    else:
        names = [n.strip() for n in args.source.split(",") if n.strip()]
        bad = [n for n in names if n not in kb_ingest.SOURCES]
        if bad:
            raise SystemExit(f"sieve kb ingest: unknown source(s) {', '.join(bad)}; known: {', '.join(kb_ingest.SOURCES)}")
    opts = {"limit": args.limit, "osv_ecosystem": args.osv_ecosystem}
    summary = kb_ingest.ingest(ix, names, opts, print, refresh=args.refresh)
    failed = [n for n, s in summary.items() if s.get("error")]
    total = sum(int(s.get("rows", 0)) for s in summary.values())
    print(f"\ningest complete: {total} row(s) across {len(summary)} source(s)" + (f"; failed: {', '.join(failed)}" if failed else ""))
    print(json.dumps(ix.stats().get("precedents_by_source", {})))
    return 1 if failed and len(failed) == len(summary) else 0


def register(sub: Any) -> None:
    p = sub.add_parser("kb", help="knowledge base: search, add, use, prime, write back")
    ks = p.add_subparsers(dest="kcmd", required=True)

    q = ks.add_parser("sources", help="the public precedent sources, what each holds, when it was last ingested")
    q.set_defaults(func=cmd_sources)

    q = ks.add_parser("ingest", help="pull public precedents (no API key needed) into the local index")
    q.add_argument("--source", help="comma list, or `all` (default). See `sieve kb sources`.")
    q.add_argument("--limit", type=int, help="c4: contests to read (default 40); osv: records per ecosystem")
    q.add_argument("--osv-ecosystem", help="comma list for the osv source, e.g. OSS-Fuzz,crates.io,Go,npm,PyPI,Maven")
    q.add_argument("--refresh", action="store_true", help="re-fetch sources ingested within the last 7 days")
    q.set_defaults(func=cmd_ingest)

    q = ks.add_parser("index", help="(re)build the local index from the vault, seed cards and vector cards")
    q.set_defaults(func=cmd_index)

    q = ks.add_parser("search", help="local search; --online adds Solodit (web3) through the rate-limited broker")
    q.add_argument("query")
    q.add_argument("--domain", choices=["web3", "web", "binary"])
    q.add_argument("--class", dest="klass")
    q.add_argument("--limit", type=int, default=8)
    q.add_argument("--online", action="store_true")
    q.add_argument("--offline", action="store_true")
    q.add_argument("--impact", help="comma list, e.g. HIGH,MEDIUM")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_search)

    q = ks.add_parser("get", help="show a card or a cached online hit")
    q.add_argument("ref")
    q.set_defaults(func=cmd_get)

    q = ks.add_parser("osv", help="known vulnerabilities for a package (OSV, no key needed)")
    q.add_argument("--package", required=True)
    q.add_argument("--ecosystem", required=True, help="npm, PyPI, Go, Maven, crates.io, RubyGems, Packagist, ...")
    q.add_argument("--version")
    q.add_argument("--limit", type=int, default=10)
    q.add_argument("--offline", action="store_true")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_osv)

    q = ks.add_parser("use", help="promote a fetched precedent that helped into a curated card")
    q.add_argument("ref")
    q.add_argument("--finding")
    q.add_argument("--domain", choices=["web3", "web", "binary"])
    q.add_argument("--class", dest="klass")
    q.set_defaults(func=cmd_use)

    q = ks.add_parser("add", help="add a precedent you found on the web (report, writeup, CVE)")
    q.add_argument("--from-json")
    q.add_argument("--title")
    q.add_argument("--domain", choices=["web3", "web", "binary"])
    q.add_argument("--class", dest="klass")
    q.add_argument("--url")
    q.add_argument("--severity")
    q.add_argument("--stack")
    q.add_argument("--tell")
    q.add_argument("--tags")
    q.add_argument("--body")
    q.add_argument("--used-in", help="finding id it helped with (marks the card curated)")
    q.set_defaults(func=cmd_add)

    q = ks.add_parser("lesson", help="record something an engagement taught you (read back by `kb prime`)")
    q.add_argument("--kind", required=True, choices=list(LESSON_KINDS))
    q.add_argument("--title", required=True)
    q.add_argument("--body", required=True, help="the wrong assumption / the lens that would have caught it / the move that paid")
    q.add_argument("--domain", choices=["web3", "web", "binary"])
    q.add_argument("--stack")
    q.add_argument("--ref", help="engagement or finding this came from")
    q.set_defaults(func=cmd_lesson)

    q = ks.add_parser("prime", help="build .sieve/xray/precedents.md for this engagement")
    q.add_argument("--max-online", type=int, default=8)
    q.add_argument("--offline", action="store_true")
    q.set_defaults(func=cmd_prime)

    q = ks.add_parser("writeback", help="write confirmed findings back as cards")
    q.set_defaults(func=cmd_writeback)

    q = ks.add_parser("stats")
    q.set_defaults(func=cmd_stats)

    q = ks.add_parser("doctor", help="check keys, limits and (with --live) the real API shape")
    q.add_argument("--live", action="store_true")
    q.set_defaults(func=cmd_doctor)
