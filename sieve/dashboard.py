"""Loopback dashboard for a running campaign: read-only, no dependencies, nothing leaves the machine.

`sieve campaign dashboard` serves one HTML page plus `/api/state` on 127.0.0.1 only (Host-header checked
against DNS rebinding, GET only, no file serving). The page polls the JSON every few seconds and draws the
node graph by layer, the frontier, the findings by tier and the event log. `--once` writes a static snapshot
(`.sieve/campaign/dashboard.html`) instead — the same page with the data embedded.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

from . import campaign as C
from . import frontier, util, validate
from .flow import next_action
from .state import Engagement


def _layers(nodes: List[Dict[str, Any]]) -> List[List[str]]:
    depth: Dict[str, int] = {}
    by = {n["id"]: n for n in nodes}

    def d(nid: str) -> int:
        if nid in depth:
            return depth[nid]
        deps = by[nid]["depends_on"]
        depth[nid] = 0 if not deps else 1 + max(d(x) for x in deps)
        return depth[nid]
    for n in nodes:
        d(n["id"])
    out: List[List[str]] = [[] for _ in range((max(depth.values()) if depth else 0) + 1)]
    for n in nodes:
        out[depth[n["id"]]].append(n["id"])
    return out


def snapshot(eng: Engagement) -> Dict[str, Any]:
    st = eng.load()
    head, detail = next_action(eng)
    snap: Dict[str, Any] = {
        "generated": util.now_iso(),
        "engagement": {"id": st["id"], "name": st["name"], "phase": st["phase"], "packs": st["packs"],
                       "pass": f"{st.get('pass_current', 0)}/{st.get('passes_planned', 1)}",
                       "elapsed_min": round(eng.elapsed_minutes(st), 1), "halt": st.get("halt_reason"),
                       "hook": st["counters"].get("blocks_total", 0)},
        "next": {"head": head, "detail": detail},
        "frontier": frontier.stats(eng),
        "frontier_kinds": {},
        "campaign": None, "findings": [], "events": [],
    }
    rows = frontier.load(eng)
    kinds: Dict[str, Dict[str, int]] = {}
    for r in rows:
        k = kinds.setdefault(r["kind"], {"open": 0, "closed": 0})
        k["open" if r["status"] in frontier.OPEN else "closed"] += 1
    snap["frontier_kinds"] = kinds
    if C.active(eng):
        try:
            _topo, nodes, cst = C.load(eng, allow_drift=True)
            sts = C.statuses(eng, nodes, cst)
            snap["campaign"] = {
                "profile": cst["profile"], "layers": _layers(nodes),
                "counts": {s: sum(1 for v in sts.values() if v == s) for s in set(sts.values())},
                "nodes": {n["id"]: {"spec": n["spec"], "kind": n["kind"], "status": sts[n["id"]], "deps": n["depends_on"],
                                    "attempts": cst["nodes"][n["id"]].get("attempts", 0), "error": cst["nodes"][n["id"]].get("error"),
                                    "note": cst["nodes"][n["id"]].get("note"), "started": cst["nodes"][n["id"]].get("started"),
                                    "finished": cst["nodes"][n["id"]].get("finished"), "description": n["description"],
                                    "outputs": [o["path"] for o in n["outputs"]]} for n in nodes}}
        except SystemExit as exc:
            snap["campaign"] = {"error": str(exc)}
        ev = os.path.join(C.cdir(eng), "events.jsonl")
        if os.path.isfile(ev):
            snap["events"] = [json.loads(x) for x in util.read_text(ev).split("\n")[-60:] if x.strip()][::-1]
    try:
        for a in validate.assess_all(eng):
            snap["findings"].append({k: a.get(k) for k in ("id", "kind", "severity", "tier", "title", "cites", "exec", "judged", "why")})
    except SystemExit:
        pass
    return snap


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sieve Campaign</title>
<style>
:root{--bg:#f6f7f9;--fg:#15181d;--mut:#5b6572;--card:#fff;--line:#dfe3e8;--ok:#1f9d55;--run:#2b6fdd;--rdy:#b7791f;--fail:#d64545;--pend:#8a94a3;--stale:#c05621;--acc:#7c3aed}
@media (prefers-color-scheme:dark){:root{--bg:#0f1216;--fg:#e6e9ee;--mut:#98a2b3;--card:#171b21;--line:#2a313a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:16px 20px;border-bottom:1px solid var(--line);background:var(--card);display:flex;flex-wrap:wrap;gap:14px;align-items:center}
h1{font-size:18px;margin:0;letter-spacing:.14em}h1 b{color:var(--acc)}main{padding:16px 20px;display:grid;gap:16px;grid-template-columns:minmax(0,1fr)}
.card{min-width:0;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.card h2{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);margin:0 0 10px}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;border:1px solid var(--line);color:var(--mut);font-size:12px}
.bar{height:8px;background:var(--line);border-radius:99px;overflow:hidden;display:flex}.bar i{display:block;height:100%}
.graph{display:flex;gap:10px;overflow:auto;padding-bottom:6px}.col{min-width:150px;display:flex;flex-direction:column;gap:6px}
.node{border:1px solid var(--line);border-left:4px solid var(--pend);border-radius:6px;padding:5px 8px;font-size:12px;cursor:pointer;background:var(--card);word-break:break-all}
.node.done,.node.skipped{border-left-color:var(--ok)}.node.running{border-left-color:var(--run)}.node.ready{border-left-color:var(--rdy)}.node.failed,.node.blocked{border-left-color:var(--fail)}.node.stale{border-left-color:var(--stale)}
.node small{display:block;color:var(--mut)}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:top}th{color:var(--mut);font-weight:600}
.t-confirmed{color:var(--ok);font-weight:600}.t-trace-verified{color:var(--rdy);font-weight:600}.t-unvalidated,.t-stale,.t-tampered{color:var(--fail);font-weight:600}
pre{white-space:pre-wrap;margin:0;font:12px/1.4 ui-monospace,Menlo,monospace}.grid2{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
@media (max-width:640px){main{padding:12px}header{padding:12px}}
</style></head><body>
<header><h1>SI<b>E</b>VE</h1><span id="eng" class="pill"></span><span id="phase" class="pill"></span><span id="next" style="color:var(--mut)"></span></header>
<main>
<div class="card"><h2>Campaign progress</h2><div class="bar" id="prog"></div><div id="counts" style="margin-top:8px;color:var(--mut)"></div></div>
<div class="card"><h2>Node graph — left to right is dependency order</h2><div class="graph" id="graph"></div><pre id="detail" style="margin-top:10px;color:var(--mut)">Click a node for detail.</pre></div>
<div class="grid2">
<div class="card"><h2>Findings — what the machine computes</h2><table id="findings"><tr><th>id</th><th>sev</th><th>tier</th><th>title</th></tr></table></div>
<div class="card"><h2>Frontier</h2><div class="bar" id="fbar"></div><div id="fstats" style="margin:8px 0;color:var(--mut)"></div><table id="fkinds"></table></div>
</div>
<div class="card"><h2>Event log</h2><table id="events"></table></div>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
const COL={done:'var(--ok)',skipped:'var(--ok)',running:'var(--run)',ready:'var(--rdy)',failed:'var(--fail)',blocked:'var(--fail)',stale:'var(--stale)',pending:'var(--pend)'};
let DATA=null;
function el(t,c,x){const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=x;return e}
function render(d){DATA=d;const e=d.engagement;
 document.getElementById('eng').textContent=e.name+' · '+e.id+' · '+e.packs.join('+');
 document.getElementById('phase').textContent='phase '+e.phase+' · pass '+e.pass+' · '+e.elapsed_min+'m'+(e.halt?' · HALTED':'');
 document.getElementById('next').textContent='NEXT: '+d.next.head+' — '+d.next.detail.slice(0,160);
 const c=d.campaign;const prog=document.getElementById('prog'),counts=document.getElementById('counts'),g=document.getElementById('graph');
 prog.textContent='';counts.textContent='';g.textContent='';
 if(c&&c.nodes){const tot=Object.keys(c.nodes).length;
  ['done','skipped','running','ready','stale','failed','blocked','pending'].forEach(s=>{const n=c.counts[s]||0;if(!n)return;const i=el('i');i.style.width=(100*n/tot)+'%';i.style.background=COL[s];i.title=s+': '+n;prog.appendChild(i)});
  counts.textContent=Object.entries(c.counts).map(([k,v])=>k+' '+v).join(' · ')+'   (profile '+c.profile+')';
  c.layers.forEach(layer=>{const col=el('div','col');layer.forEach(id=>{const n=c.nodes[id];const b=el('div','node '+n.status,id);b.appendChild(el('small','',n.kind+' · '+n.status));
   b.onclick=()=>{document.getElementById('detail').textContent=id+'\n'+(n.description||'')+'\nstatus: '+n.status+' · attempts '+n.attempts+'\ndepends on: '+(n.deps.join(', ')||'—')+'\noutputs: '+(n.outputs.join(', ')||'—')+(n.note?'\nnote: '+n.note:'')+(n.error?'\nERROR: '+n.error:'')};col.appendChild(b)});g.appendChild(col)});
 } else {counts.textContent=c&&c.error?c.error:'No campaign yet — `sieve campaign init`.'}
 const ft=document.getElementById('findings');ft.textContent='';const hr=el('tr');['id','sev','tier','title'].forEach(h=>hr.appendChild(el('th','',h)));ft.appendChild(hr);
 (d.findings||[]).filter(f=>f.kind==='FINDING').forEach(f=>{const r=el('tr');r.appendChild(el('td','',f.id));r.appendChild(el('td','',f.severity||'—'));r.appendChild(el('td','t-'+f.tier,f.tier));r.appendChild(el('td','',(f.title||'')+(f.why&&f.why.length?'  ('+f.why[0].slice(0,80)+')':'')));ft.appendChild(r)});
 const fs=d.frontier;const fb=document.getElementById('fbar');fb.textContent='';[['done','var(--ok)'],['dead','var(--pend)'],['blocked','var(--fail)'],['open','var(--rdy)'],['probing','var(--run)']].forEach(([k,col])=>{const n=fs.by_status[k]||0;if(!n||!fs.total)return;const i=el('i');i.style.width=(100*n/fs.total)+'%';i.style.background=col;i.title=k+': '+n;fb.appendChild(i)});
 document.getElementById('fstats').textContent=fs.open+' open of '+fs.total+' ('+fs.closed_pct+'% closed) · done '+fs.by_status.done+' · dead '+fs.by_status.dead+' · blocked '+fs.by_status.blocked;
 const fk=document.getElementById('fkinds');fk.textContent='';Object.entries(d.frontier_kinds).sort().forEach(([k,v])=>{const r=el('tr');r.appendChild(el('td','',k));r.appendChild(el('td','',v.open+' open'));r.appendChild(el('td','',v.closed+' closed'));fk.appendChild(r)});
 const ev=document.getElementById('events');ev.textContent='';(d.events||[]).slice(0,25).forEach(x=>{const r=el('tr');r.appendChild(el('td','',x.time.slice(11,19)));r.appendChild(el('td','',x.node));r.appendChild(el('td','',x.event));r.appendChild(el('td','',x.detail));ev.appendChild(r)});
}
async function tick(){try{const r=await fetch('/api/state',{cache:'no-store'});render(await r.json())}catch(e){}}
const emb=document.getElementById('data');
if(emb){render(JSON.parse(emb.textContent))}else{tick();setInterval(tick,3000)}
</script>
</body></html>
"""


