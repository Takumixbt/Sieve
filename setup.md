# Setup

Sieve's own orchestration layer needs nothing beyond Python 3.9+ and a POSIX shell (or native
PowerShell on Windows). Everything below is the real security tooling it drives — install what
your engagements actually need; `sieve doctor` tells you what's missing and for which pack.

## 1. The skill itself

```bash
git clone <this-repo> ~/.sieve/skill      # or wherever your harness looks for skills
export PATH="$HOME/.sieve/skill/bin:$PATH"   # add to your shell profile
sieve banner                               # confirms the install
sieve hooks install --scope user           # registers the persistence Stop hook (Claude Code)
```

On native Windows PowerShell (no WSL): `python3` must resolve; run
`python -m sieve <command>` from the skill's directory in place of the `sieve` shim, or add a
`sieve.ps1` wrapper that does the same `PYTHONPATH` + `python -m sieve` dispatch as `bin/sieve`.

## 2. Knowledge base (optional, recommended for web3)

```bash
export CYFRIN_API_KEY=...     # solodit.cyfrin.io -> profile menu -> API Keys -> generate
sieve kb doctor --live        # confirms the key works with one real, cheap query
```

No key → `sieve kb search --online` reports the missing-key error clearly and every other command
still works against the local/seed cards. `sieve kb osv` (OSV.dev) needs no key at all.

## 3. Real tooling, by pack

Full roster and Burp extension list: `references/local-tooling.md`. Quick install:

```bash
# --- Web ---
go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install github.com/projectdiscovery/httpx/cmd/httpx@latest
go install github.com/projectdiscovery/katana/cmd/katana@latest
go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install github.com/ffuf/ffuf/v2@latest
go install github.com/lc/gau/v2/cmd/gau@latest
go install github.com/hahwul/dalfox/v2@latest
pip install sqlmap
# Burp Suite: download from portswigger.net/burp; install extensions from the BApp Store inside the app.

# --- Web3 ---
curl -L https://foundry.paradigm.xyz | bash && foundryup
pip install slither-analyzer mythril semgrep
cargo install aderyn
# Echidna / Medusa: grab the release binary for your platform from their GitHub releases.

# --- Binary / mobile ---
sudo apt install checksec binutils file        # macOS: brew install checksec binutils
brew install radare2 jadx apktool android-platform-tools   # or your distro's equivalents
git clone https://github.com/AFLplusplus/AFLplusplus && cd AFLplusplus && make
pip install frida-tools objection
# Ghidra: download from https://github.com/NationalSecurityAgency/ghidra/releases
# MobSF: docker run -p 8000:8000 opensecurity/mobile-security-framework-mobsf
```

`sieve doctor` re-checks all of the above and tells you exactly what's still missing.

## 4. Verify

```bash
sieve doctor
sieve hooks status
mkdir -p /tmp/sieve-smoke && cd /tmp/sieve-smoke
sieve init . --pack web3 --lab --quiet
sieve status
```

You should see the engagement created, phase `init`, and a `NEXT:` line telling you to fill in
`.sieve/case.md`. Delete `/tmp/sieve-smoke` when done — it's a throwaway smoke test, not a real
engagement.

## Configuration

`sieve.yaml` at the skill root holds the defaults (KB endpoints, rate limits, persistence budget,
report format). Override per-user in `~/.sieve/sieve.yaml`, per-engagement in
`<target>/.sieve/sieve.yaml` — later files win, merged key by key. See the comments in the shipped
`sieve.yaml` for every setting.
