# 2026 incident patterns

Three cards that changed how native and mobile audits should be scoped, each traced to a real 2026
incident (the MikroTrick RouterOS chain, Pwn2Own Berlin's logic-only browser sandbox escape, the
Ivanti EPMM pre-auth chain). The through-line: **chains of small, individually-unremarkable logic
bugs are displacing single memory-corruption bugs**, because mitigations raised the cost of the
latter — so a finding scored "low, no impact alone" is a composition candidate, not a closed item
(`references/methodology.md` Part 8).

## Auth / credential comparison

### BIN-AUTHKEY-INCOMPLETE-CMP-01 · Incomplete public-key/credential comparison auth bypass
- signal: any authentication scheme that "compares a public key" (SSH host/user key auth, mTLS client cert pinning, JWT/JWK public-key matching, signed-URL verification) — check whether the comparison logic actually compares every structural component of the key/credential (for RSA: modulus AND exponent; for a cert: full DN/SAN/key material, not just a cached fingerprint field) or only a subset used as a lookup/matching key
- attack: obtain or derive a partial component of an authorized credential that is not secret (an RSA public modulus, by definition public, vs. the private exponent); construct a new, attacker-controlled credential (a keypair with exponent=1) that matches on every component the target's comparison logic actually checks but differs on a component it silently ignores; use that attacker-controlled credential (for which the attacker does hold the matching private key) to complete authentication as the victim identity
- proof: a working authentication as a victim identity performed using a credential the attacker legitimately generated (not stolen), demonstrating the target's matching logic accepted a different, attacker-forged key/cert differing from the authorized one in a component that was never actually compared
- fp: confirm the "matched but different" credential truly was not the authorized one bit-for-bit — if the target normalizes/canonicalizes the credential before comparison (recomputing exponent from a stored default), the comparison may be complete in practice even if the code reads as checking only part of the structure
- sev: Critical
- cwe: CWE-347
- kb: ssh public key auth incomplete rsa comparison modulus exponent bypass MikroTrick

## Composed logic chains

### BIN-CHAIN-LOGIC-SBXESC-01 · Multi-bug pure-logic sandbox/permission-boundary escape
- signal: target has a well-hardened memory-safety posture (site isolation, CFI, hardened allocator, no recent memory-corruption CVEs) but exposes multiple independently-low-severity logic/permission findings (an IPC message the sandboxed process shouldn't be able to send but can; a permission check present on one code path but missing on an equivalent alternate path; a state transition reachable out of order) — treat a cluster of such findings as a composition candidate rather than closing each as "Low, no direct impact standalone"
- attack: map every sandboxed-process-to-broker/host IPC message and every permission/state check gating a privileged operation; for each, test not just "is the check present" but "is the check present on every code path that reaches this operation, including less-obvious ones (error-handling paths, out-of-order re-entrant calls, alternate API entry points)"; then attempt to compose 2-4 such gaps into a sequence that starts from confirmed sandboxed code and ends outside the sandbox boundary, exactly as a memory-corruption chain would compose an info-leak + a corruption bug
- proof: an end-to-end PoC starting from the actual sandboxed execution context (not a privileged test harness) that demonstrates code execution or state modification outside the intended sandbox boundary, using only the composed logic bugs — no memory corruption required
- fp: an individual missing-permission-check finding that is real but requires an already-privileged starting point to reach is not evidence of a sandbox escape — every step of the chain must be reachable starting from the actual untrusted/sandboxed entry point
- sev: Critical
- cwe: CWE-284
- kb: browser sandbox escape logic bug chain no memory corruption ipc permission Pwn2Own

### BIN-SHELLOUT-ARITH-01 · Command injection via shell arithmetic-expansion / RewriteMap-style external script
- signal: target's web/app server invokes an external shell script or interpreter for a subsidiary function (Apache mod_rewrite RewriteMap programs, a "helper script" called via popen/exec, a webhook handler shelling out) — look at the external script's own input handling, not just the calling application's validation, since input that already passed app-layer validation is often wrongly treated as pre-sanitized by the time it reaches the helper script
- attack: identify an HTTP parameter or other attacker-controlled value that flows into the external script's invocation; within that script, look specifically for Bash arithmetic-expansion contexts (`$(( ... ))`, `let`, array-index expressions) as a second, easily missed injection surface distinct from the obvious backtick/`$()`/`eval` patterns; craft a value that, when the shell evaluates it as an arithmetic expression, contains a command-substitution subexpression the shell will execute as a side effect of arithmetic evaluation
- proof: a crafted HTTP request that results in attacker-chosen OS command execution on the target host, with the request/response and resulting command output captured as evidence
- fp: many arithmetic-expansion code paths only accept values already constrained to be numeric by an earlier regex/type check in the calling application — confirm the actual end-to-end data flow, not just that the pattern exists in the script, before treating it as exploitable
- sev: Critical
- cwe: CWE-78
- kb: apache rewritemap bash arithmetic expansion command injection pre-auth rce Ivanti EPMM
