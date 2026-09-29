---
name: sieve
description: Multi-domain security audit skill — web3, web, and binary/mobile — for authorized engagements, built to be paired with real tooling (Burp Suite over its MCP server, the ProjectDiscovery recon set, Slither/Aderyn/Foundry, Ghidra/Frida) rather than replace it. Drop a target (a bounty program URL, a repo, a domain, a contract address, an APK/IPA/binary) and it scopes itself, runs a mechanical x-ray with static analysis first, dispatches specialist audit lenses per pack, hunts the seams between packs, gates every finding through a six-gate judge before it ships, learns from every engagement's wins and dead ends, and writes a report. Enforces its own persistence: a Stop hook blocks the agent from giving up or asking permission while work remains. Triggers on "/sieve", "audit this", "bug bounty", "pentest", or a dropped scope link.
---

```
███████╗██╗███████╗██╗   ██╗███████╗
██╔════╝██║██╔════╝██║   ██║██╔════╝
███████╗██║█████╗  ██║   ██║█████╗
╚════██║██║██╔══╝  ╚██╗ ██╔╝██╔══╝
███████║██║███████╗ ╚████╔╝ ███████╗
╚══════╝╚═╝╚══════╝  ╚═══╝  ╚══════╝
  web3  ·  web  ·  binary
  what survives the sieve is real
```

# Sieve

A security-audit skill for **any** target — a smart-contract protocol, a web app or API, or a
native binary/mobile app. Its conviction: **the intelligence lives in the agent's reasoning; the
work is done by real tools.** Sieve doesn't scan, crawl, fuzz, or disassemble anything itself. It
says which tool to reach for (`references/local-tooling.md` — one best tool per job), how to read its
output, how to think past it (`references/hypothesis-craft.md`), and the discipline that turns tool
output and hunches into a few proven, gate-checked findings.

## Print the banner first

Every run, before anything else: print the banner above exactly — or run `sieve banner`, which
prints the same art plus the installed version. If the entry point already printed it, don't print
it twice.

## How to operate — two modes at once

**On the bright lines, follow this skill exactly. On the open ground, think for yourself.**
`shared-rules.md` has the full table; the short version:

- *Bright lines* — the scope fence, cite-or-drop, proof-or-lead, the gates in order, discoverer ≠
  verifier, receipts for dead ends. No cleverness here; a persuasive reason to skip one is the
  warning sign, not the permission.
- *Open ground* — which hypotheses to form, which invariants matter, which asymmetry to chase, which
  tools to combine, which chain to try. Be strange here. **Creativity is spent on hypotheses, never
  on evidence.**

Persistence, learning from history, asymmetric thinking, and sharp invariants are what separate a
finding nobody else submitted from a duplicate — they're the point of the skill, not decoration.

## Usage

```
/sieve https://immunefi.com/bug-bounty/someprotocol/    # a bounty program
/sieve https://github.com/acme/contracts                # a repo (pack auto-detected)
/sieve acme.com                                          # a web target
/sieve 0xABC...DEF (ethereum)                            # a deployed contract
/sieve ./app-release.apk                                 # an APK (binary pack)
/sieve ./firmware.bin                                    # a native binary (binary pack)

/sieve --web3 <target>     # force a single pack
/sieve --web <target>
/sieve --binary <target>
/sieve --quick <target>    # core (★) agents only — see agents/README.md
/sieve --focus "<question>"  # research only an operator-named question (methodology.md Part 7)
/sieve --continue           # resume an interrupted engagement
```

A bare drop with no flag lets intake pick the pack(s) — `references/scope-intake.md`.

## The lifecycle

