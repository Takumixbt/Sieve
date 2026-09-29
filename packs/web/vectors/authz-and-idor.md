# Authorization & IDOR

### WEB-IDOR-01 · Unguarded sibling verb on a guarded object endpoint
- signal: `surface.tsv` shows a `GET /resource/{id}` with `auth: yes` and a `PUT`/`PATCH`/`DELETE` on the same path with `auth: unknown` or `no`
- attack: replay the mutating verb with a session that lacks any relationship to the target object's owner
- proof: request/response pair — the mutating call succeeds against another account's object
- fp: a sibling that returns 200 but performs a no-op with no actual state change is not an IDOR — confirm the object's state actually changed
- sev: high when it mutates another user's data; critical if it grants privilege or moves funds
- cwe: CWE-639
- kb: idor broken object level authorization sibling verb

### WEB-IDOR-02 · Predictable or enumerable object identifier
- signal: sequential integer IDs, UUIDv1 (embeds a timestamp), or a hashid with a guessable/leaked salt used as the sole access-control mechanism
- attack: enumerate adjacent IDs against an authenticated-but-unrelated session
- proof: a range of IDs returning other accounts' data under one session
- fp: an enumerable ID with a proper per-request ownership check on top is not this vector alone — the ID being guessable only matters if nothing else gates access
- sev: high
- cwe: CWE-639
- kb: idor predictable identifier enumeration uuid sequential

## SSRF

### WEB-SSRF-01 · Unvalidated "fetch from URL" feature
- signal: any endpoint accepting a URL to import, preview, render, or register as a webhook, with no destination validation
- attack: point it at `169.254.169.254` (cloud metadata), `127.0.0.1`, or an RFC1918 address; confirm blind cases via OAST
- tell: `fetch\(|axios\.get\(|requests\.get\(|urlopen\(` fed directly by a request parameter with no allowlist check nearby
- proof: OAST callback hit, or a returned response body containing internal service data
- fp: a URL validated against an allowlist of external domains, with DNS re-resolution checked at fetch time (not just at validation time) is not vulnerable — confirm re-resolution is actually checked, since DNS rebinding defeats validation-time-only checks
- sev: critical when it reaches cloud metadata or an internal admin service; high otherwise
- cwe: CWE-918
- kb: ssrf server side request forgery metadata webhook url fetch

## Race conditions

### WEB-RACE-01 · Check-then-act with no locking on a single-use resource
- signal: a coupon/discount/reward/withdrawal marked "used" or balance-decremented in a step separate from the check that it's still valid
- attack: fire N concurrent requests (Turbo Intruder) at the same endpoint with the same single-use resource
- proof: N successful uses of a resource meant to be single-use, or a balance withdrawn more than once
- fp: a single successful request out of many concurrent attempts, with the rest cleanly rejected, is not a race finding — the check-then-act gap must actually be demonstrated, not just attempted
- sev: high when it duplicates value (funds, credits); medium for a non-monetary counter
- cwe: CWE-362
- kb: race condition toctou check then act concurrent requests

## Cache poisoning

### WEB-CACHE-01 · Unkeyed input reflected into a cached response
- signal: a header or parameter the cache doesn't vary on (found via Param Miner) changes the response body
- attack: poison the cached response with a payload, then confirm a second, unauthenticated request to the same URL receives the poisoned version
- proof: the second request's response, from a fresh unauthenticated client, showing the injected content
- fp: reflection observed only in your own request's response, with no confirmed second-request poisoning, is not proof — the cache must actually serve the poisoned response to someone else
- sev: high when the poisoned content is attacker-controlled JS/redirect; medium for a defacement-only reflection
- cwe: CWE-444
- kb: cache poisoning unkeyed input web cache deception
