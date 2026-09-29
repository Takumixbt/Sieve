# Local tooling — the real tools this skill drives

Sieve does not scan, fuzz, crawl, or disassemble anything itself. Every actual capability below
is a real, independently-maintained tool the operator installs; Sieve's job is knowing which one
to reach for, how to wire its output into the engagement, and how to treat what it says (a lead,
never a finding — the gate in `judging.md` still decides).

`sieve doctor` probes for everything on this page and prints what's present, what's missing, and
which classes of bug degrade to coverage-debt without it (`shared-rules.md` F7). Nothing here is
required to start an engagement; a missing tool is recorded, never silently skipped.

Install commands assume Linux/macOS with a package manager on PATH; `setup.md` has the exact
per-OS commands including native Windows/PowerShell.

---

## Web

### Burp Suite — the core of the web strand

Burp is the proxy of record: every authenticated request the agent needs to replay, every
multi-identity comparison (the sibling rule — `agents/access-control-agent.md`), every race
condition (`agents/race-condition-agent.md`) goes through it or through something driven from it.
Community edition covers manual replay and Repeater; Professional adds Intruder concurrency
control (needed for real race testing) and the extension ecosystem below.

**Extensions, by what they're for:**

| Extension | Use it for |
|---|---|
| **Autorize** | The sibling rule, automated: replay every request under a lower-privilege session and flag the ones that still succeed. Runs continuously in the background while you browse as the higher-privileged user. |
| **AuthMatrix** | A structured authorization matrix (roles × endpoints) when Autorize's single-session model isn't enough — multi-tenant apps, more than two privilege levels. |
| **Turbo Intruder** | True concurrent request firing for race-condition proof (`agents/race-condition-agent.md`'s proof oracle). A single-threaded send is not a proof; this is. |
| **Param Miner** | Hidden/unlinked parameters and headers, and the cache-poisoning workflow (unkeyed input detection). |
| **JS Link Finder** / **GAP** | Endpoint extraction from JS bundles — the "read the JS, find the API the UI doesn't show you" step, done properly instead of with a regex. |
| **Backslash Powered Scanner** | Finds injection-shaped behavior (not payload-shaped) — catches filters the payload-based active scanner misses. |
| **JWT Editor** | `alg:none`, key confusion, `kid` injection, signature stripping — the concrete moves in `agents/access-control-agent.md`'s JWT section. |
| **Logger++** | Full request/response history with filtering — the evidence trail a finding's `proof:` field cites. |
| **ActiveScan++** | Extends the built-in scanner's coverage (host header attacks, more SSRF/SSTI shapes). |
| **Retire.js** | Flags outdated JS libraries with known CVEs while you browse — feeds `agents/supply-chain-agent.md`. |
| **Collaborator Everywhere** | Auto-inserts Burp Collaborator payloads into every request for passive OAST coverage (blind SSRF, XXE) without hand-placing them. |
| **Hackvertor** | Payload encoding/transformation chains for WAF-adjacent testing. |
| **Piper** | Pipes traffic through external CLI tools (nuclei, custom scripts) from inside Burp. |

Burp's own Collaborator (or a self-hosted `interactsh-client`) is the proof oracle for blind
SSRF, blind XXE, and async injection — "the request was accepted" is never proof; a Collaborator
hit is.

### Recon chain

```
subfinder -d target.com -silent | httpx -silent -sc -title -tech-detect \
  | tee live-hosts.txt
katana -u live-hosts.txt -silent -jc | tee crawled-urls.txt
gau target.com | tee historical-urls.txt
cat crawled-urls.txt historical-urls.txt | sort -u > all-urls.txt
```

`subfinder`/`amass` (subdomains) → `httpx` (liveness, tech fingerprint, status) → `katana`
(active crawl, JS-aware) + `gau`/`waybackurls` (historical URLs) → `nuclei` (templated CVE/
misconfig sweep against the live set). Feed `all-urls.txt` straight into
`sieve xray web --url-list all-urls.txt` to seed the surface table; export a Burp project or a
DevTools/mitmproxy HAR and pass it as `--har` for the authenticated portion no crawler reaches.

### Active testing

`ffuf` (directory/parameter fuzzing, virtual-host discovery), `sqlmap` (SQL injection
confirmation — never the discovery step, only confirmation of a lead already narrowed by hand or
by Burp), `dalfox` (XSS scanning with real browser-based confirmation, cuts false positives
against a pure-regex approach).

### Install

```
go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install github.com/projectdiscovery/httpx/cmd/httpx@latest
go install github.com/projectdiscovery/katana/cmd/katana@latest
go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install github.com/ffuf/ffuf/v2@latest
pip install sqlmap        # or: git clone --depth 1 https://github.com/sqlmapproject/sqlmap
go install github.com/hahwul/dalfox/v2@latest
go install github.com/lc/gau/v2/cmd/gau@latest
```

Burp Suite itself and its extensions install from the BApp Store inside the app, or
`portswigger.net/burp` for the jar.

---

## Web3

### Static analysis — corroboration, not the x-ray

`slither` and `aderyn` run over the same source Sieve's x-ray enumerates. Their detector output
is a **lead list**, exactly like a Solodit precedent (`knowledge.md`): real signal, gated before
it ships. Sieve's own x-ray never depends on either being installed — `xray_web3.py` only greps
for candidate entry points and counts nSLOC/tests, precisely because a static analyzer's absence
must never silently shrink the x-ray (`shared-rules.md` F7).

```
slither . --json .sieve/xray/slither.json
aderyn . --output .sieve/xray/aderyn.json
```

Fold every High/Medium finding into the hit list at PRIME (`learning-loop.md`), tagged
`source: slither` / `source: aderyn`, and gate it exactly like any other lead — a detector
finding is not a finding until it clears `judging.md`.

`semgrep --config p/solidity` (or a hand-written rule from `security-arsenal`-style rule packs)
is the right tool for a specific anti-pattern once you know its shape — the "what changed" method
in `knowledge.md` step 4 ("grep your target's source for that same anti-pattern") is often a
one-line semgrep rule instead of a manual grep sweep.

### Dynamic proof

| Tool | Use |
|---|---|
| **Foundry** (`forge`) | The default PoC harness: a fork test that demonstrates the exploit end-to-end is the strongest proof a web3 finding can carry (`judging.md` Gate 1). |
| **Echidna** / **Medusa** | Property-based fuzzing once an invariant is stated (`references/property-fuzzing.md`, `templates/InvariantHandler.t.sol`). Medusa parallelizes natively; Echidna has the longer track record and corpus tooling. |
| **Mythril** | Symbolic execution — different coverage than the fuzzers, good for arithmetic and reachability questions on standalone functions. |
| **Halmos** | Symbolic testing directly on Foundry test files — fast to add if the project already has Foundry tests. |
| **Certora** (if licensed) | Formal specification when a property must hold for *all* inputs, not just the ones a fuzzer reached. |

### Install

```
curl -L https://foundry.paradigm.xyz | bash && foundryup
pip install slither-analyzer
cargo install aderyn                 # or: curl ... | bash, see aderyn's own installer
pip install mythril
pip install semgrep
# Echidna / Medusa: download the release binary for your platform from their GitHub releases
```

---

## Binary and mobile

### Triage

`checksec` (mitigations: NX, PIE, canary, RELRO, Fortify — the binary-gate's first line),
`file`/`strings` for a first pass, `readelf`/`objdump`/`nm` (already on most systems) for
symbols and sections.

### Reverse engineering

**Ghidra** (free, scriptable, the default for anything without an IDA license) or
**radare2**/**rizin** (faster for quick triage, better for scripting a repeated task) or **IDA**
where a license exists. Pick Ghidra when depth matters more than speed; radare2 when you need to
script the same triage step across many binaries.

### Fuzzing

**AFL++** for native C/C++/Rust targets with a fuzzable entry point; **libFuzzer** when the
target already builds as a fuzz harness (Rust's `cargo fuzz`, Go's native fuzzing, C++ via
`-fsanitize=fuzzer`). A crash without a sanitizer (ASan/UBSan) built in is a much weaker proof —
build with `-fsanitize=address,undefined` before fuzzing whenever the target allows it.

### Mobile

| Tool | Use |
|---|---|
| **jadx** | Java/Kotlin decompilation from an APK — the first read for any Android target. |
| **apktool** | Unpack/repack for resource-level and smali-level patching. |
| **MobSF** | Automated static+dynamic baseline (manifest issues, hardcoded secrets, known-bad configs) — run it first, then go manual for anything it can't reason about. |
| **Frida** | Dynamic instrumentation: hook a method, bypass a root/SSL-pinning check to observe real traffic, dump runtime state. |
| **objection** | A Frida-powered CLI that wraps the common mobile bypasses (pinning, root detection, keychain dumping) so you're not writing the same Frida script every engagement. |
| **adb** | The baseline: install, logcat, shell access, `pm dump` for permissions and exported components. |

### Install

```
sudo apt install checksec binutils file       # or: brew install checksec binutils
# Ghidra: download from https://github.com/NationalSecurityAgency/ghidra/releases
brew install radare2                          # or: apt install radare2
git clone https://github.com/AFLplusplus/AFLplusplus && cd AFLplusplus && make
pip install frida-tools objection
brew install jadx apktool android-platform-tools   # adb ships in platform-tools
# MobSF: docker run -p 8000:8000 opensecurity/mobile-security-framework-mobsf
```

---

## Wiring tool output into an engagement

Everything above lands as a file; Sieve only ever reads files it's told about — nothing here
calls out to a tool on its own:

```
sieve xray web3 --slither .sieve/xray/slither.json --aderyn .sieve/xray/aderyn.json
sieve xray web --openapi api-docs/openapi.json --har burp-export.har --url-list all-urls.txt
```

A tool's absence is coverage-debt, printed in the final report's Coverage section
(`report-formatting.md`), never a silent pass. "Not tested" and "tested, clean" stay two
different sentences.
