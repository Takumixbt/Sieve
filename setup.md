# Setup

Sieve's own orchestration layer needs nothing beyond Python 3.9+ and `git`, plus a POSIX `sh` for proof commands (on
Windows, the one Git for Windows installs). The real security tooling it drives is installed from one table
(`references/local-tooling.md`) by one command. Install what your engagements need; `sieve doctor` tells you what is
missing, per pack.

## 1. The skill itself

```bash
git clone https://github.com/Takumixbt/Sieve ~/Projects/Sieve
```

**As a Claude Code skill** (the way it is meant to be run: you drop a target link and the agent drives everything):

```bash
# macOS / Linux
ln -s ~/Projects/Sieve ~/.claude/skills/sieve
# Windows (PowerShell, no admin needed for a junction)
New-Item -ItemType Junction -Path "$HOME\.claude\skills\sieve" -Target "$HOME\Projects\Sieve"
```

**The command line** (the skill calls it; you can too):

```bash
export PATH="$HOME/Projects/Sieve/bin:$PATH"   # POSIX: bin/sieve
# Windows: add %USERPROFILE%\Projects\Sieve\bin to PATH: bin\sieve.cmd works in cmd and PowerShell
python bin/sieve.py banner                     # works everywhere, no PATH needed
sieve hooks install --scope user               # registers the persistence Stop hook (Claude Code)
```

`python -m sieve <command>` from the skill's directory also works. Set `SIEVE_PYTHON` to pick a specific interpreter for
the launchers.

## 2. The tooling: one command per pack

```bash
sieve install prereq          # go, pipx, cargo, uv, docker: dry run: prints the commands
sieve install prereq --run    # ...and executes the missing ones (asks first; --yes to skip)

sieve install web             # subfinder, httpx, katana, gau, ffuf, nuclei, trufflehog, sqlmap, cloakbrowser + Burp steps
sieve install web3            # foundry, slither, aderyn, trailmark, semgrep, heimdall, halmos, echidna, medusa
sieve install web3-chains --only anchor   # per-chain toolchains, only what the target uses
sieve install binary          # checksec, binwalk, Ghidra, r2, gdb+pwndbg, AFL++, pwntools, jadx, frida, MobSF...
```

Every command is a dry run unless you pass `--run`. Tools that cannot be installed by a command (Burp Suite, its BApp
extensions, Ghidra) print as manual steps with what to download. `sieve doctor` re-checks everything, including tools that
landed in `~/.cargo/bin`, `~/go/bin`, `~/.foundry/bin` or `~/.local/bin` before your shell's `PATH` knew about them.

**Burp MCP (web):** install Burp Suite Pro, add **MCP Server** from the BApp Store, then point your harness at it. For
Claude Code, `claude mcp add --transport http burp http://127.0.0.1:13337` (use the host and port the extension's MCP tab
shows, and put the same value in `tools.burp.mcp` in `sieve.yaml`). Add Autorize, Turbo Intruder, Param Miner, JWT Editor, HTTP Request Smuggler and InQL from the same BApp Store.

**CloakBrowser (web recon):** `pip install cloakbrowser`, then once, headed, to sign the dedicated test identity in:

```bash
python scripts/browser-recon.py --setup --proxy http://127.0.0.1:8080   # proxy optional: routes the browser through Burp
```

Use a dedicated test mailbox and, for a dApp, a dedicated test wallet with an extension loaded by `--extension DIR`;
never a production identity. The profile lives in `~/.sieve/browser/`. An identity a previous tool left in `~/.helix` is
adopted in place. If a proxy is configured and is not running, the browser cannot load pages and the node records the gap
as coverage debt.

## 3. Knowledge base and Obsidian

```bash
sieve kb ingest               # public precedents, no API key: DeFi exploits, contest findings, HackerOne, KEV, OSV, ...
sieve kb sources              # what is loaded and when
sieve vault init              # create the Sieve vault (root note, graph colours, KB scaffold, vector notes)
sieve vault path              # where it is
```

The vault is `$SIEVE_VAULT`, else `vault.root` in `sieve.yaml`, else `Sieve Vault` in Documents (OneDrive's Documents
when that is where Documents lives). Open that folder in Obsidian (*Open folder as vault*) and start at `Sieve.md`.
Obsidian is optional: the vault is plain markdown. Solodit is optional too: with a `CYFRIN_API_KEY` set,
`sieve kb search --online` adds it; without one nothing changes.

## 4. Verify

```bash
sieve doctor
sieve hooks status
sieve selftest --fast         # the skill's own tests: no network, no real target (about two minutes; drop --fast for the full profile)
```

Then a real dry run on any small contract or app you own:

```bash
sieve scan ./my-project       # detects packs, runs the x-ray, rules, precedents, seeds the frontier, recommends a depth
sieve campaign init           # uses the recommendation
sieve status
```

## Configuration

`sieve.yaml` at the skill root holds the defaults (vault location, knowledge-base sources and limits, persistence
budget, report format). Override per user in `~/.sieve/sieve.yaml`, per engagement in `<target>/.sieve/sieve.yaml`; later
files win, merged key by key. Environment variables: `SIEVE_VAULT`, `SIEVE_USER_HOME` (default `~/.sieve`),
`SIEVE_BROWSER_HOME`, `SIEVE_OFFLINE=1` (no outbound knowledge-base calls), `SIEVE_NO_STATIC=1` (skip the auto-invoked
analyzers), `SIEVE_PYTHON`.
