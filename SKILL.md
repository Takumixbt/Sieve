---
name: sieve
description: Multi-domain security audit skill — web3, web, and binary/mobile — built to be paired with real tooling (Burp Suite, subfinder/httpx/katana, Slither/Aderyn/Foundry/Echidna, Ghidra/radare2/Frida) rather than replace it. Drop a target (a bounty program URL, a repo, a domain, a contract address, an APK/IPA/binary) and it scopes itself, runs a mechanical x-ray, dispatches specialist hunting agents per pack, hunts the seams between packs, gates every finding through a six-gate judge before it ships, and writes a report. Enforces its own persistence: a Stop hook blocks the agent from giving up or asking permission while work remains. Triggers on "/sieve", "audit this", "bug bounty", "pentest", or a dropped scope link.
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
native binary/mobile app — built on one conviction: **the intelligence lives in the agent's
reasoning, and the actual work is done by real tools.** Sieve does not scan, crawl, fuzz, or
disassemble anything itself. It teaches you which real tool to reach for
(`references/local-tooling.md`: Burp and its extensions, subfinder/httpx/katana, Slither/Aderyn/
Foundry/Echidna/Medusa, Ghidra/radare2/Frida/jadx), how to read its output, and the discipline that
turns a pile of tool output and hunches into a small number of proven, gate-checked findings.

## Print the banner first

Before anything else, every run: print the banner above exactly — or run `sieve banner`, which
prints the same art plus the installed version. If the entry point already printed it this run,
don't print it twice.

## Operating context

