# AGENTS.md — how an agent installs, boots, and operates Sieve

This is the host-capability contract: what Sieve needs from the harness it's running on, and how
it degrades when something is missing. Read this once per new environment, not per engagement.

## Requirements

- **Python ≥ 3.9** on PATH as `python3` — Sieve's CLI (`sieve/`) is stdlib-only; no `pip install`
  is required for the skill's own orchestration layer.
- **`git`**, **`jq`** (optional but recommended), a POSIX shell (or PowerShell on native Windows —
  `setup.md` has the exact per-OS commands).
- **A background/parallel-agent dispatch capability** (Claude Code's `Task`/`Agent` tool, or the
  harness's equivalent). Without it, see "No-fanout" below.

## The real security tools

None of them are required to *start* an engagement — `sieve doctor` reports what's present, and
every missing tool is recorded as coverage-debt in the report, never a silent skip
(`references/shared-rules.md`, `judging.md`). See `references/local-tooling.md` for the full roster
and `setup.md` for install commands (`sieve install <pack>` runs them from the same table `sieve doctor` checks). Depth scales with what's installed: a web engagement with no
Burp available still runs (passive recon, source-level review) but can't confirm anything requiring
live traffic; a web3 engagement with no Foundry still runs the reasoning-based hunt but can't
produce a fork-test proof for Gate 6.

## Booting

1. `sieve doctor` — prints installed/missing tools per pack, KB API key status
   (`kb.sources.*.api_key_env` in `sieve.yaml`), and whether the Stop hook is registered.
2. `sieve hooks install --scope user` (once, per machine) — registers the persistence Stop hook in
   Claude Code's settings. Idempotent; safe to run again. See `references/shared-rules.md`'s
   persistence section for why this exists.
3. `sieve init <target> --pack <web3,web,binary>` — starts an engagement; see `SKILL.md`'s
   lifecycle from here.

## No-fanout (the harness can't dispatch parallel sub-agents)

Run the roster **sequentially** instead of in parallel, and persist state to `.sieve/` continuously
— each agent writes its raw findings to disk as it finishes, so a context reset loses nothing and
`sieve --continue` resumes cleanly. `.sieve/`, not the context window, is the source of truth.
Chunk a large target by subsystem rather than trying to hold the whole thing in one context.

## No Stop-hook support (a harness other than Claude Code)

The persistence doctrine in `references/shared-rules.md` still applies — it's a discipline, not
only a mechanism. Without the hook, treat `sieve status`'s frontier count as the thing you check
before ending any turn, manually, every time. `sieve run` (if the harness supports a headless
re-invoke loop) can substitute for hook-enforced persistence by re-entering the agent until the
frontier drains.

## Capability probing at preflight

Before dispatching anyone, confirm and print:

```
[ ] .sieve/case.md exists, scope resolved (not invented), fence explicit
[ ] active-testing permission known and honored (case.md rules.active_testing)
[ ] fanout capability detected (parallel Task/Agent dispatch, or sequential fallback above)
[ ] tool roster probed (sieve doctor) — absences recorded as coverage-debt
[ ] Stop hook registered (sieve hooks status) — or the manual-check fallback above is in effect
[ ] shared-rules.md, methodology.md, judging.md, local-tooling.md actually read this turn
```

An unprinted checklist is an unrun one — this is the same discipline `SKILL.md`'s Turn-based
orchestration exists to enforce, applied to preflight specifically.

## Network egress

Sieve's own network calls are limited to `sieve kb` (Solodit, OSV, optionally NVD — all through the
rate-limited broker in `sieve/kb_net.py`) and the version-agnostic tools it shells out to. If egress
is sandboxed or proxied, `sieve kb doctor --live` confirms reachability without spending a real
query; `SIEVE_OFFLINE=1` disables all outbound KB calls and falls back to local cards only.
