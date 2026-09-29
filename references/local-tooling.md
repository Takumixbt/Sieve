# Local tooling — the complete toolkit

Sieve does not scan, fuzz, crawl, or disassemble anything itself. Every capability below is a
real, independently-maintained tool the operator installs; Sieve's job is knowing which one to
reach for, in which phase, and how to treat what it says — a lead, gated by `judging.md`, never a
finding on its own.

`sieve doctor` probes for the core of this list and prints what's present, what's missing, and
which finding classes degrade to coverage-debt without it (`shared-rules.md` F7). Nothing here is
required to start an engagement; a missing tool is recorded, never silently skipped. Install
commands for the core set are in `setup.md`; anything beyond that is a one-line search away and
named here so you know it exists and when to reach for it.

**How to read this file.** Each pack is organized by phase, in the order an engagement actually
uses it: recon → static/passive → interception/dynamic → vulnerability-class tooling →
exploitation/proof. Within a phase, the first tool named is the default; the others are named for
when the default doesn't fit the target.

---

## 1 · Web

### 1.1 Reconnaissance & asset discovery

| Purpose | Primary | Alternatives / specialists |
|---|---|---|
| Subdomain enumeration | `subfinder` | `amass` (deeper, slower, graph-based), `assetfinder`, `chaos` (ProjectDiscovery's own dataset, needs an API key), certificate-transparency search (`crt.sh`, `censys`), `knock` (wordlist-driven), `fierce` (DNS recon for non-contiguous IP space) |
| DNS resolution / brute force | `dnsx` | `massdns`, `puredns`, `shuffledns` (wordlist-driven subdomain brute force at scale) |
| Typosquat / phishing-domain / brand-impersonation detection | `dnstwist` | a different use case from subdomain enum — permutes the target's own domain and checks which lookalikes are registered; relevant to any brand-protection-adjacent engagement scope |
| IP/service search engines beyond Shodan/Censys, useful when the target or its infra isn't US-centric | Shodan/Censys | `ZoomEye`, `FOFA` (China-focused), `onyphe`, `BinaryEdge`, `GreyNoise` (also flags known-scanner/benign noise, useful for filtering your own recon traffic's signature) |
| Credential-reuse / data-breach exposure | `haveibeenpwned` API | `dehashed` — relevant to a credential-stuffing/password-reuse angle on the recon surface |
| Network-ownership intelligence (who actually announces this IP range) | `BGPview` | `Robtex` — useful alongside `cloud_enum`/`S3Scanner` for cloud-asset-exposure work |
| IP reputation / abuse-history lookup | `abuseipdb` | flags a target's outbound IPs or webhook endpoints against known-abusive ranges — cheap, free-tier API |
| Live-host probing & fingerprinting | `httpx` | `whatweb`, `wappalyzer` (browser extension or CLI), `webanalyze` |
| Visual recon (screenshot every live host) | `gowitness` | `aquatone`, `eyewitness` — invaluable for triaging hundreds of hosts fast |
| Active crawling (JS-aware) | `katana` | `gospider`, `hakrawler` |
| Historical / passive URL discovery | `gau` | `waybackurls`, Common Crawl index queries |
| Content & directory discovery | `ffuf` | `feroxbuster` (Rust, recursive by default), `gobuster`, `dirsearch`, `kiterunner` (purpose-built for API route guessing against an OpenAPI-shaped target) |
| Parameter discovery | `arjun` | `x8`, `paramspider` |
| JS bundle analysis (endpoints, secrets, source maps) | `LinkFinder` | `JSluice`, `SecretFinder`, `mantra`, or a Burp **JS Link Finder**/**GAP** pass (1.2) |
| Cloud asset exposure | `cloud_enum` | `S3Scanner`, `GCPBucketBrute`, `CloudBrute` |
| Secrets in accessible repos/history | `trufflehog` | `gitleaks`, `shhgit`, a manual `.git` directory dump + `git log -p` if the directory itself is exposed |
| WAF fingerprinting (informs payload strategy, never a target to defeat for its own sake) | `wafw00f` | Burp's passive detection |
| Headless browser automation against a target with real anti-bot defenses (Cloudflare/Akamai/PerimeterX/DataDome) | **CloakBrowser** (`CloakHQ/CloakBrowser`) | A source-patched, stealth Chromium — drop-in for Playwright/Puppeteer/Selenium — worth reaching for the moment `katana`/a normal headless browser gets challenge-paged or fingerprinted off a JS-heavy target. `playwright-stealth`/`undetected-chromedriver` are the older, more fragile config-level alternative (JS-injected patches a fingerprint check can detect; CloakBrowser's patches are source-level, compiled in). Route its traffic through Burp's proxy (1.2) to get the same interception/replay workflow with the anti-bot problem solved underneath it. |

### 1.2 Interception & manual testing — the core of the web strand

**Burp Suite** is the proxy of record: every authenticated replay, every multi-identity
comparison, every race condition goes through it or through something driven from it. Community
edition covers manual replay and Repeater; Professional adds Intruder concurrency control (needed
for real race testing) and the extension ecosystem below. **OWASP ZAP** is the credible
open-source alternative when Burp Pro isn't available — its automation framework and passive
scanner cover a meaningful fraction of the same ground. **mitmproxy** is the scriptable option,
strongest for mobile traffic (`packs/binary/agents/mobile-dynamic-agent.md`) and for building a
custom interception script Burp's extension model doesn't fit well.

**Burp extensions, by what they're for** (BApp Store, inside the app):

| Extension | Use it for |
|---|---|
| **Autorize** | The sibling rule, automated: replay every request under a lower-privilege session and flag the ones that still succeed. Runs continuously while you browse as the higher-privileged user. |
| **AuthMatrix** | A structured authorization matrix (roles × endpoints) when Autorize's single-session model isn't enough. |
| **Turbo Intruder** | True concurrent request firing for race-condition proof. A single-threaded send is not a proof; this is. |
| **Param Miner** | Hidden/unlinked parameters and headers, and the cache-poisoning workflow (unkeyed-input detection). |
| **JS Link Finder** / **GAP** | Endpoint extraction from JS bundles, done properly instead of with a regex. |
| **Backslash Powered Scanner** | Finds injection-*shaped* behavior, not payload-shaped — catches filters the payload-based active scanner misses. |
| **JWT Editor** | `alg:none`, key confusion, `kid` injection, signature stripping. |
| **Logger++** | Full request/response history with filtering — the evidence trail a finding's `proof:` field cites. |
| **ActiveScan++** | Extends the built-in scanner's coverage (host-header attacks, more SSRF/SSTI shapes). |
| **Retire.js** | Flags outdated JS libraries with known CVEs while you browse. |
| **Collaborator Everywhere** | Auto-inserts Collaborator payloads into every request for passive OAST coverage without hand-placing them. |
| **Hackvertor** | Payload encoding/transformation chains for WAF-adjacent testing. |
| **Piper** | Pipes traffic through external CLI tools (nuclei, a custom script) from inside Burp. |
| **InQL** | GraphQL schema extraction, query generation, and a batch-testing console — the GraphQL equivalent of Autorize's sibling-testing loop (1.3). |
| **Software Vulnerability Scanner** | Maps fingerprinted components to known CVEs directly inside Burp. |
| **Flow** | Visualizes and filters the request sequence for a complex multi-step flow (`business-logic-agent.md`'s workflow-bypass work). |

**CyberChef** (browser-based or self-hosted) is the encoding/decoding/crypto swiss-army knife for
whatever payload transform a target's custom encoding scheme demands.

### 1.3 Vulnerability-class tooling

| Class | Tool |
|---|---|
| SQL injection (confirmation, never discovery) | `sqlmap` |
| NoSQL injection | `NoSQLMap` |
| Command injection | `commix` |
| SSTI | `tplmap` |
| XSS (confirmation via real browser rendering) | `dalfox`, `XSStrike` |
| Blind/OOB confirmation (SSRF, blind XXE, blind injection) | Burp **Collaborator**, self-hosted `interactsh-client`/`interactsh-server` |
| SSRF-specific payload generation | `SSRFmap` |
| CORS misconfiguration | `Corsy`, `CORScanner` |
| Request smuggling | `smuggler`, an HTTP/2-aware variant (`h2csmuggler`) for downgrade-based desync |
| GraphQL | `InQL` (1.2), `graphql-cop`, `clairvoyance` (schema recovery when introspection is disabled) |
| JWT | `jwt_tool`, Burp **JWT Editor** (1.2) |
| TLS/SSL configuration | `testssl.sh`, `sslyze`, `sslscan` |
| CMS-specific | `wpscan` (WordPress), `droopescan` (Drupal/SilverStripe), `joomscan` (Joomla) |
| Templated CVE/misconfig sweep | `nuclei` (treat every hit as a LEAD, never a finding on its own) |
| General vulnerability scanning | `nikto` (fast, noisy, good for a first pass) |
| Authenticated login brute force (only where the program's scope explicitly permits it) | `hydra` |

### 1.4 Reporting & evidence

Burp's **Logger++** export and a saved `.har` capture (browser DevTools, or Burp's own project
file exported to HAR) are what `sieve xray web --har ...` ingests. An **OpenAPI/Swagger** doc, if
the target publishes one, is the other structured input `sieve xray web --openapi ...` reads.

---

## 2 · Web3

### 2.1 Static analysis — the x-ray's own first move, not operator-supplied corroboration

`sieve xray web3` auto-invokes `slither` and `aderyn` itself the moment they're on PATH — see
`references/xray.md` Phase 0. Install both; running one instead of both is a coverage gap, not a
choice, since their detector sets overlap but don't agree often enough to skip either.

| Tool | What it's strongest at |
|---|---|
| `slither` | The default first pass — fast, mature detector set. Auto-run by `sieve xray web3`. |
| `aderyn` | A faster, Rust-native alternative with an overlapping but non-identical detector set. Auto-run by `sieve xray web3` alongside slither, never instead of it. |
| `mythril` | Symbolic execution — different coverage than either of the above, strong on arithmetic/reachability questions for a single function. Not auto-run (slow enough that blocking the x-ray on it is the wrong tradeoff) — run it by hand on the handful of functions the auto-run pass or your own read flagged as arithmetic-heavy. |
| `semgrep` (with a Solidity ruleset, or a hand-written rule) | The right tool once you know a specific anti-pattern's shape — the "what changed" method's step 4 is often a one-line semgrep rule instead of a manual grep sweep. |
| `4naly3er` | Gas-and-pattern static pass — most of its findings are Do-Not-Report by `packs/web3/judging.md`, but it occasionally surfaces a real access-control gap alongside the noise. |
| Wake (`wake detect`) | Ackee Blockchain's Python-based framework — detectors plus a scriptable analysis layer when a one-off custom check is worth writing. |
| `surya` / `sol2uml` | Call-graph and inheritance-graph visualization — read before writing `xray/architecture.json` by hand on a large, deeply-inherited codebase. |
| `trailmark` (`uv tool install trailmark`) | Builds a queryable code graph once (tree-sitter parse + a `rustworkx` graph, 17+ languages including Solidity), then answers "who calls X," "every path from this entry point to that sink," and blast-radius questions as graph queries instead of a manual re-read every time the question comes up. Auto-run by `sieve xray web3` alongside slither/aderyn when installed (`xray/graph.json`) — see `xray.md` Phase 1; a manual call-chain trace is still the fallback when it isn't installed, never a blocker. `.trailmark/links.toml` is worth setting up by hand on a protocol that spans more than one VM/language (an Anchor program calling out to a Solidity bridge, a CosmWasm contract's IBC hooks) — a single-language parser can't see that boundary crossing on its own. |
| **`heimdall-rs`** (CLI: `heimdall`, installer: `bifrost`) | **Not just a decompiler for missing-source targets** — `heimdall decompile` (pseudo-Solidity from bytecode), `heimdall disassemble` (raw opcodes), `heimdall cfg` (control-flow graph), and `heimdall dump` (a storage-layout dump straight off a deployed contract's actual slots, which catches a proxy/upgrade storage-collision that reading the *source's* declared layout alone would miss — run it even on a verified target when a delegatecall/proxy pattern is in play). |
| `panoramix` | An older EVM decompiler, still worth a second pass alongside `heimdall-rs` when its output disagrees or one tool's decompilation is unusually lossy on a specific target's bytecode patterns. |

**Unverified or bytecode-only targets:** `heimdall-rs`/`panoramix` decompile EVM bytecode back to
pseudo-Solidity when no source is published — every finding from a decompiled target carries
`confidence: heuristic` (`references/scope-intake.md`). `ethersplay` (a Binary Ninja plugin) and
`evm-cfg-builder` are the control-flow-graph route when a decompiler's output is too lossy to
reason about directly.

### 2.2 Dynamic proof, fuzzing, and formal verification

| Tool | Use |
|---|---|
| **Foundry** (`forge`, `cast`, `anvil`) | The default PoC harness — a fork test demonstrating the exploit end-to-end is the strongest proof a web3 finding can carry (`judging.md` Gate 6). `anvil` forks mainnet/testnet state locally; `cast` is the fast CLI for one-off calls and encoding. |
| **Echidna** | Property-based fuzzing, longest track record, mature corpus/coverage tooling (`references/property-fuzzing.md`). |
| **Medusa** | Property-based fuzzing, parallelizes natively — faster wall-clock on a multi-core machine. |
| **Halmos** | Symbolic testing directly on existing Foundry test files — fast to add when the project already has Foundry tests to reuse as properties. |
| **ItyFuzz** | A hybrid fuzzer (symbolic-execution-assisted) that's found bugs the pure-fuzzing tools above missed on some targets — worth a run on a high-value target even after Echidna/Medusa converge. |
| **Certora Prover** (if licensed) | Formal specification when a property must hold for *all* inputs, not just the ones a fuzzer reached. |
| **Tenderly** | Transaction simulation and step-through debugging against real or forked mainnet state — often faster than a local fork for a one-off "what would this call actually do" question. |

### 2.3 Per-chain / per-VM tooling

| Chain / VM | Tooling |
|---|---|
| EVM (general) | Everything in 2.1–2.2. `Remix` (browser IDE) for a fast one-off compile-and-poke. |
| Solana / Anchor | `anchor` CLI, `solana-test-validator` (local cluster for a fork-equivalent test), `soteria` (Solana-specific static analyzer), `sec3`/`x-ray` (commercial Solana audit tooling) for a second static opinion. |
| Move (Aptos / Sui) | The Move Prover (formal verification built into the Move toolchain), `aptos` CLI, `sui` CLI, `sui move test`. |
| CosmWasm | `cosmwasm-check` (validates a compiled contract against the chain's required capabilities), `wasmd` for a local chain. |
| Cairo / Starknet | `caracal` (Crytic's Cairo static analyzer — the closest Cairo equivalent to Slither), `amarna` (an older Cairo static analyzer, still useful for a second pass), the `starknet` CLI/Scarb toolchain for compiling and testing. |
| Algorand | `goal`/`algokit` CLI, PyTeal/TEAL static review — check specifically for rekeying-vulnerable logic, unchecked fee handling, and asset-closing edge cases (Trail of Bits' `building-secure-contracts` names these as the highest-frequency real Algorand bug classes). |
| Substrate (Polkadot/Kusama parachains) | `subxt` for typed chain interaction/testing, `cargo-contract` for ink!-based pallets — check `BadOrigin` handling, weight/fee-exhaustion, and panic-on-overflow in pallet arithmetic. |
| TON | FunC/Tact toolchain (`func`, `tact` compiler), `ton-community/blueprint` for a local test harness — check integer-as-boolean confusion, fake-Jetton-contract acceptance, and TON forwarding without a gas-sufficiency check. |

### 2.4 On-chain intelligence

Block explorers (Etherscan and its per-chain equivalents) for verified source and transaction
history; `4byte.directory` / OpenChain's signature database to resolve an unknown function
selector found in calldata; **Sourcify** for decentralized source verification when a chain's own
explorer doesn't have it; **Dune Analytics** for a historical query across on-chain activity
(useful for "has this exact attack pattern already happened here" checks); **DeFiLlama** for
protocol TVL/composability context that shapes the economic-security lens's blast-radius
reasoning.

---

## 3 · Binary & mobile

### 3.1 Triage

`checksec` (mitigations: NX, PIE, canary, RELRO, Fortify), `file`, `strings`, `readelf`,
`objdump`, `nm` (binutils — usually already present). `DIE` (Detect It Easy) or `PEiD` for packer
identification on Windows PE targets. `binwalk` for firmware images — extracts embedded
filesystems, identifies compression, finds embedded keys/certificates. `EMBA` for a full
automated firmware security baseline (filesystem extraction through a static-analysis sweep) when
the target is an embedded/IoT firmware image rather than a single binary.

### 3.2 Reverse engineering — static

**Ghidra** (free, scriptable, the default for anything without an IDA license) or **radare2**/
**rizin** (faster for quick triage, better for scripting a repeated task across many binaries;
**Cutter** is r2's GUI when a visual CFG helps) or **IDA Pro/Free** where a license exists —
**Binary Ninja** is a strong middle ground (better decompiler output than Ghidra on some
architectures, a real Python API) worth reaching for on a stubborn target. **Hopper** covers
macOS/iOS Mach-O well when Ghidra's support for a specific Objective-C/Swift pattern falls short.
`YARA` rules for pattern-matching known-vulnerable code signatures across a large binary set.

### 3.3 Dynamic analysis & debugging

`gdb` with `pwndbg` or `gef` (either turns raw GDB into an exploit-dev-aware debugger — heap
inspection, one-command ASLR-aware breakpoints); `peda` as an older but still-usable alternative.
`WinDbg`/`x64dbg` for Windows targets; `lldb` on macOS/iOS. `strace`/`ltrace` for syscall and
library-call tracing on Linux; **Process Monitor** and **Process Hacker** for the Windows
equivalent. `Valgrind` (and `Dr. Memory` on Windows) for memory-error detection on a target that
doesn't need to be adversarially fuzzed — often faster than standing up a fuzzer for a single
suspected bug. `QEMU`, `unicorn`, and `qiling` (a higher-level emulation framework built on
Unicorn) for running or single-stepping code without the real hardware/OS underneath it —
essential for firmware and embedded targets. `Triton` — dynamic symbolic execution/taint-tracking
built on real instruction traces, a complementary alternative to `angr`'s (mostly static) symbolic
execution when a question is easier answered by actually running the target under instrumentation
and tracking taint through it than by exploring the binary's control-flow graph abstractly.

### 3.4 Fuzzing

**AFL++** for native C/C++/Rust targets with a fuzzable entry point; **libFuzzer** when the target
already builds as a fuzz harness (`cargo fuzz` for Rust, Go's native fuzzing,
`-fsanitize=fuzzer` for C++); **honggfuzz** as a strong alternative with different mutation
strategies worth trying when AFL++ plateaus. **boofuzz** for stateful protocol fuzzing (a network
daemon that requires a specific handshake before the interesting parsing begins). A crash without
a sanitizer (ASan/UBSan) built in is a much weaker proof — build with
`-fsanitize=address,undefined` before fuzzing whenever the target allows it
(`references/property-fuzzing.md`'s web3 equivalent of this same discipline).

### 3.5 Exploit development

`pwntools` (the standard Python exploit-dev framework — process interaction, ROP-chain
construction, format-string helpers). `ROPgadget`/`ropper` to enumerate available gadgets;
`one_gadget` to find a single-instruction win condition in libc; `angrop` (built on `angr`) to
auto-generate a ROP chain when hand-building one is impractical. `angr` itself for symbolic
execution when a path-reachability question is better answered symbolically than by fuzzing.

### 3.6 Mobile — Android

`jadx` (Java/Kotlin decompilation — the first read for any APK) or `apktool` (unpack/repack for
resource- and smali-level patching); `dex2jar` + a Java decompiler (JD-GUI, or Bytecode Viewer's
bundled one) as an alternative decompilation path when jadx struggles with a specific
obfuscation. **MobSF** for an automated static+dynamic baseline (run first, then go manual for
anything it can't reason about). `drozer` for exercising exported components from another app's
perspective — the dynamic complement to `mobile-static-agent.md`'s static component review.
**Frida** for runtime instrumentation; **objection** wraps the common Frida-based bypasses
(pinning, root detection) so you're not rewriting the same script every engagement. `adb` for the
baseline: install, logcat, shell access, `pm dump` for permissions and exported components.

### 3.7 Mobile — iOS

`class-dump` for Objective-C class/method signatures from a Mach-O binary; `otool`/`jtool2` for
low-level Mach-O inspection. Hopper or IDA for the disassembly itself. **Frida** and **objection**
again — the same pinning/root(jailbreak)-detection bypass workflow as Android, targeting
`SecTrustEvaluate`/`NSURLSession` delegates instead. **Needle** is the iOS-focused equivalent of
`drozer` — a structured framework for the common iOS security checks (keychain dumping, URL
scheme testing, ATS configuration review). **Passionfruit** for a GUI-driven static+dynamic
baseline. A jailbroken device or **Corellium** (virtual iOS devices, commercial) is usually
required for full dynamic coverage — `bagbak`/`Clutch` decrypt an App Store binary as the first
step on a device that has one installed.

### 3.8 Cross-cutting

`nmap` for network/service discovery when a binary target exposes a network-facing daemon.
`Wireshark`/`tshark` for protocol-level traffic analysis — the binary-side equivalent of a HAR
capture. `Docker` for standing up an isolated, disposable copy of the target rather than fuzzing
or instrumenting a shared/production instance. `Metasploit` for a known-module exploitation path
once a specific, identified CVE is confirmed present — rarely the discovery tool, occasionally the
fastest way to build a proof.

---

## Wiring tool output into an engagement

Two different wiring shapes, by whether a tool is safe and local (no target network access,
no active-testing permission needed) or requires one:

**Auto-run.** `slither`/`aderyn` need nothing but the source already on disk — `sieve xray web3`
launches them itself the moment they're on PATH; no flag needed. Override only to point at a report
you already generated with non-default flags, or to opt out entirely:

```
sieve xray web3                                                      # auto-runs slither + aderyn
sieve xray web3 --slither custom-run.json                            # use this instead of auto-running
sieve xray web3 --no-auto-static                                     # skip both — coverage-debt, recorded
```

**Operator-supplied.** Everything that touches a live target (web recon output, an OpenAPI/HAR
capture) needs the engagement's active-testing permission and a network call this skill never
issues on its own — run the real tool yourself, then hand Sieve the file:

```
sieve xray web --openapi api-docs/openapi.json --har burp-export.har --url-list all-urls.txt
```

A tool's absence is coverage-debt, printed in the final report's Coverage section
(`report-formatting.md`), never a silent pass. "Not tested" and "tested, clean" stay two different
sentences.
