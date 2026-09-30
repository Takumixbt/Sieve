# Local tooling - one best tool per job

Sieve doesn't scan, fuzz, crawl, or disassemble anything itself. Everything below is a real tool the
operator installs; Sieve decides where to point it and what its output means - a lead, gated by
`judging.md`, never a finding on its own.

**The rule for this file: one best tool per job, and nothing that a tool already on the list does.**
Burp Suite, driven over its MCP server, is the web hub - so no separate proxy, no separate replay
tool, no separate OAST server, no separate JWT or race-condition tool. A missing tool is coverage-debt
in the report (`shared-rules.md`), never a silent skip.

**Install everything for a pack in one go:** `sieve install web` · `sieve install web3` ·
`sieve install binary` (prints commands; add `--run` to execute the missing ones). The install column
below is the single source - `sieve install` and `sieve doctor` both read it. Prerequisites first:

<!-- install:prereq -->
| Tool | Job | Install |
|---|---|---|
| `go` | Go toolchain - most recon tools install through it | `sudo apt install -y golang-go` (macOS: `brew install go`) |
| `pipx` | isolated installs for Python CLIs | `sudo apt install -y pipx && pipx ensurepath` (macOS: `brew install pipx`) |
| `cargo` | Rust toolchain - aderyn, cosmwasm-check, others | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh -s -- -y` |
| `uv` | fast Python tool/venv manager (trailmark) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `docker` | MobSF and other containerised tools | `sudo apt install -y docker.io` (macOS: Docker Desktop) |

---

## 1 · Web

### 1.1 Recon & discovery

<!-- install:web -->
| Tool | Job | Install |
|---|---|---|
| `subfinder` | Passive subdomain enumeration - the default; add `amass` only when it's exhausted | `go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest` |
| `httpx` | Live-host probing, fingerprinting, status/title/tech - also screenshots (`-screenshot`) | `go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest` |
| `katana` | JS-aware crawler - endpoints and parameters from a live app | `CGO_ENABLED=1 go install github.com/projectdiscovery/katana/cmd/katana@latest` |
| `gau` | Historical URLs (Wayback, Common Crawl, OTX) - forgotten endpoints | `go install github.com/lc/gau/v2/cmd/gau@latest` |
| `ffuf` | Content/API-route and vhost discovery | `go install github.com/ffuf/ffuf/v2@latest` |
| `nuclei` | Templated CVE/misconfig sweep - every hit is a lead, never a finding | `go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest` |
| `trufflehog` | Secrets in repos, history, and JS - verifies whether a credential is live, so only run verification where scope allows | `curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh \| sh -s -- -b ~/.local/bin` |
| `cloakbrowser` | Stealth Chromium (Playwright drop-in) driven by the `browser-recon` campaign node: real-client capture of XHR, WebSocket frames, storage and forms, for SPAs, auth walls and challenge pages. Persistent test identity, optional Burp proxy | `pip install cloakbrowser` (the first launch downloads the Chromium build) |

Name clash: on machines with the Python `httpx` package installed its `httpx` command can shadow ProjectDiscovery's. If `httpx -version`
prints `Usage: httpx [OPTIONS] URL`, call `httpx-pd` (a copy of `~/go/bin/httpx`); `sieve preflight` checks for this.

Bundled scripts (stdlib Python, no install): `scripts/browser-recon.py` (the CloakBrowser driver above; `--setup` signs the
dedicated test identity in once), `scripts/js-recon.py` (endpoints, source maps, secrets and JWTs out of minified JS, as a
receipt rather than a guess), `scripts/race.py` (barrier-synced parallel requests to prove a check-then-act race; it
refuses to fire unless the scope fence lists the host and active testing is permitted) and `scripts/secrets-sweep.sh` (a
dependency-free floor when trufflehog is absent). Every hit is a lead, never a finding.

Also worth an occasional look, nothing to install: certificate-transparency search (`crt.sh`),
Shodan/Censys for exposed infrastructure, `dnstwist`-style lookalike checks on brand-scoped
programs. Parameter discovery, hidden headers, and unkeyed-input hunting are **Param Miner** (1.2),
not a separate CLI.

### 1.2 Interception & manual testing - Burp Suite + MCP

**Burp Suite Professional is the proxy of record.** Every authenticated replay, every multi-identity
comparison, every race, every OAST callback goes through it - driven by the agent over the
**Burp MCP server** (PortSwigger's official extension), so the agent can send requests, search proxy
history, and hand requests to Repeater/Intruder without leaving the session. Built-in features
cover what other tools would otherwise be added for: **Collaborator** (out-of-band/blind SSRF, XXE,
injection), **DOM Invader** in Burp's browser (DOM XSS, postMessage, prototype pollution), the
**Logger** tab (the evidence trail a finding's `proof:` cites), and the **Scanner** (a lead source,
like `nuclei`). Burp Community covers manual replay only - race testing and Collaborator need Pro.

<!-- install:burp -->
| Tool | Job | Install |
|---|---|---|
| Burp Suite Pro | The proxy, scanner, Collaborator, Repeater/Intruder | manual - download from portswigger.net/burp |
| Burp MCP Server | Lets the agent drive Burp | BApp Store → **MCP Server** → enable it, then in Claude Code: `claude mcp add --transport http burp http://<host>:<port>` with the host and port the extension's MCP tab shows (this machine: `http://127.0.0.1:13337`; set it as `tools.burp.mcp` in `sieve.yaml`). `sieve preflight` checks it answers |
| Autorize | The sibling rule, automated: replay everything as a lower-privilege session and flag what still succeeds | BApp Store → Autorize |
| Turbo Intruder | Genuinely concurrent requests - the only acceptable proof of a race | BApp Store → Turbo Intruder |
| Param Miner | Hidden parameters/headers and unkeyed-input (cache-poisoning) detection | BApp Store → Param Miner |
| JWT Editor | `alg` confusion, `kid` injection, signature stripping, key attacks | BApp Store → JWT Editor |
| HTTP Request Smuggler | Desync/smuggling detection and exploitation, HTTP/1 and HTTP/2 | BApp Store → HTTP Request Smuggler |
| InQL | GraphQL schema recovery and query generation | BApp Store → InQL |

