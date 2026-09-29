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
native binary/mobile app — built to be paired with real tooling, not to replace it. Sieve doesn't
scan, crawl, fuzz, or disassemble anything itself: it teaches an agent which real tool to reach for
(Burp Suite, subfinder/httpx/katana, Slither/Aderyn/Foundry/Echidna, Ghidra/radare2/Frida — see
[`references/local-tooling.md`](references/local-tooling.md)), how to read its output, and the
discipline — a six-gate judge, evidence-or-silence, a scope fence — that turns tool output and
hunches into a small number of proven findings instead of a pile of noise.

It covers Solidity, Vyper, Move, Anchor/Solana, and Cairo on the web3 side, every common web
framework, and native/mobile binaries — and it enforces its own anti-laziness rules at the harness
level (a Claude Code Stop hook — see below) rather than only asking the model nicely. Methodology
attribution: [`CREDITS.md`](CREDITS.md).

## Start here

| If you're... | Read |
|---|---|
| New to the skill | [`SKILL.md`](SKILL.md) — the controller: full lifecycle, exact orchestration turns |
| Setting it up | [`setup.md`](setup.md) |
| Wiring in Burp/Slither/Ghidra/etc. | [`references/local-tooling.md`](references/local-tooling.md) |
| Looking for the rules every agent follows | [`references/shared-rules.md`](references/shared-rules.md) |
| Looking for a specific lens agent | [`agents/README.md`](agents/README.md) — the roster table |

## What makes it different

- **Real tools, not reimplementations.** No custom Solidity parser, no custom web crawler — the
  x-ray's own mechanical layer (`sieve xray`) only greps, counts, and merges structured output
  real tools already produced. Slither/Aderyn findings and Burp/subfinder/katana output feed in as
  corroborating leads, gated exactly like anything else.
- **Persistence is enforced, not requested.** `sieve hooks install` registers a Stop hook that
  blocks the agent from ending a turn while the engagement's work queue (`.sieve/frontier.tsv`) has
  open rows — and calls out a permission-seeking ending ("would you like me to continue?") by name.
  A dead end needs a receipt: three attempts across three genuinely different approaches
  (`sieve ladder`), or it isn't dead yet.
- **A real gate.** Six sequential gates (`references/judging.md`) — refutation, reachability,
  trigger, invariant/intent, impact, proof — run by a verifier that never gated its own discovery.
  Confidence is computed by the agent per a fixed arithmetic, never inflated to hit a payout tier.
- **A knowledge base that compounds.** Local markdown cards, a rate-limited Solodit/OSV broker
  (so twelve parallel agents never blow either API's real limit), and `sieve kb writeback` growing
  the store from every engagement's confirmed findings.
- **Three packs, one seam-hunting pass.** `references/crossover.md` — the highest-value bugs
  usually live where a web control gates a web3 privilege, or a native binary underwrites a
  contract's guarantee.

## Layout

Five things to actually run (`SKILL.md`, `AGENTS.md`, `setup.md`, `sieve.yaml`, `bin/sieve`) at the
root; everything else groups under one of four directories — the method (`references/`), the
hunters (`agents/`, `packs/`), the engine (`sieve/`), and everything that isn't markdown or Python
(`kb/`, `templates/`, `scripts/`, `assets/`).

```
Sieve/
├─ SKILL.md               the controller — lifecycle, orchestration turns, non-negotiables
├─ AGENTS.md              host-capability contract: what a harness must give this skill
├─ README.md              this file
├─ CREDITS.md             the one place methodology/tooling lineage is named
├─ CHANGELOG.md · LICENSE · VERSION
├─ setup.md               install, per OS
├─ sieve.yaml             engagement config — quotas, thresholds, KB sources, persistence budgets
├─ bin/sieve              entry point (`./bin/sieve ...` or `python3 -m sieve ...`)
│
├─ references/            THE METHOD — read in full, every engagement
│   ├─ shared-rules.md        the contract every dispatched agent operates under
│   ├─ methodology.md         completeness contract, mental tools, creativity techniques
│   ├─ judging.md              the six-gate judge
│   ├─ xray.md                 mechanical-then-narrative x-ray discipline
│   ├─ dispatch.md             bundle assembly, parallel-spawn mechanics
│   ├─ scope-intake.md         turning a dropped target into `.sieve/case.md`
│   ├─ knowledge.md            KB prior-art sweep + write-back
│   ├─ crossover.md            the seven cross-pack seam shapes
│   ├─ report-formatting.md    the assembler's rules
│   ├─ cvss-guide.md           scoring judgment — deliberately no calculator
│   ├─ property-fuzzing.md     the invariant-handler pattern for fuzz suites
│   └─ local-tooling.md        the full external tool roster, by domain
│
├─ agents/README.md       THE ROSTER — every lens agent, ★-marked core vs. deep, bundle spec
├─ packs/                 THE HUNTERS — one directory per domain, same shape in each
│   ├─ web3/    {agents/*.md × 12, vectors/*.md, judging.md}
│   ├─ web/     {agents/*.md × 8,  vectors/*.md, judging.md}
│   ├─ binary/  {agents/*.md × 7,  vectors/*.md, judging.md}      native + mobile
│   └─ seams/   {agents/crossover-agent.md}                        cross-pack seam hunter
│
├─ sieve/                 THE ENGINE — stdlib-only Python, mechanical work only
│   ├─ main.py · __main__.py          CLI dispatch
│   ├─ cli_core.py                    init/phase/pass/status/ladder/frontier/hook/finish
│   ├─ cli_kb.py                      kb index/search/get/osv/use/add/prime/writeback/doctor
│   ├─ cli_xray.py · cli_report.py · cli_setup.py
│   ├─ state.py · config.py · fence.py · frontier.py · hook.py
│   ├─ kb_store.py · kb_net.py · vectors.py
│   ├─ xray_web3.py · xray_web.py · xray_git.py
│   └─ report.py · flow.py · util.py · yamlish.py · banner.py
│
├─ kb/                    seed knowledge — the real vault lives at `~/.sieve/kb/`
│   ├─ README.md
│   └─ seed/cards/*.md         shipped examples, `status: seed`, never auto-promoted
├─ templates/InvariantHandler.t.sol    the property-fuzzing starter template
├─ scripts/generate_svg.py             architecture-diagram generator (vendored, MIT — CREDITS.md)
└─ assets/banner-art.txt               the BOLD SIEVE banner source
```

## For authorized use only

This skill assumes an engagement the operator owns or has explicit written permission to test —
a bug bounty program, a contracted pentest, a security audit, or a target you own. Every scope
boundary comes from `.sieve/case.md`; nothing in this skill invents or widens scope on its own.
