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
native binary/mobile app — built to be paired with real tooling. Sieve doesn't scan, crawl, fuzz,
or disassemble anything itself: it teaches an agent which real tool to reach for (see
[`references/local-tooling.md`](references/local-tooling.md)), how to read its output, and the
discipline — a six-gate judge, evidence-or-silence, a scope fence, and a machine that decides what
counts as *confirmed* — that turns tool output and hunches into a small number of proven findings
instead of a pile of noise.

It covers Solidity, Vyper, Move, Anchor/Solana, and Cairo on the web3 side, every common web
framework, and native/mobile binaries — and it enforces its own rules at the harness level (a
Claude Code Stop hook, a stdlib-only CLI that refuses shortcuts) rather than only asking the model
nicely. Methodology attribution: [`CREDITS.md`](CREDITS.md).

## Start here

| If you're... | Read |
|---|---|
| New to the skill | [`SKILL.md`](SKILL.md) — the controller: full lifecycle, exact orchestration turns |
| Wondering what the `sieve` command is for | [What the CLI is for](#what-the-cli-is-for) below |
| Setting it up | [`setup.md`](setup.md) |
| Wiring in Burp/Slither/Ghidra/etc. | [`references/local-tooling.md`](references/local-tooling.md) |
| Looking for the rules every agent follows | [`references/shared-rules.md`](references/shared-rules.md) |
| Curious how "confirmed" is decided | [`references/validation.md`](references/validation.md) |
| Running a full engagement | [`references/campaign.md`](references/campaign.md) |
| Looking for a specific lens agent | [`agents/README.md`](agents/README.md) — the roster table |

## What the CLI is for

Sieve is two things that only work together: **markdown the agent reads** (the method — how to think, what
to hunt, what counts as evidence) and **a small command-line tool the agent runs** (`sieve …`, pure Python
standard library, no install). The markdown is the brain. The CLI is the **spine** — the part that does
not trust the brain to police itself. It never scans a target and never calls a model. It does the
bookkeeping and the refusing:

| Job | Commands | Why a tool and not a sentence in a prompt |
|---|---|---|
| **Remember** | `sieve init`, `status`, `phase`, the `.sieve/` folder | Context windows reset. State on disk is the source of truth; `sieve status` always names the next step |
| **Fence** | `sieve fence`, the scope card | Nothing is touched that `case.md` doesn't list; proof runs are fence-checked too; fails closed |
| **Prepare** | `sieve xray`, `frontier seed`, `bundle` | Runs Slither/Aderyn first, greps the entry points, builds every agent's briefing and prints its size — so "I built the bundles" can't be narrated |
| **Keep going** | the Stop hook, `frontier`, `ladder`, `rollcall`, `absorb` | A queue of work that only drains with receipts; a dead end needs three different attempts; the hook blocks "want me to continue?" |
| **Check the agents' work** | `merge`, `rollcall`, `cites` | Parses what agents wrote; re-reads every `file:line` by code; demotes hedged or proofless "findings" to leads |
| **Decide what's real** | `judge`, `prove run`, `verify` | Re-executes the proof with a negative control, checks seals and hashes; `confirmed` is *computed*, never typed |
| **Run the campaign** | `campaign init/run/next/submit/status/dashboard` | A DAG of reasoning steps with schema-checked hand-offs and a live dashboard |
| **Learn** | `kb`, `vault` | Confirmed findings, false positives and dead ends become cards the next engagement reads first (Obsidian-ready) |
| **Report** | `report`, `finish` | Prints the machine's tier for each finding, plus everything that was skipped |
| **Set up** | `doctor`, `install`, `lint`, `hooks install` | Tells you which real tools are missing and how to install them |

## What makes it different

- **"Confirmed" is a computed value.** A finding is confirmed only when the tool itself re-ran its
  proof several times, a **negative control stayed silent** (ideally the same command against a copy
  of the target with the fix applied — a fake PoC can't survive that), every citation was re-read by
  code, the code hasn't drifted, and a verifier who didn't find it signed off. The report prints that
  tier and ignores whatever the file claims. ([`references/validation.md`](references/validation.md))
- **A campaign, not a checklist.** `sieve campaign` runs a topology of ~70 nodes — x-ray and static rules,
  threat model, goal plan, eight independent invariant lenses merged, a dynamic strategy node, looped
  specialist hunts, a roaming pass, a triage panel with quorum, a deterministic reportability gate,
  machine-run proofs, an independence audit — each agent's output validated against a versioned contract
  before the next step sees it. ([`references/campaign.md`](references/campaign.md))
- **Real tools, not reimplementations — and few of them.** Burp driven over its MCP server covers
  most of the web stack; `sieve install <pack>` installs the rest from one table. No custom Solidity
  parser, no custom web crawler — the x-ray's mechanical layer greps, counts, runs
  Slither/Aderyn/trailmark itself, and merges structured output real tools already produced. Their
  findings feed in as leads, gated exactly like anything else.
- **Persistence is enforced, not requested.** `sieve hooks install` registers a Stop hook that
  blocks the agent from ending a turn while the engagement's work queue (`.sieve/frontier.tsv`) has
  open rows — and calls out a permission-seeking ending ("would you like me to continue?") by name.
  A dead end needs a receipt: three attempts across three genuinely different approaches
  (`sieve ladder`), or it isn't dead yet.
- **A real gate.** Six sequential gates (`references/judging.md`) — refutation, reachability,
  trigger, invariant/intent, impact, proof — run by verifiers that never gated their own discovery,
  by quorum when a finding is complex.
- **A knowledge base that compounds — and shows you the graph.** Local markdown cards wired for
  Obsidian (`sieve vault init`: wikilinks, class/domain hubs, an engagement graph), a rate-limited
  Solodit/OSV broker, and `sieve kb writeback` growing the store from confirmed findings, killed
  hypotheses *and* rejected false positives; your own misses become lessons the next engagement reads first.
- **A method for seeing what nobody else does.** Invariants derived through independent lenses,
  an asymmetry checklist, history-driven hunting, and a roaming pass for the classes no lens was
  looking for (`references/hypothesis-craft.md`) — inside bright lines the agent must follow exactly.
- **Three packs, one seam-hunting pass.** `references/crossover.md` — the highest-value bugs
  usually live where a web control gates a web3 privilege, or a native binary underwrites a
  contract's guarantee.

## Layout

Five things to actually run (`SKILL.md`, `AGENTS.md`, `setup.md`, `sieve.yaml`, `bin/sieve`) at the
root; everything else groups under one of five directories — the method (`references/`), the
hunters (`agents/`, `packs/`), the campaign (`campaigns/`), the engine (`sieve/`), and everything
that isn't markdown or Python (`kb/`, `templates/`, `scripts/`, `assets/`).

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
│   ├─ hypothesis-craft.md    invariants, asymmetric thinking, learning from history, the roaming pass
│   ├─ judging.md              the six-gate judge — what each gate asks
│   ├─ validation.md           how "confirmed" becomes machine-checked (proofs, controls, seals, tiers)
│   ├─ xray.md                 mechanical-then-narrative x-ray discipline
│   ├─ dispatch.md             classic passes: bundle → dispatch → rollcall → merge → absorb
│   ├─ campaign.md             the topology-driven campaign: nodes, contracts, profiles, dashboard
│   ├─ scope-intake.md         turning a dropped target into `.sieve/case.md`
│   ├─ knowledge.md            KB prior-art sweep + write-back
│   ├─ crossover.md            the seven cross-pack seam shapes
│   ├─ report-formatting.md    the finding-file contract and what the assembler prints
│   ├─ cvss-guide.md           scoring judgment — deliberately no calculator
│   ├─ property-fuzzing.md     the invariant-handler pattern for fuzz suites
│   └─ local-tooling.md        one best tool per job — with the install command for each
│
├─ agents/README.md       THE ROSTER — every lens agent, ★-marked core vs. deep, bundle spec
├─ packs/                 THE HUNTERS — one directory per domain, same shape in each
│   ├─ web3/    {agents/*.md × 12, vectors/*.md, judging.md}
│   ├─ web/     {agents/*.md × 9,  vectors/*.md, judging.md}
│   ├─ binary/  {agents/*.md × 7,  vectors/*.md, judging.md}      native + mobile
│   └─ seams/   {agents/crossover-agent.md}                        cross-pack seam hunter
│
├─ campaigns/             THE CAMPAIGN — copied per engagement to .sieve/campaign/ and editable there
│   ├─ campaign.yml           the topology (nodes, dependencies, contracts, profiles smoke/default/exhaustive)
│   ├─ prompts/*.md           one editable prompt per agent node (threat model, lenses, strategy, triage, prove…)
│   └─ rules/{web3,web,binary}.yml    ~55 static anti-pattern rules — hits become frontier rows
│
├─ sieve/                 THE ENGINE — stdlib-only Python, mechanical work only
│   ├─ main.py · __main__.py          CLI dispatch
│   ├─ cli_core.py                    init/phase/pass/status/ladder/frontier(+seed)/hook/finish
│   ├─ cli_pass.py · pipeline.py · merge.py · seed.py · blocks.py    bundle/dispatch/rollcall/merge/absorb
│   ├─ cli_validate.py · validate.py · judging.py · cites.py         verify / prove run / judge — deterministic validation
│   ├─ cli_campaign.py · campaign.py · campaign_actions.py · campaign_schema.py · campaign_rules.py · dashboard.py
│   ├─ cli_kb.py                      kb index/search/get/osv/use/add/lesson/prime/writeback/doctor
│   ├─ cli_vault.py · vault.py        Obsidian wiring: knowledge vault + engagement graph
│   ├─ cli_setup.py · tooling.py      doctor / install / lint, driven by references/local-tooling.md
│   ├─ cli_xray.py · cli_report.py
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
