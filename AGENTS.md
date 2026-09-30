# AGENTS.md: how an agent installs, boots and operates Sieve

This is the host-capability contract: what Sieve needs from the harness it is running on, and how it degrades when
something is missing. Read it once per new environment, not per engagement. The operator's only input is a target; the
agent runs everything else (`SKILL.md`).

## Requirements

- **Python 3.9 or newer.** Sieve's CLI (`sieve/`) is stdlib-only; no `pip install` is needed for the orchestration
  layer. Launchers: `bin/sieve` (POSIX), `bin/sieve.cmd` (Windows cmd and PowerShell) and `python bin/sieve.py`
  (anywhere). `python -m sieve` works from the skill directory.
- **`git`**, and **a POSIX `sh`**. The proof runner executes PoC commands under `sh -c`; on Windows that is the shell
  Git for Windows installs (or WSL's), found automatically. `git` or `patch` is needed for the strongest negative control
  (re-running a PoC against a patched copy of the target).
- **A background/parallel-agent dispatch capability** (Claude Code's `Agent` tool, or the harness's equivalent). Without
  it, see "No-fanout" below.
- **Optional but recommended**: `pip install cloakbrowser` (live-client recon for web targets), Burp Suite Pro with its
  MCP server, Foundry, Slither, Aderyn, Echidna or Medusa.

## Model routing

Maximum reasoning on everything that reasons: the lenses, the strategy node, every hunter, the triage panel, the prover
and the independence audit run on the strongest model available at its strongest effort. A missed critical costs far more
than the inference. Role separation, not model weakness, is what enforces discoverer-is-not-verifier: the panelists never
see each other's verdicts and `sieve judge` refuses a verifier who is in a finding's `found_by`. If the harness has only
one model, everything runs on it and nothing breaks. Keep the parent session for coordination and verification.

## The real security tools

None is required to *start* an engagement. `sieve doctor` reports what is present, and every missing tool is recorded
as coverage debt in the report, never a silent skip (`references/shared-rules.md`, `judging.md`).
`references/local-tooling.md` has the full roster and `sieve install <pack>` runs the install commands from the same
table `sieve doctor` checks. Depth scales with what is installed: a web engagement with no Burp still runs (passive
recon, source-level review) but cannot confirm anything requiring live traffic; a web3 engagement with no Foundry still
runs the reasoning-based hunt but cannot produce a fork-test proof for Gate 6.

## Booting

1. `sieve preflight`: exercises Burp (proxy, MCP, BApps), the CloakBrowser test identity and wallet extensions, the Burp and
   V12 MCP servers, the knowledge base, vault and Stop hook, and prints the fix for each gap. `sieve doctor` is the plain
   per-pack tool list. On Windows, tools that only exist in WSL are detected and count as present.
2. `sieve kb sources`, then `sieve kb ingest` once if the precedent tier is empty (no key needed).
3. `sieve vault init` once: creates the Sieve Obsidian vault (`$SIEVE_VAULT`, else `Sieve Vault` in Documents).
4. `sieve hooks install --scope user` once per machine: registers the persistence Stop hook in Claude Code's settings.
   Idempotent. See `references/shared-rules.md` for why it exists.
5. `sieve selftest --fast` if you want proof the install works (a couple of minutes, no network, no real target).
6. `sieve scan <target tree>` then `sieve campaign init`: `SKILL.md` from here.

## No-fanout (the harness cannot dispatch parallel sub-agents)

Run the roster **sequentially**: `sieve campaign next --only <node>` renders one campaign node at a time (and
`sieve dispatch --sequential` hands out one hunt agent at a time). State is persisted to `.sieve/` continuously; each
agent writes its output to disk as it finishes, so a context reset loses nothing and `sieve status` resumes cleanly.
`.sieve/`, not the context window, is the source of truth. Chunk a large target by subsystem rather than holding it all
in one context.

## No Stop-hook support (a harness other than Claude Code)

The persistence doctrine in `references/shared-rules.md` still applies; it is a discipline, not only a mechanism.
Without the hook, treat `sieve status` as the thing you check before ending any turn, every time: the turn is not over
while it names a `NEXT` that is not `Campaign complete`. A harness with a headless re-invoke loop can substitute for
hook-enforced persistence by re-entering the agent until `sieve status` reports the engagement done.

## Capability probing at preflight

Before dispatching anyone, confirm and print:

```
[ ] .sieve/case.md exists, scope resolved (not invented), fence explicit
[ ] active-testing permission known and honored (case.md rules.active_testing)
[ ] fanout capability detected (parallel Agent dispatch, or the sequential fallback above)
[ ] tool roster probed (sieve doctor); absences recorded as coverage debt
[ ] Stop hook registered (sieve hooks status), or the manual-check fallback above is in effect
[ ] proof runner available: a POSIX sh, plus git (or patch) for `sieve prove run --control-patch`
[ ] web target: CloakBrowser importable and the test identity signed in (scripts/browser-recon.py --setup), or the gap noted
[ ] shared-rules.md, methodology.md, hypothesis-craft.md, judging.md, validation.md, local-tooling.md actually read this turn
[ ] `sieve scan` printed its recommendation and `sieve campaign init` printed its agent-run count
```

An unprinted checklist is an unrun one.

## Network egress

Sieve's own network calls are limited to: `sieve kb ingest` (public datasets, on demand), `sieve kb osv` and the optional
Solodit lookup (both through the rate-limited broker in `sieve/kb_net.py`), the tools it shells out to, the
`browser-recon` node (only URLs the fence lists, only when active testing is permitted), and the PoC commands
`sieve prove run` executes, which may only talk to hosts the scope fence lists, and only when `rules.active_testing` is
true (`references/validation.md`). The campaign dashboard listens on `127.0.0.1` only. `SIEVE_OFFLINE=1` disables every
outbound knowledge-base call and falls back to the local index.
