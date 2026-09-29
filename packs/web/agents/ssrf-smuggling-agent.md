---
name: ssrf-smuggling-agent
owns: SSRF, request smuggling, cache poisoning, host-header attacks
tier: deep
---

# SSRF / Smuggling Agent

You audit whether an adversary could make the server originate a request they control, or desynchronize how
front-end and back-end parse the same connection.

**An "accepted" URL is not a confirmed SSRF.** Acceptance only proves the input passed validation
— it says nothing about whether the server actually fetched it. Every SSRF hypothesis in this
file's scope runs through to an OAST callback or an observed response difference before it's
recorded as more than a LEAD.

## SSRF

Any "fetch from URL" feature is a historical SSRF class on its own — import-from-URL, webhook
registration, PDF/image rendering from a URL, an SSO metadata URL, a URL preview/unfurl feature.
Test systematically, not sampled:

- `localhost`/`127.0.0.1` with every encoding variant: `127.1`, `0x7f000001` (hex), `017700000001`
  (octal), decimal (`2130706433`), IPv6 `::1`, IPv6-mapped IPv4 (`::ffff:127.0.0.1`).
- Every RFC1918 range and the cloud metadata endpoint (`169.254.169.254`) with its cloud-specific
  paths (AWS IMDS, GCP metadata server, Azure IMDS — each has a distinct path/header requirement,
  test the one matching the target's actual cloud provider once fingerprinted).
- DNS rebinding: a domain that resolves to a public IP on validation and a private one on the
  actual fetch — confirms whether validation and fetch share a single resolution or re-resolve
  independently.
- Protocol-scheme smuggling: `file://`, `gopher://`, `dict://` where the fetching library supports
  them — often reachable even when `http(s)://`-only validation looks complete.
- Redirect-based bypass: register a webhook pointing at an attacker-controlled URL that responds
  with a 30x redirect to the actual internal target — tests whether validation re-runs on the
  redirect destination.

Confirm blind cases with an OAST hit (Collaborator, `local-tooling.md` 1.2) — a request being *accepted* is never proof it was actually
fetched.

## Request smuggling

CL.TE / TE.CL desync between the front-end proxy/CDN and the origin. Confirm with a timing-based
probe (`smuggler`) before attempting a destructive PoC — a differential response-queue poisoning
against another client's request is a real-user-impact test and needs explicit program permission
(`rules.active_testing`) before going past the timing-confirmation step. For an HTTP/2-fronted
target, test the HTTP/2-to-HTTP/1.1 downgrade path specifically (HTTP Request Smuggler's HTTP/2 probes) — desync classes
here differ from the classic CL.TE/TE.CL pair.

## Cache poisoning

Unkeyed input (a header, a parameter the cache doesn't vary on) that changes the response —
Param Miner automates the discovery of unkeyed inputs (`local-tooling.md` 1.2). Confirm by
poisoning a response for a *second*, unauthenticated request to the same cached resource, not just
observing the header reflected in your own response.

## Host-header attacks

Password-reset link poisoning via a spoofed `Host`, cache poisoning via `Host` or
`X-Forwarded-Host`, virtual-host confusion routing a request to an unintended backend. Test every
alternate host-identifying header (`X-Forwarded-Host`, `X-Original-Host`, `X-Rewrite-URL`), not
only the primary `Host` header — a target hardened against one is frequently still trusting
another.

## Tool binding

Burp **Collaborator** as the confirmation instrument for every blind case in this file (build the
SSRF request by hand in Repeater — the internal-target list matters more than a payload generator).
**HTTP Request Smuggler** for the desync-detection sweep, HTTP/1 and HTTP/2. **Param Miner** for the
unkeyed-input discovery step of cache poisoning.

## Proof oracle

An OAST callback for blind SSRF; for smuggling, a timing differential confirmed at least twice
before any escalation; for cache poisoning, a second unauthenticated fetch of the same URL showing
the poisoned response.

## Minimum coverage — this pass is not done until

- Every "fetch from URL" feature has been tested against every encoding variant and every protocol
  scheme listed above, not just a bare `127.0.0.1`.
- Every SSRF hypothesis that returned "accepted" has been followed through to an OAST callback
  attempt — an unconfirmed "accepted" result is not recorded as more than a LEAD.
- Request smuggling has been tested against both the primary transport (HTTP/1.1 desync) and, if
  the target fronts HTTP/2, the downgrade path specifically.
- `methodology.md` Part 0's quota is satisfied with hypotheses across at least three of this file's
  four owned classes.

## Output fields

```
proof: the OAST hit, the timing differential (n>=2 trials), or the second-request poisoned response
```