That's the whole list. Hackvertor, ActiveScan++, Logger++, Retire.js and similar overlap something
above; add one only when a specific engagement needs it and say why in `.sieve/assumptions.md`.

### 1.3 Confirmation

<!-- install:web-confirm -->
| Tool | Job | Install |
|---|---|---|
| `sqlmap` | Confirms and characterises a SQL injection Burp or a hand test already found - never discovery | `pipx install sqlmap` |

Everything else people reach for here - XSS confirmation (Burp's browser + DOM Invader), blind/OOB
(Collaborator), SSRF payloads (Collaborator + a hand-built request), CORS and cache probes (Param
Miner + Repeater), TLS review (rarely pays), JWT tooling (JWT Editor) - is already covered in 1.2.

---

## 2 · Web3

### 2.1 Static analysis - the x-ray's first move

`sieve xray web3` auto-runs `slither`, `aderyn`, and `trailmark` (when installed) before any manual
reading (`references/xray.md` Phase 0) - install all three; their outputs disagree often enough that
skipping one is a coverage gap.

<!-- install:web3 -->
| Tool | Job | Install |
|---|---|---|
| `forge` | Foundry - build, test, fork tests (the PoC harness), plus `cast`/`anvil` for on-chain calls and local forks | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| `slither` | Default detector pass; auto-run | `pipx install slither-analyzer` |
| `aderyn` | Independent detector set; auto-run alongside slither | `cargo install aderyn` |
| `trailmark` | Builds a call/reference graph once so "who calls X / blast radius" are queries, not re-reads; auto-run | `uv tool install trailmark` |
| `semgrep` | Once you know an anti-pattern's shape, a one-line rule beats a manual sweep - the "what changed" method's step 4 | `pipx install semgrep` |
| `heimdall` | Bytecode: decompile/disassemble/CFG, and `dump` for a deployed contract's real storage layout (catches proxy storage collisions even on verified targets) | `curl -L http://get.heimdall.rs \| bash && bifrost` |
| `halmos` | Symbolic testing straight from existing Foundry tests | `pipx install halmos` |
| `echidna` | Property fuzzing, longest track record (`references/property-fuzzing.md`) | `brew install echidna` (Linux without brew: release binary from `github.com/crytic/echidna`) |
| `medusa` | Property fuzzing that parallelises natively - pick one of echidna/medusa per target, run the other only if the first converges clean | `go install github.com/crytic/medusa@latest` |

Symbolic execution (`mythril`) is deliberately absent: `halmos` on the invariants you derived beats
a whole-codebase run. Unverified/bytecode-only targets: `heimdall` decompiles, and every resulting
finding carries `confidence: heuristic` (`scope-intake.md`).

### 2.2 Dynamic proof

`forge` is the proof harness: a fork test that reproduces the exploit end to end is the strongest
proof a web3 finding can carry (`judging.md` Gate 6); `anvil` forks mainnet state locally and `cast`
does the one-off calls. Fuzzers (`echidna`/`medusa`) come *after* you've stated a property.

### 2.3 Other chains - install only what the target uses

<!-- install:web3-chains -->
| Tool | Job | Install |
|---|---|---|
| `solana` | Solana CLI + local validator | `sh -c "$(curl -sSfL https://release.anza.xyz/stable/install)"` |
| `anchor` | Anchor build/test for Solana programs | `cargo install --git https://github.com/coral-xyz/anchor avm --force && avm install latest && avm use latest` |
| `sui` | Sui Move build/test/prover (long compile) | `cargo install --locked --git https://github.com/MystenLabs/sui.git --branch mainnet sui` |
| `aptos` | Aptos Move build/test/prover | `curl -fsSL "https://aptos.dev/scripts/install_cli.py" \| python3` |
| `cosmwasm-check` | Validates a compiled CosmWasm contract against chain capabilities | `cargo install cosmwasm-check` |
| `caracal` | Cairo/Starknet static analyzer - Slither's closest equivalent | `cargo install --git https://github.com/crytic/caracal --profile release --force` |

Algorand, Substrate, and TON are covered by vector cards (`packs/web3/vectors/cross-chain-and-altvm.md`)
and each chain's own toolchain; install them per engagement.

### 2.4 On-chain intelligence - nothing to install

Block explorers for verified source and history; **Sourcify** when an explorer lacks the source;
`cast 4byte`/OpenChain to resolve selectors; **Dune** for "has this exact pattern happened here";
**DeFiLlama** for TVL/composability context; Solodit through `sieve kb search --online`.

---

## 3 · Binary & mobile

### 3.1 Triage

<!-- install:binary -->
| Tool | Job | Install |
|---|---|---|
| `checksec` | Mitigations first, always: NX, PIE, canary, RELRO, Fortify - it changes what "found" means | `sudo apt install -y checksec` (macOS: `brew install checksec`) |
| `binwalk` | Firmware images: extract filesystems, find embedded keys and certs | `sudo apt install -y binwalk` |

`file`, `strings`, `readelf`, `objdump`, `nm` (binutils) come with the OS.

### 3.2 Reverse engineering - static

| Tool | Job | Install |
|---|---|---|
| Ghidra | Default disassembler/decompiler - free, scriptable (needs a JDK) | manual - release zip from `github.com/NationalSecurityAgency/ghidra`, plus `sudo apt install -y openjdk-21-jdk` |
| `r2` | radare2 - fast triage and scripting a repeated task across many binaries | `git clone https://github.com/radareorg/radare2 ~/tools/radare2 && ~/tools/radare2/sys/install.sh` |

IDA Pro or Binary Ninja instead of Ghidra where you hold a licence; the workflow is the same.

### 3.3 Dynamic analysis

| Tool | Job | Install |
|---|---|---|
| `gdb` | The debugger | `sudo apt install -y gdb` |
| pwndbg | GDB made exploit-aware: heap inspection, ASLR-aware breakpoints | `curl -qsL 'https://install.pwndbg.re' \| sh -s -- -t pwndbg-gdb` |
| `valgrind` | Memory-error detection when a rebuild with sanitizers isn't possible | `sudo apt install -y valgrind` |

Sanitizers (`-fsanitize=address,undefined`) ship with the compiler - build the target with them
whenever you can rebuild; a crash without one is a much weaker proof.

### 3.4 Fuzzing

| Tool | Job | Install |
|---|---|---|
| `afl-fuzz` | AFL++ - coverage-guided fuzzing for anything with a fuzzable entry point | `sudo apt install -y afl++` |

`libFuzzer` (`-fsanitize=fuzzer`), `cargo fuzz`, and Go's native fuzzing come with their toolchains.

### 3.5 Exploit development

Python libraries live in one shared virtualenv so nothing collides:
`python3 -m venv ~/.sieve/venv` first (`sieve install binary` does it).

| Tool | Job | Install |
|---|---|---|
| pwntools | Process interaction, payload and ROP-chain construction (its ROP module replaces standalone gadget finders) | `python3 -m venv ~/.sieve/venv && ~/.sieve/venv/bin/pip install pwntools` |
| angr | Symbolic execution when a path question beats fuzzing | `python3 -m venv ~/.sieve/venv && ~/.sieve/venv/bin/pip install angr` |

### 3.6 Mobile - Android and iOS

Traffic goes through Burp (1.2); the pinning bypass below is what unlocks it.

| Tool | Job | Install |
|---|---|---|
| `jadx` | First read of any APK - Java/Kotlin decompilation | `brew install jadx` (Linux without brew: release zip from `github.com/skylot/jadx`) |
| `apktool` | Unpack/repack for resources and smali-level patching | `sudo apt install -y apktool` |
| `adb` | Install, logcat, shell, exported-component and permission dumps | `sudo apt install -y adb` |
| `frida` | Runtime instrumentation - the core of dynamic mobile work, Android and iOS | `pipx install frida-tools` |
| `objection` | The common Frida bypasses (pinning, root/jailbreak detection) pre-built | `pipx install objection` |
| MobSF | Automated static+dynamic baseline - run first, then go manual; every result is a lead | `docker run -d --name mobsf -p 8000:8000 opensecurity/mobile-security-framework-mobsf:latest` |

iOS additionally needs a jailbroken device or Corellium (commercial) for full dynamic coverage;
Frida and objection are the same tools, hooking `SecTrustEvaluate`/`NSURLSession` instead of
`X509TrustManager`. A Flutter app's logic sits in a compiled Dart snapshot that jadx can't read -
check for `libapp.so` first and reach for a Dart-snapshot decompiler.

---

## Windows notes

`sieve install <pack>` uses Linux and macOS commands from the tables above; on Windows it swaps in native routes where
one exists (`winget` for jadx and adb, `pipx` for checksec, `cargo` for binwalk, a `~/.sieve/venv` for pwntools and angr).
Everything else has one of three homes, and `sieve doctor` / `sieve preflight` look in all of them:

- **native**: on PATH, or in `~/.cargo/bin`, `~/go/bin`, `~/.local/bin`, `~/.sieve/venv/Scripts`, winget's package folders
- **`~/tools/`**: portable installs that need no admin rights: `jdk-21/`, `ghidra_*/`, `jadx/`, with wrappers in
  `~/tools/bin/` (`ghidra-headless.cmd` for agent-driven analysis, `ghidra.cmd`, `jadx.cmd`) that set `JAVA_HOME` and forward
  their arguments. Put `~/tools/bin` on PATH, or call the wrapper by full path
- **WSL**: Foundry, Halmos, radare2, AFL++, valgrind, gdb and checksec are typically present. Run them as
  `wsl -e bash -lc '<cmd>'` and reach project files under `/mnt/c/...`. The first WSL probe cold-starts the distro (a couple
  of minutes) and is then cached for a day in `~/.sieve/wsl-tools.json`

Two things need you: `pwndbg` (its installer wants your WSL `sudo` password) and MobSF (Docker Desktop must be running to
pull and start it). Burp's BApps are installed from Burp's own BApp Store; `sieve preflight` reads which ones Burp has loaded.

## Not listed on purpose

ZAP, mitmproxy, nikto, hydra, wpscan, testssl.sh, dalfox, jwt_tool, Corsy, arjun, LinkFinder,
gowitness, sqlmap-alternatives, `mythril`, Wake, 4naly3er, surya/sol2uml, panoramix, ItyFuzz, Certora,
ROPgadget/ropper/one_gadget/angrop, Hopper, class-dump, Needle, drozer (`adb` + Frida cover it),
YARA, Metasploit, EMBA. Each overlaps something above or rarely changes an outcome. If an engagement
truly needs one, add it in `.sieve/assumptions.md` with the reason - don't grow this list.

## Wiring tool output into an engagement

Two shapes, by whether a tool is local and safe or touches a live target:

```
sieve xray web3                                   # auto-runs slither + aderyn + trailmark
sieve xray web3 --slither run.json                # use a report you already generated
sieve xray web3 --no-auto-static                  # skip auto-run - recorded as coverage-debt
sieve xray web --openapi api.json --har burp.har --url-list urls.txt   # live-target output you collected
```

Anything that touches a live target needs the engagement's active-testing permission
(`.sieve/case.md`) and a network call this skill never issues on its
own - run the real tool yourself, then hand Sieve the file. A tool's absence is coverage-debt,
printed in the report's Coverage section (`report-formatting.md`), never a silent pass: "not
tested" and "tested, clean" stay two different sentences.
