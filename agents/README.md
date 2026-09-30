# Agents - the roster and the bundle spec

Every agent below is a single-lens hunter: read its bundle once, hunt its lens, emit
FINDING/LEAD/HYPOTHESIS blocks (`shared-rules.md`), never gate or dedup your own output
(`judging.md` §0 - discoverer ≠ verifier). `dispatch.md` builds and spawns every bundle.

★ marks the **core** roster - what `--mode quick` runs alone. Everything else is the **deep**
roster, run by default (`sieve init` defaults to `--mode deep`): the class of bug that pays best is
usually the one a quick pass skips.

## Web3 - `packs/web3/agents/`

Twelve lenses covering the full space of web3 logic bugs - arithmetic, permissions, economics,
execution flow, invariants, peripheral code, first-principles assumptions, asymmetry, boundaries,
and three cross-lens gap-hunters - generalized past Solidity to every VM `xray_web3.py` discovers.
Methodology attribution: `CREDITS.md`.

| Agent | ★ | Owns |
|---|---|---|
| `math-precision-agent` | ★ | Rounding, precision loss, decimal/scale mixing, overflow, downcasts |
| `access-control-agent` | ★ | Permission model gaps, initialization hijack, privilege escalation, delegatecall/proxy storage collisions |
| `economic-security-agent` | ★ | External dependency failure, token misbehavior, atomic value extraction, ERC compliance |
| `execution-trace-agent` | ★ | Cross-function/cross-transaction execution-flow assumptions |
| `invariant-agent` | | Conservation laws, state couplings, round-trip and boundary invariant breaks |
| `periphery-agent` | | Libraries, helpers, encoders, base contracts - the code nobody else reads |
| `first-principles-agent` | | Bugs with no name - implicit assumptions the code's own logic rests on |
| `asymmetry-agent` | | Paired functions/branches/storage that should mirror and don't |
| `boundary-agent` | | Every external call site and payable function, four corner cases each |
| `numerical-gap-agent` | | Seam: precision × invariant × boundary (gap-hunter) |
| `trust-gap-agent` | | Seam: access × economics × asymmetry (gap-hunter) |
| `flow-gap-agent` | | Seam: execution × periphery × first-principles (gap-hunter) |

## Web - `packs/web/agents/`

| Agent | ★ | Owns |
|---|---|---|
| `recon-agent` | ★ | Surface mapping: subdomains, live hosts, JS endpoints/secrets, tech fingerprint → CVE |
| `access-control-agent` | ★ | IDOR, broken auth, JWT/OAuth/SSO, privilege escalation - the sibling rule |
| `injection-agent` | ★ | SQL/NoSQL/command/SSTI/XXE, deserialization |
| `business-logic-agent` | ★ | Race conditions, workflow/state-machine bypass, price/quantity manipulation |
| `client-side-agent` | | XSS, CSRF, postMessage, prototype pollution, open redirect, clickjacking |
| `ssrf-smuggling-agent` | | SSRF, request smuggling, cache poisoning, host-header attacks |
| `graphql-agent` | | Introspection, depth/complexity DoS, authorization-per-field gaps |
| `supply-chain-agent` | | Dependency confusion, exposed secrets, outdated/vulnerable libraries |
| `ai-native-appsec-agent` | | Prompt injection, insecure LLM output handling, MCP/plugin supply chain, agent memory poisoning, toxic tool-call composition - only in scope when the target has an AI-native surface |

## Binary / mobile - `packs/binary/agents/`

| Agent | ★ | Owns |
|---|---|---|
| `memory-safety-agent` | ★ | Overflow, UAF, double-free, type confusion, format string, integer-to-OOB |
| `exploit-primitive-agent` | ★ | Turning a crash into control - the primitive chain |
| `reverse-engineering-agent` | ★ | Enumeration-only: symbols, control flow, string/import triage |
| `fuzzing-harness-agent` | | Enumeration-only: builds a harness, never decides a verdict |
| `crypto-logic-agent` | | Weak crypto choices, bad randomness, key handling |
| `mobile-static-agent` | ★ | Manifest/plist review, exported components, deep links, hardcoded secrets |
| `mobile-dynamic-agent` | | Frida-driven runtime hooks: pinning bypass, root-detection bypass, storage dump |

**Enumeration-only agents never decide a verdict** - they map surface or build a harness; the
orchestrator re-judges anything they surface. This is the raw→verified boundary from
`judging.md` §0, enforced by role, not by model tier.

## Seams - `packs/seams/agents/`

| Agent | Owns |
|---|---|
| `crossover-agent` | Runs once two or more packs have produced output; hunts the seams in `crossover.md` |

## The bundle every agent receives

See `dispatch.md` for the exact `cat` order and the dispatch prompt. Every bundle ends with the
agent's own file (`agents/<agent>.md`) last, so its lens is the most recent thing in context when
hunting starts.