def static_html(snap: Dict[str, Any]) -> str:
    data = json.dumps(snap).replace("</", "<\\/")
    return PAGE.replace("__DATA__", data)


def live_html() -> str:
    return PAGE.replace('<script type="application/json" id="data">__DATA__</script>\n', "")  # live mode fetches /api/state


def serve(eng: Engagement, port: int = 8787) -> ThreadingHTTPServer:
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
    page = live_html().encode("utf-8")

    class H(BaseHTTPRequestHandler):
        def _ok(self) -> bool:
            if (self.headers.get("Host") or "") not in allowed:      # DNS-rebinding guard
                self.send_error(403, "bad Host header")
                return False
            return True

        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if not self._ok():
                return
            if self.path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", page)
            elif self.path == "/api/state":
                try:
                    body = json.dumps(snapshot(eng)).encode("utf-8")
                except Exception as exc:  # noqa: BLE001
                    body = json.dumps({"error": str(exc)}).encode("utf-8")
                self._send(200, "application/json", body)
            elif self.path == "/healthz":
                self._send(200, "text/plain", b"ok")
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            self.send_error(405)

        def log_message(self, *a: Any) -> None:  # quiet
            return

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    srv.daemon_threads = True
    return srv


def run_forever(eng: Engagement, port: int) -> None:
    srv = serve(eng, port)
    print(f"dashboard: http://127.0.0.1:{port}/  (loopback only; Ctrl-C to stop)")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        t.join()
    except KeyboardInterrupt:
        srv.shutdown()
