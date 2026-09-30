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

An autonomous security-audit engine for **any** target: a smart-contract protocol, a web app or API, or a native/mobile
binary. You hand it a link. The agent driving it (Claude Code, run as a skill) does the rest: reads the bounty program,
builds the scope card, scans, runs a topology of about 70 reasoning and mechanical steps, dispatches the specialist agents,
gates every finding, **executes each proof with a negative control**, and writes a report that only calls something
confirmed when a machine says so.

Sieve does not scan, crawl, fuzz or disassemble anything itself. It tells the agent which real tool to reach for
([`references/local-tooling.md`](references/local-tooling.md)), how to read its output, how to think past it, and enforces the
discipline (a six-gate judge, evidence-or-silence, a scope fence, computed verdicts) that turns tool output and hunches into
a small number of proven findings instead of a pile of noise.

It covers Solidity, Vyper, Move, Anchor/Solana, Cairo and CosmWasm on the web3 side, every common web framework, and
native and mobile binaries.

## Start here

| If you are | Read |
|---|---|
| Running it | [`setup.md`](setup.md), then drop a target link into the session |
| The agent driving it | [`SKILL.md`](SKILL.md): the script, turn by turn |
| Wiring in Burp, Slither, Ghidra, CloakBrowser | [`references/local-tooling.md`](references/local-tooling.md) |
| Wondering how "confirmed" is decided | [`references/validation.md`](references/validation.md) |
| Looking at the campaign | [`references/campaign.md`](references/campaign.md) |
| Looking for a specific lens agent | [`agents/README.md`](agents/README.md) |

## How an engagement runs

```
link -> intake -> sieve scan -> sieve campaign (run / next / dispatch / submit) -> report -> vault + knowledge base
```

1. **Intake.** The agent reads the program page, extracts scope, rules, payout table and known issues, clones the repos, proves
   the checkout matches the deployed bytecode, and fills `.sieve/case.md`: the fence. Nothing outside it is touched.
2. **`sieve preflight`, then `sieve scan`.** Preflight exercises Burp, the CloakBrowser test identity, the MCP servers, the
   knowledge base and the hook, and prints the fix for every gap. Scan is the mechanical head, with no model and no traffic to a target: it detects the packs, runs the x-ray and every installed
   static analyzer, the static rules and the knowledge-base prime, seeds the work queue, and recommends how deep to go.
3. **The campaign.** A DAG the engine schedules: threat model, eight independent invariant lenses merged, a dynamic strategy
   node, property fuzzing, looped specialist hunts, a roaming pass, a drain that closes every open row with a receipt, a
   triage panel by quorum, a deterministic reportability gate, proofs, an independence audit. Every agent's output is
   validated against a versioned contract before the next step sees it.
4. **Report and learn.** The report prints the tier the machine computed. Confirmed findings, false positives and dead ends
   become cards the next engagement reads first. The whole engagement is filed in an Obsidian vault as a linked graph.

**Depth is a dial, not a mode**: `lite` (about 12 agent runs), `default` (about 44) and `exhaustive` (about 57 for one pack;
all eight lenses, three hunt loops, a triage quorum of three, the independence audit). The same gates and proofs apply at every
depth. `sieve campaign init` prints the cost before anything is dispatched.

## What makes it different

- **"Confirmed" is a computed value.** A finding is confirmed only when the tool re-ran its proof several times, a **negative
  control stayed silent** (ideally the same command against a copy of the target with the fix applied, which a fake PoC cannot
  survive), every citation was re-read by code, the code has not drifted, and a verifier who did not find it signed off. The report
  prints that tier and ignores whatever the file claims. Receipts are HMAC-sealed in a hash-chained ledger; editing or forging
  one is detected.
- **Real tools, not reimplementations.** Burp over its MCP server, Slither, Aderyn, Foundry, Echidna or Medusa, Ghidra, Frida,
  the ProjectDiscovery set, and **CloakBrowser** for live-client recon (XHR, WebSocket frames, storage, forms), fence-checked in code
  and navigation-guarded so a click cannot leave scope.
- **Persistence is enforced.** A Stop hook blocks the agent from ending a turn while the work queue has open rows and names a
  permission-seeking ending by name. A dead end needs a receipt: three attempts across three genuinely different rungs.
- **A knowledge base that starts full and compounds.** `sieve kb ingest` pulls 70k public precedents with no API key (real DeFi
  exploits, contest findings, disclosed HackerOne reports, exploited-in-the-wild CVEs, OSS-Fuzz advisories **with their fix
  commits**). Your own confirmed findings, false positives and dead ends rank above them and are read first next time.
- **A vault that shows the gaps.** One Obsidian vault for the knowledge base and every engagement. Each numbered invariant is a
  note with a coverage state; `unprobed` ones are the audit's blind spots, visible in the graph.
- **A method for seeing what nobody else does.** Invariants derived through independent lenses, an asymmetry checklist,
  history-driven hunting, and a roaming pass for the classes no lens was looking for
  ([`references/hypothesis-craft.md`](references/hypothesis-craft.md)), inside bright lines the agent must follow exactly.
- **Tested.** `sieve selftest` runs about 110 tests, including a full 71-node engagement with simulated agents that ends in a
  machine-confirmed finding, and a live browser test.

## Layout

```
Sieve/
├─ SKILL.md               the agent's script: turn by turn, non-negotiables
├─ AGENTS.md              host-capability contract: what a harness must give this skill
├─ setup.md               install, per OS
├─ sieve.yaml             config: vault, knowledge-base sources, persistence budgets, thresholds
├─ bin/                   sieve (POSIX) · sieve.cmd (Windows) · sieve.py (anywhere)
│
├─ references/            THE METHOD: shared-rules, methodology, hypothesis-craft, judging, validation, xray, campaign,
│                         dispatch, scope-intake, knowledge, crossover, recon-resilience, vm-gates, solana-scan,
│                         property-fuzzing, report-formatting, cvss-guide, local-tooling
├─ agents/README.md       the roster: every lens agent, core vs. deep
├─ packs/                 THE HUNTERS: web3 (12 agents) · web (9) · binary (7) · seams (crossover); vector cards and gates per pack
├─ campaigns/             THE TOPOLOGY: campaign.yml (nodes, profiles), prompts/*.md, rules/*.yml
├─ sieve/                 THE ENGINE: stdlib-only Python, mechanical work only
│   ├─ scan · cli_scan · preflight · cli_preflight · leads · cli_leads   the mechanical head, the tool check, external leads
│   ├─ campaign · campaign_actions · campaign_schema · campaign_rules · dashboard      the campaign engine
│   ├─ pipeline · merge · blocks · frontier · seed · hook                              the hunt machinery and persistence
│   ├─ validate · judging · cites · fence · report                                     the verdict, the fence, the report
│   ├─ kb_store · kb_ingest · kb_net · cli_kb · vault · cli_vault                      knowledge base and vault
│   └─ tooling · cli_setup · cli_selftest · state · config · util · yamlish            setup and plumbing
├─ scripts/               browser-recon.py (CloakBrowser) · js-recon.py · race.py · secrets-sweep.sh · generate_svg.py
├─ tests/                 the self-test suite (`sieve selftest`)
├─ kb/                    shipped seed cards; the real store lives in the vault
└─ templates/             the property-fuzzing handler starter
```

## For authorized use only

This skill assumes an engagement the operator owns or has explicit written permission to test: a bug bounty program, a
contracted pentest, a security audit, or a target you own. Every scope boundary comes from `.sieve/case.md`; nothing in this
skill invents or widens scope on its own. Methodology and dataset attribution: [`CREDITS.md`](CREDITS.md).
