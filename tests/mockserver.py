"""A tiny mock of the Solodit and OSV endpoints. Records server-side timestamps so tests can prove
rate-limit behaviour from the outside."""
import contextlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {}


def reset(**kw):
    STATE.clear()
    STATE.update({"mode": "nested", "key": "test-key", "requests": [], "fail_429": 0, "retry_after": 1})
    STATE.update(kw)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _send(self, code, obj, headers=None):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        STATE["requests"].append({"t": time.time(), "path": self.path, "body": body})
        if self.path.endswith("/solodit/findings"):
            if self.headers.get("X-Cyfrin-API-Key") != STATE["key"]:
                return self._send(401, {"error": "bad key"})
            if STATE["fail_429"] > 0:
                STATE["fail_429"] -= 1
                return self._send(429, {"error": "slow down"}, {"Retry-After": str(STATE["retry_after"])})
            nested = "filters" in body
            if (STATE["mode"] == "nested") != nested:
                return self._send(400, {"error": "unexpected request shape"})
            f = body["filters"] if nested else body
            kw = f.get("keywords", "")
            return self._send(200, {"findings": [{
                "id": "id-" + kw.replace(" ", "-")[:20], "slug": "slug-" + kw.replace(" ", "-")[:20],
                "title": f"Oracle price manipulation ({kw})", "impact": "HIGH",
                "content": f"Spot price used for {kw}. Contact bob@example.com key AKIAABCDEFGHIJKLMNOP",
                "firm_name": "Sherlock", "protocol_name": "ExampleLend", "quality_score": 4.5,
                "tags": [{"value": "Oracle"}, {"value": "Flash Loan"}]}], "totalResults": 1})
        if self.path.endswith("/v1/query"):
            return self._send(200, {"vulns": [{"id": "GHSA-xxxx-yyyy", "summary": "Prototype pollution in lodash",
                                              "details": "merge allows __proto__", "aliases": ["CVE-2019-10744"],
                                              "database_specific": {"severity": "HIGH"}}]})
        self._send(404, {"error": "no route"})


@contextlib.contextmanager
def run_mock(**kw):
    reset(**kw)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", STATE
    finally:
        srv.shutdown()
        srv.server_close()
