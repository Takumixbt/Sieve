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

It's methodologically built on [Pashov Audit Group's skills](https://github.com/pashov/skills)
(MIT; see [`CREDITS.md`](CREDITS.md)), generalized from Solidity-only to web3's other VMs plus web
and binary/mobile, and extended with a persistence engine that enforces its own anti-laziness rules
at the harness level (a Claude Code Stop hook — see below) rather than only asking the model
nicely.

## Start here

- **New to the skill?** [`SKILL.md`](SKILL.md) is the controller — the full lifecycle and the exact
  orchestration turns.
- **Setting it up?** [`setup.md`](setup.md).
- **Wiring in Burp/Slither/Ghidra/etc.?** [`references/local-tooling.md`](references/local-tooling.md).
- **Just want the rules every agent follows?** [`references/shared-rules.md`](references/shared-rules.md).

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

```
SKILL.md                the controller
AGENTS.md               host-capability contract (what a harness needs to give this skill)
setup.md                install
references/             the method: shared-rules, methodology, judging, xray, dispatch,
                         scope-intake, knowledge, crossover, report-formatting, cvss-guide,
                         local-tooling
agents/README.md        the roster and bundle spec
packs/{web3,web,binary}/agents/*.md    the lenses
packs/{web3,web,binary}/vectors/*.md   the fast-recall attack catalog (parseable cards)
packs/{web3,web,binary}/judging.md     pack-specific gate additions
packs/seams/agents/crossover-agent.md  the cross-pack seam hunter
sieve/                  the orchestration CLI (stdlib-only Python) — state, frontier, hooks,
                         KB, x-ray enumerators, report assembler
scripts/generate_svg.py architecture-diagram generator (vendored from Pashov Audit Group, MIT)
kb/seed/                a starting set of local knowledge cards
tests/                  the CLI's own test suite (run: python3 -m unittest discover -s tests)
```

## For authorized use only

This skill assumes an engagement the operator owns or has explicit written permission to test —
a bug bounty program, a contracted pentest, a security audit, or a target you own. Every scope
boundary comes from `.sieve/case.md`; nothing in this skill invents or widens scope on its own.