```
DROP A LINK
    │
    ▼
┌─────────┐  scope-intake.md -> .sieve/case.md (the fence) -> `sieve init`
│  INIT   │
└────┬────┘
     ▼
┌─────────┐  xray.md + `sieve xray <pack>` — static analysis first — then read, classify, derive
│  X-RAY  │  invariants through independent lenses, write architecture.json -> architecture.svg
└────┬────┘
     ▼
┌─────────┐  knowledge.md + `sieve kb prime` — precedent, the target's history, YOUR lessons
│  PRIME  │  -> .sieve/plan.md, the ranked hit list
└────┬────┘
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  HUNT — dispatch.md builds every bundle and spawns the roster in     │
│  parallel, `sieve pass N` per pass, `sieve frontier` drains the      │
│  queue; the last pass before convergence is the ROAMING PASS         │
└────┬───────────────────────────────────────────────────────────────┬─┘
     ▼                                                                ▼
┌───────────┐  two or more packs ran? -> crossover.md, packs/seams/agents/crossover-agent.md
│ CONVERGE  │
└────┬──────┘
     ▼
┌─────────┐  judging.md — restate-the-claim, triage, six gates, discoverer != verifier
│  GATE   │
└────┬────┘
     ▼
┌─────────┐  methodology.md Part 4 — every CONFIRMED finding is a root; chain it, find an
│ DEEPEN  │  alternate trigger, lower the precondition, before it's frozen at a severity
└────┬────┘
     ▼
┌─────────┐  judging.md Gate 6 — `sieve prove record <id> --oracle ... --evidence ...`
│  PROVE  │
└────┬────┘
     ▼
┌─────────┐  report-formatting.md — `sieve report` assembles report/report.md
│ REPORT  │
└────┬────┘
     ▼
┌─────────┐  `sieve kb writeback` (findings + dead ends) · post-mortem lessons · `sieve vault
│  LEARN  │  export` — the next engagement opens already knowing this stack's failure modes
└─────────┘
```

`sieve status` always names the current phase and the exact next command — read it whenever you're
unsure what to do next; do not improvise a different order.

## Orchestration — mechanical, not narrated

**A summary of these phases is not the same as running them.** An orchestrator that narrates "I did
intake, I hunted, I gated" without the tool calls ships findings that never passed `judging.md`.
Every turn below produces a printed, checkable artifact for exactly this reason.

**Turn 1 — read the core discipline**, in parallel: `shared-rules.md`, `methodology.md`,
`hypothesis-craft.md`, `judging.md`, `local-tooling.md`. In full, as distinct tool calls — not
absorbed from this file's summary. Run `sieve doctor`; missing tools are coverage-debt, named in the
report (`sieve install <pack>` prints the fix).

**Turn 2 — intake.** Follow `scope-intake.md`. `sieve init <target> --pack <web3,web,binary>`. Fill
in `.sieve/case.md` completely — `sieve phase xray` refuses to start otherwise. Print the resolved
scope (hosts/contracts/paths, active-testing permission) before proceeding.

**Turn 3 — x-ray.** `sieve phase xray`, then `xray.md` for every pack: `sieve xray <pack>` (web3
auto-runs Slither, Aderyn, and trailmark before you read a line), then read, classify, and write the
narrative files by hand — including the merged, ranked invariant list (`hypothesis-craft.md` §2).
Render the map (`sieve xray map`); run `sieve xray git` once. Seed the frontier from what you found:
`sieve frontier add <kind> <component> --pack <pack> --prio <n>` for every entry point, endpoint, or
boundary worth a dedicated look — an empty frontier after x-ray blocks `sieve phase prime`.

**Turn 4 — prime.** `sieve phase prime`, `sieve kb prime` (precedent **and your own lessons**), the
prior-art sweep (`knowledge.md`), the target's history (fix-commits, prior audit exclusions —
`hypothesis-craft.md` §4). Rank the hit list with the asymmetry sheet (§3); write `.sieve/plan.md`.

**Turn 5 — hunt.** `sieve phase hunt`, `sieve pass 1`. Build every bundle (`dispatch.md`), print
each one's line count, dispatch the full roster in **one message** as parallel background agents.
Wait for every completion notification — never poll; confirm every agent returned output or is named
as coverage-debt. Repeat `sieve pass N+1` until the frontier is drained. **Then run the roaming pass**
(`hypothesis-craft.md` §5) — three hypothesis classes nobody on the roster was looking for — and only
then declare convergence, with every roster agent having run in that final state.

