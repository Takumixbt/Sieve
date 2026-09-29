# Setup

Sieve's own orchestration layer needs nothing beyond Python 3.9+ and a POSIX shell (or PowerShell on
Windows). The real security tooling it drives is installed from one table
(`references/local-tooling.md`) by one command. Install what your engagements need; `sieve doctor`
tells you what's missing, per pack.

## 1. The skill itself

```bash
git clone <this-repo> ~/.sieve/skill      # or wherever your harness looks for skills
export PATH="$HOME/.sieve/skill/bin:$PATH"   # add to your shell profile
sieve banner                               # confirms the install
sieve hooks install --scope user           # registers the persistence Stop hook (Claude Code)
```

On native Windows PowerShell (no WSL): `python3` must resolve; run `python -m sieve <command>` from
the skill's directory in place of the `sieve` shim, or add a `sieve.ps1` wrapper that does the same
`PYTHONPATH` + `python -m sieve` dispatch as `bin/sieve`.

## 2. The tooling — one command per pack

```bash
sieve install prereq          # go, pipx, cargo, uv, docker — dry run: prints the commands
sieve install prereq --run    # ...and executes the missing ones (asks first; --yes to skip)

sieve install web             # subfinder, httpx, katana, gau, ffuf, nuclei, trufflehog, sqlmap + Burp steps
sieve install web3            # foundry, slither, aderyn, trailmark, semgrep, heimdall, halmos, echidna, medusa
sieve install web3-chains --only anchor   # per-chain toolchains, only what the target uses
sieve install binary          # checksec, binwalk, Ghidra, r2, gdb+pwndbg, AFL++, pwntools, jadx, frida, MobSF...
```

Every command is dry-run unless you pass `--run`. Tools that can't be installed by a command (Burp
Suite, its BApp extensions, Ghidra, CloakBrowser) print as manual steps with what to download.
`sieve doctor` re-checks everything, including tools that landed in `~/.cargo/bin`, `~/go/bin`,
`~/.foundry/bin` or `~/.local/bin` before your shell's `PATH` knew about them.

**Burp MCP (web):** install Burp Suite Pro, add **MCP Server** from the BApp Store, then point your
harness at it — for Claude Code, `claude mcp add --transport sse burp http://127.0.0.1:9876` (check
the host and port on the extension's MCP tab first). Add Autorize, Turbo Intruder, Param Miner, JWT
Editor, HTTP Request Smuggler, and InQL from the same BApp Store.

## 3. Knowledge base and Obsidian

```bash
export CYFRIN_API_KEY=...     # solodit.cyfrin.io -> profile menu -> API Keys -> generate
sieve kb doctor --live        # confirms the key works with one real, cheap query
sieve vault init              # ~/.sieve/kb becomes an Obsidian vault: vector notes, hubs, linked cards
```

No key → `sieve kb search --online` reports the missing-key error clearly and every other command still
works against the local/seed cards. `sieve kb osv` needs no key. Obsidian is optional: open
`~/.sieve/kb` (and, per engagement, `.sieve/vault/` after `sieve vault export`) with *Open folder as
vault* to get the graph.

## 4. Verify

```bash
sieve doctor
sieve hooks status
mkdir -p /tmp/sieve-smoke && cd /tmp/sieve-smoke
sieve init . --pack web3 --lab --quiet
sieve status
```

You should see the engagement created, phase `init`, and a `NEXT:` line telling you to fill in
`.sieve/case.md`. Delete `/tmp/sieve-smoke` when done — it's a throwaway smoke test.

## Configuration

`sieve.yaml` at the skill root holds the defaults (KB endpoints, rate limits, persistence budget,
report format). Override per-user in `~/.sieve/sieve.yaml`, per-engagement in
`<target>/.sieve/sieve.yaml` — later files win, merged key by key. See the comments in the shipped
`sieve.yaml` for every setting.
