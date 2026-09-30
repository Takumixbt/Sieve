# Recon resilience - the operational failure modes, and the fix for each

`shared-rules.md` is the skill holding itself to account. This file is the *target* pushing
back: the SPA that renders nothing to `curl`, the auth wall, the WebSocket-only data,
the WAF, the rate limit, the unverified contract, the stripped binary. These are the
obstacles a real engagement hits. The fix keeps the run **autonomous** (the skill
drives the live client itself) and **inside the scope card**. The operator is asked
for one headed pass: the dedicated test Gmail and, on a dApp, the dedicated test
wallet (`local-tooling.md` → authorized test identity).

## Web pack - most of these are solved by driving a real browser

The single biggest web recon failure is treating a modern app like a static site.
`scripts/browser-recon.py` (CloakBrowser, Playwright API) is the fix for a whole
class at once - it drives a real Chromium and captures the live surface autonomously
(the `browser-recon` campaign node). Then the obstacle-specific fixes:

| Failure mode | Fix |
|---|---|
| **SPA renders nothing without JS** - static recon sees an empty shell | `browser-recon.py` renders JS and captures the real DOM + every XHR the app fires |
| **Auth wall / login required** | one headed `--setup` / `--save-login` on the dedicated test Gmail into the persistent profile → later runs reuse `$HELIX_HOME/browser-profile` (`local-tooling.md`) |
| **Client-side routing** - endpoints live in JS, not HTML | `browser-recon.py --click` drives the router; `js-recon.py` extracts the route table from the bundle |
| **WebSocket / SSE realtime data** - invisible to `curl` | the browser driver captures every WS frame (sent + received) with its schema |
| **Short-lived / rotating tokens (CSRF, JWT refresh)** - replayed requests 401 | drive through the browser so tokens are always fresh; capture the refresh flow itself |
| **Signed requests (HMAC / custom header)** - replay fails | observe the signing in the captured JS; replicate it, or note the scheme as the finding surface |
| **Cross-account test needs two identities** (IDOR / sibling rule) | two browser contexts with two saved sessions; compare account B's token against account A's object |
| **GraphQL persisted queries** - arbitrary queries rejected | capture the persisted-query hashes the real client sends; test field-auth through them |
| **WAF / CDN blocks a payload** | fingerprint it; vary encoding/framing/endpoint; test an in-scope origin if discoverable; a 403 is a signal to change technique, then it is coverage-debt - **not** a target to hammer |
| **Rate limit / 429** | responsible pacing (jittered backoff, low concurrency) - which is also the not-a-DoS requirement; stay under a documented limit; the limit's own weakness may be a finding (`race.py`) |
| **CAPTCHA at a gate** | complete it once during the headed `--setup` pass as the test identity; the saved profile carries the session. A mid-flow gate with no test path is coverage-debt |
| **Client looks automated** | CloakBrowser is the driver (`humanize=True`, persistent profile, `stealth_args` on). Headed when a wallet extension is loaded. If the app still blocks, record it and keep going on what you can reach |
| **Geo/region gate** | `--proxy` + `--geoip` when the engagement supplies a proxy; otherwise the program's region + test account |

## Web3 pack

| Failure mode | Fix |
|---|---|
| **Unverified / proxy / diamond contract** - no source | fetch verified source (Etherscan/Blockscout); resolve the impl (EIP-1967 slot / `facets()`); if still unverified, **decompile the bytecode** (heimdall-rs / Dedaub / panoramix) and audit that. Always pin the artifact and check it against the local source (`references/scope-intake.md`) |
| **Public RPC rate-limit / 429** | multi-RPC fallback (provider key → public → self-hosted) + cache reads; plain resilience against a public service |
| **Non-archive node** - can't read historical/exploit-block state | use an archive node for past state |
| **Bytecode ≠ local source** | artifact hash-pin before reading a line (already a hard rule) - a stale clone silently invalidates every finding |
| **Frontend builds the signed tx (dApp)** | the on-chain audit alone misses what the user signs - `browser-recon.py` captures the actual `to`/`data`/`value` the client builds (crossover seam 4). The browser driver serves web3, not just web |
| **Off-chain keeper / oracle / prover / sequencer** the contract trusts | crossover seams 2/5/7/8 - audit the off-chain decision, not just the on-chain verifier |
| **Chain-specific surface** (L2 precompiles, custom opcodes, Hyperliquid HyperCore reads) | the per-VM gate + treat the precompile/precompiled read as a trusted external source (integration/oracle lens) |

## Binary pack

| Failure mode | Fix |
|---|---|
| **Stripped (no symbols)** | disassembly + signature recovery (Ghidra/FLIRT) - the `reverse-engineering-agent`'s job |
| **Packed / obfuscated** | unpack (UPX / manual OEP dump); record the anti-analysis as a coverage-confidence fact |
| **Anti-debug / anti-VM** | patch or bypass the check *for analysis* (it is your authorized target), or run under qemu |
| **Won't run (missing deps / wrong arch)** | harness the function under test, stub the dependency, or emulate - you do not need the whole program to audit a parser |
| **Binary-only (no source) fuzzing** | AFL++ binary-only mode (qemu/frida) instead of a source build |
| **Not actually native** (WASM / JVM / .pyc bytecode) | re-classify - it is a different pack/toolchain, not a memory-corruption target |

## Scope still gates the client

The live client is **CloakBrowser** at full launch surface (`scripts/browser-recon.py`,
`local-tooling.md`). Every URL it opens must be on the scope card (`shared-rules.md`
§8). The identity in the profile is a dedicated test Gmail and a dedicated test
wallet - not a production mailbox and not production funds.