**Turn 6 — crossover**, only if two or more packs produced raw output: `crossover.md` +
`packs/seams/agents/crossover-agent.md`.

**Turn 7 — gate.** `sieve phase gate`. Every candidate through `judging.md`, run by the orchestrator
or a dedicated verifier — never the actor that raised it. `sieve judge <id> --verdict ... --reason
...` records each verdict.

**Turn 8 — deepen.** `methodology.md` Part 4 on every CONFIRMED finding before it's frozen.

**Turn 9 — self-audit before shipping, unconditional.** Before any finding enters
`.sieve/findings/`, try to disprove it: re-read the cited `file:line`, re-send the request, re-run
the trace in a fresh tool call. Evidence that can't be reproduced right now demotes the finding to a
lead — the direct fix for the shipped-false-positive failure `shared-rules.md`'s tripwires exist to
prevent.

**Turn 10 — prove, report, learn.** `sieve phase prove`; `sieve prove record` for every C/H/M
finding. `sieve phase report`, `sieve report`. Then the five-minute post-mortem
(`hypothesis-craft.md` §4): `sieve kb lesson` for every false positive, miss, revived dead end, and
technique that paid; `sieve kb writeback`; `sieve vault export`; `sieve finish`.

## Persistence — `shared-rules.md` has the doctrine, the hook is the backstop

A Stop hook (`sieve hooks install`) blocks the turn from ending while the frontier has open rows and
the persistence budget isn't spent, and calls out a permission-seeking ending by name. Internalize
the doctrine (`shared-rules.md`, `methodology.md` Parts 0 and 6b) rather than treating the hook as
something to satisfy mechanically. `sieve status` shows the hook's state so you can tell a quiet
engagement from one where the hook was never wired in.

## References

| Group | Files (all under `references/`) | When |
|---|---|---|
| **Core discipline** | `shared-rules.md` · `methodology.md` · `hypothesis-craft.md` · `judging.md` · `local-tooling.md` | Turn 1, every engagement, in full |
| **Lifecycle mechanics** | `xray.md` · `dispatch.md` · `scope-intake.md` | the matching phase (x-ray / hunt / intake) |
| **Knowledge + seams** | `knowledge.md` · `crossover.md` | prime and learn; converge (≥2 packs ran) |
| **Closing an engagement** | `report-formatting.md` · `cvss-guide.md` | prove/report, per C/H/M finding |
| **Fuzz-suite support** | `property-fuzzing.md` | only when the target ships (or needs) property tests |

**Agents:** `agents/README.md` (roster and bundle spec), `packs/<pack>/agents/*.md` (the lenses),
`packs/<pack>/vectors/*.md` (fast-recall attack cards), `packs/<pack>/judging.md` (pack-specific gate
additions). **Setup:** `setup.md`; `AGENTS.md` for the host-capability contract. **Full tree:**
[`README.md`](README.md).

## Non-negotiables

```
EVIDENCE OR SILENCE       no finding without file:line, request/response, or a runnable PoC
DISCOVERER != VERIFIER    the actor that found it never gates its own finding
REAL TOOLS DO THE WORK    Burp/Slither/Ghidra/subfinder do the scanning; this skill decides where
                          to point them and what their output means
NEVER ASK PERMISSION      for a decision you can make — record it and continue (shared-rules.md)
A DEAD END NEEDS A RECEIPT   >=3 attempts on >=3 different ladder rungs, or it isn't dead yet
SCOPE IS THE FENCE        never touch what case.md didn't list
VERIFY, DON'T RECALL      names, flags, numbers, and "it doesn't exist" are checked in this turn
LEARN EVERY ENGAGEMENT    confirmed findings, killed hypotheses, and your own mistakes feed the next one
```