Read `references/shared-rules.md` in full before anything else — it is the contract every agent
this skill dispatches operates under: the anti-hallucination rule, the READ-ONLY discipline, the
persistence doctrine, and the universal finding format. Skimming it while reading this file is not
the same as reading it as its own turn.

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
/sieve --focus "<question>"  # research only an operator-named question (methodology.md Part 5)
/sieve --continue           # resume an interrupted engagement
```

A bare drop with no flag lets intake pick the pack(s) — `references/scope-intake.md`.

## Repository map

```
references/   the method (read Turn 1, in full)   │  packs/<pack>/   the hunters
agents/       the roster + bundle spec             │    agents/*.md     the lens files
sieve/        the engine (stdlib Python, mechanical)│    vectors/*.md    fast-recall attack cards
kb/           seed knowledge cards                  │    judging.md      pack-specific gate additions
```

Full tree with every file named: [`README.md`](README.md)'s Layout section. This is the compact
version — enough to know where to look without leaving this file.

## The lifecycle

```
DROP A LINK
    │
    ▼
┌─────────┐  scope-intake.md -> .sieve/case.md (the fence) -> `sieve init`
│  INIT   │
└────┬────┘
     ▼
┌─────────┐  xray.md + `sieve xray <pack>` -> facts.json, entry-points/invariants/authz,
│  X-RAY  │  architecture.json -> `sieve xray map` -> architecture.svg
└────┬────┘
     ▼
┌─────────┐  knowledge.md + `sieve kb prime` -> .sieve/plan.md, the ranked hit list
│  PRIME  │
└────┬────┘
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  HUNT — dispatch.md builds every bundle, spawns the pack's roster    │
│  in parallel (agents/README.md), `sieve pass N` per pass, `sieve     │
│  frontier` drains the work queue, repeat until it's empty            │
└────┬───────────────────────────────────────────────────────────────┬─┘
     ▼                                                                ▼
┌───────────┐  two or more packs ran? -> crossover.md, packs/seams/agents/crossover-agent.md
│ CONVERGE  │
└────┬──────┘
     ▼
┌─────────┐  judging.md — six gates, discoverer != verifier, `sieve judge <id> --verdict ...`
│  GATE   │
└────┬────┘
     ▼
┌─────────┐  methodology.md Part 3 — every CONFIRMED finding is a root; chain it, find an
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
┌─────────┐  `sieve kb writeback` — confirmed findings become KB cards; the next engagement
│  LEARN  │  opens already knowing this stack's failure modes
└─────────┘
```

`sieve status` always names the current phase and the exact next command — read it whenever you're
unsure what to do next; do not guess or improvise a different order.

## Orchestration — mechanical, not narrated

**A summary of these phases is not the same as running them.** This skill's own design history
includes an observed failure where an orchestrator narrated "I did intake, I hunted, I gated"
without the underlying tool calls ever happening — findings shipped that never actually passed
`judging.md` because the file was referenced, not read. Every phase below produces a printed,
checkable artifact for exactly this reason.

**Turn 1 — read the core discipline**, in parallel, before anything else: `shared-rules.md`,
`methodology.md`, `judging.md`, `local-tooling.md`. Read in full, as distinct tool calls — not
absorbed from skimming this file's summary of them.

**Turn 2 — intake.** Follow `scope-intake.md`. Run `sieve init <target> --pack <web3,web,binary>`.
Fill in `.sieve/case.md` completely before leaving this turn — `sieve phase xray` refuses to start
otherwise. Print the resolved scope (hosts/contracts/paths, active-testing permission) before
proceeding.

**Turn 3 — x-ray.** `sieve phase xray`, then follow `xray.md` for every pack in scope: run
`sieve xray <pack>` (feeding real tool output where available — Slither/Aderyn JSON, an OpenAPI
doc, a HAR export), read what it found, write the narrative files by hand, render the map
(`sieve xray map`). Run `sieve xray git` once, any pack. Seed the frontier from what you found:
`sieve frontier add <kind> <component> --pack <pack> --prio <n>` for every entry point, endpoint,
or attack-surface boundary worth a dedicated look — the frontier is what the persistence rules in
`shared-rules.md` and the Stop hook actually enforce against, so an empty frontier after x-ray is a
`sieve phase prime` blocker, not an oversight to skip past.

**Turn 4 — prime.** `sieve phase prime`, `sieve kb prime`, run the prior-art sweep
(`knowledge.md`), rank the hit list with `methodology.md`'s backward-critical pass, write
`.sieve/plan.md`.

**Turn 5 — hunt.** `sieve phase hunt`, `sieve pass 1`. Build every bundle (`dispatch.md`), print
each one's line count, dispatch the full roster in **one message** as parallel background agents.
Wait for every completion notification — never poll. `sieve rollcall`-equivalent: confirm every
dispatched agent returned output or is named as coverage-debt. Repeat `sieve pass N+1` until the
frontier is drained and a full pass adds nothing new (`dispatch.md`'s convergence rule — all roster
agents must have run in that state, never declared after a partial pass).

**Turn 6 — crossover**, only if two or more packs produced raw output: `crossover.md` +
`packs/seams/agents/crossover-agent.md`.

**Turn 7 — gate.** `sieve phase gate`. Every candidate through `judging.md`'s six gates, run by the
orchestrator or a dedicated verifier — never the actor that raised it. `sieve judge <id> --verdict
... --reason ...` records each verdict.

**Turn 8 — deepen.** `methodology.md` Part 3 on every CONFIRMED finding before it's frozen.

**Turn 9 — self-audit before shipping, unconditional.** Before any finding enters
`.sieve/findings/`, actively try to disprove it: re-read the cited `file:line`, re-send the
request, re-run the trace in a fresh tool call. A finding whose evidence can't be reproduced right
now is demoted to a lead — this is the direct fix for the shipped-false-positive failure mode
`shared-rules.md`'s anti-hallucination rule exists to prevent, applied one more time right before
the report locks it in.

**Turn 10 — prove, report, learn.** `sieve phase prove`, `sieve prove record` for every C/H/M
finding (`judging.md` Gate 6). `sieve phase report`, `sieve report`. `sieve kb writeback`. `sieve
finish`.

## Persistence — read `shared-rules.md`'s section, this is the enforcement

A Stop hook (`sieve hooks install`) blocks the turn from ending while the frontier has open rows and
the persistence budget isn't spent, and calls out a permission-seeking ending by name. It is a
backstop, not the method — internalize the doctrine in `shared-rules.md` and `methodology.md`
rather than treating the hook as something to satisfy mechanically. `sieve status` always shows the
hook's own state (installed? firing? how many blocks?) so you can tell a quiet engagement from one
where the hook was never wired in.

## References

| Group | Files | When |
|---|---|---|
| **Core discipline** | `shared-rules.md` · `methodology.md` · `judging.md` · `local-tooling.md` | Turn 1, every engagement, in full |
| **Lifecycle mechanics** | `xray.md` · `dispatch.md` · `scope-intake.md` | one per matching phase (x-ray / hunt / intake) |
| **Knowledge + seams** | `knowledge.md` · `crossover.md` | prime phase; converge phase (≥2 packs ran) |
| **Closing an engagement** | `report-formatting.md` · `cvss-guide.md` | prove/report phase, per C/H/M finding |
| **Fuzz-suite support** | `property-fuzzing.md` | only when the target ships (or needs) property tests |

All paths above are under `references/`.

**Agents:** `agents/README.md` (the roster and bundle spec), `packs/<pack>/agents/*.md` (the
lenses), `packs/<pack>/vectors/*.md` (the fast-recall attack catalog), `packs/<pack>/judging.md`
(pack-specific gate additions).

**Setup:** `setup.md` for install, `AGENTS.md` for the host-capability contract this skill expects.

## Non-negotiables

```
EVIDENCE OR SILENCE       no finding without file:line, request/response, or a runnable PoC
DISCOVERER != VERIFIER    the actor that found it never gates its own finding
REAL TOOLS DO THE WORK    Burp/Slither/Ghidra/subfinder do the scanning; this skill decides where
                          to point them and what their output means
NEVER ASK PERMISSION      for a decision you can make — record it and continue (shared-rules.md)
A DEAD END NEEDS A RECEIPT   >=3 attempts on >=3 different ladder rungs, or it isn't dead yet
SCOPE IS THE FENCE        never touch what case.md didn't list
LEARN EVERY ENGAGEMENT    confirmed findings and killed hypotheses both feed the next one
```
