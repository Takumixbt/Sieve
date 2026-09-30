---
name: sieve
description: Autonomous security audit engine for authorized engagements, covering web3, web and binary/mobile targets. The operator hands over a target (a bug bounty program URL, a repo, a domain, a contract address, an APK or binary) and Claude drives the whole engagement to a finished report without further input - intake, a mechanical scan, a topology-driven campaign (threat model, eight independent invariant lenses, strategy, looped specialist hunts, property fuzzing, roaming, triage panel), a six-gate judge, executed proofs with negative controls, an Obsidian vault, and a submission-ready report. A finding is only CONFIRMED when a machine re-runs its proof and re-reads every citation; the report prints the machine's answer, never an agent's claim. It is paired with real tooling (Burp over MCP, CloakBrowser, the ProjectDiscovery recon set, Slither/Aderyn/Foundry/Echidna, Ghidra/Frida) and enforces its own persistence with a Stop hook. Triggers on "/sieve", "audit this", "bug bounty on X", "pentest X", "find vulnerabilities in X", "review this protocol for security", or a dropped program/repo/contract/domain/binary link with security intent.
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

The operator's whole input is a target. **You drive everything from there to the finished report**: reading the
program, building the scope card, scanning, running the campaign, dispatching the agents, gating, proving, reporting
and filing the vault. Do not hand steps back. Do not ask permission for a decision you can make: record it in
`.sieve/assumptions.md` and continue. The only honest reasons to stop and ask are `sieve halt --reason scope |
credentials | irreversible`.

Sieve does not scan, crawl, fuzz or disassemble anything itself. It names the real tool for each job
(`references/local-tooling.md`), tells you how to read its output and how to think past it
(`references/hypothesis-craft.md`), and a small stdlib-only CLI enforces the discipline that turns tool output and
hunches into a few proven, gate-checked findings. The intelligence is yours, the work is done by real tools, and the
verdict is computed by a machine.

## Print the banner first

Every run, before anything else, print the banner above exactly, or run `sieve banner`. If the entry point already
printed it, do not print it twice.

## Two modes at once

**On the bright lines, follow this skill exactly. On the open ground, think for yourself.** `shared-rules.md` has the
full table.

- *Bright lines*: the scope fence, cite-or-drop, proof-or-lead, the gates in order, discoverer is never verifier,
  receipts for dead ends. No cleverness here. A persuasive reason to skip one is the warning sign. Most of them are
  checked by code, not by your honesty.
- *Open ground*: which hypotheses to form, which invariants matter, which asymmetry to chase, which tools to combine,
  which chain to try. Be strange here. **Creativity is spent on hypotheses, never on evidence.**

Do not deviate from the flow below. If a step seems unnecessary, that is the moment it matters most.

## Usage

```
/sieve https://immunefi.com/bug-bounty/someprotocol/    # a bounty program: you build the scope card from it
/sieve https://github.com/acme/contracts                # a repo (packs auto-detected)
/sieve acme.com                                         # a web target
/sieve 0xABC...DEF (ethereum)                           # a deployed contract
/sieve ./app-release.apk                                # an APK (binary pack)
/sieve --continue                                       # resume an interrupted engagement (`sieve status`)
/sieve --focus "<question>"                             # research only an operator-named question
```

`--web3`, `--web`, `--binary` force a single pack. A bare drop lets intake pick (`references/scope-intake.md`).

## The engagement, turn by turn

```
LINK -> INTAKE -> SCAN -> CAMPAIGN (run / next / dispatch / submit, repeated) -> REPORT -> LEARN
```

**Turn 1: read the discipline, in parallel.** `shared-rules.md`, `methodology.md`, `hypothesis-craft.md`,
`judging.md`, `validation.md`, `local-tooling.md`, in full, as distinct tool calls (not from this file's summary).
Run **`sieve preflight`**: it exercises what an audit depends on (Burp's proxy, MCP server and loaded BApps; CloakBrowser
opening the persistent test identity with its live login and wallet extensions; the Burp and V12 MCP servers; the
knowledge base, vault and Stop hook) and prints the exact fix for every gap. Apply the fixes you can (`sieve install
<pack> --run`, `sieve kb ingest`, `sieve vault init`); whatever remains is coverage debt, named in the report, never
a silent skip. It writes `.sieve/preflight.md` as the engagement's receipt. Tools that live in WSL on a Windows machine
(Foundry, Halmos, radare2, AFL++, checksec...) run as `wsl -e bash -lc '<cmd>'` with project paths under `/mnt/c/`.

**Turn 2: intake from the link.** Follow `scope-intake.md`.
- *A bounty program page*: fetch it (agent-reach, or a browser through CloakBrowser if it is behind a challenge page).
  Extract every in-scope asset, every out-of-scope asset and vulnerability class, the rules (active testing, rate
  limits, test accounts, forbidden actions), the payout table, known issues and prior audits. Clone every in-scope
  repo. For a deployed contract, fetch the verified source and **prove the checkout matches the on-chain bytecode
  before auditing it**; a stale clone silently invalidates every finding.
- *Sweep prior art before hunting*: prior audit PDFs in the repo, contest reports, the program's disclosed reports
  (`knowledge.md`). It kills duplicates and shows where nobody has looked. Write every known issue and prior-audit finding as
  one line under `## Known issues and prior audits` in `case.md`: the reportability gate flags any candidate that resembles one.
- Create the engagement in the target tree (`sieve init <root> --pack <packs>` or let `sieve scan` do it), then fill
  `.sieve/case.md` **completely**. Print the resolved scope (hosts, contracts, paths, whether active testing is
  permitted). Nothing outside it is ever touched.

**Turn 3: scan.** `sieve scan <root>`. It runs the x-ray, every installed static analyzer (Slither, Aderyn,
trailmark), the static rules, the knowledge-base prime and the frontier seed, with no model and no traffic, and ends
with a measured profile recommendation and what each profile would dispatch. If it reports an analyzer as skipped for missing dependencies (a Hardhat project without `node_modules`, a Foundry project
with empty `lib/` submodules), install them yourself in a sandbox that cannot reach anything sensitive
(`npm ci --ignore-scripts`, `git submodule update --init --recursive`; never run a target's own install scripts on your
real environment) and re-run `sieve scan --refresh`; Slither and Aderyn are worth the extra minute.
Read it, then choose the depth and record
the choice and its reason in `assumptions.md`:
- **a live bounty with real money in scope, or "a full audit": `exhaustive`** (all eight lenses, three hunt loops,
  a triage quorum of three, property fuzzing, the independence audit). This is the relentless setting.
- a normal repo review: `default`.
- a tiny target or a quick look: `lite` (same hunt, same gates, same proofs, no lens fan-out).

**Second opinion (V12, optional, budget-capped).** If the V12 MCP server is connected and `sieve config get
external.v12.enabled` is true, run an independent automated audit alongside your own, and fold what it finds in as
**leads**:
1. Only for code that may leave the machine: a public repo, or a program that permits third-party tools. Never send a
   private or confidential-program tree.
2. `v12_whoami`, then `v12_estimate_cost` for the exact in-scope paths (tests, mocks and `lib/` are excluded by
   default). Launch only when the quote is at or under `external.v12.max_cost_cents` and the scope is at or under
   `external.v12.max_lines`; otherwise record the quote in `assumptions.md` and move on. Do not ask.
3. `v12_audit_github` (or `v12_upload_zip` then `v12_audit_zip`), then wait on `v12_watch` rather than polling, then
   `v12_get_findings`.
4. For each result: `sieve leads add --source v12 --title ... --file ... --line ... --severity ... --detail ... --ref <run
   url>`. Each becomes an open frontier row the drain must close with a receipt. A V12 finding is never reported as a
   finding: it needs this engagement's own gates and proof. Do not write triage state back to V12 unless the operator asks.
The same command folds in Burp scanner issues, nuclei output or any other tool's results (`sieve leads import`).

**Turn 4: the campaign.** `sieve campaign init --profile <p>`, then repeat until it says `Campaign complete`:

```
sieve campaign run        # executes every mechanical node, validates and accepts finished agent artifacts
sieve campaign next       # renders a prompt for every ready agent node
```

`next` prints the ready agent nodes. **Spawn ALL of them in ONE message as parallel background agents**, each told to
read its prompt file in full and do exactly what it says. Do not poll. When they return, `sieve campaign run` again.
An agent whose artifact fails its contract is sent back with the exact errors (`sieve campaign submit <node>`); three
rejections fail the node. Spawn every agent with `model: "opus"` (the strongest available, at its strongest effort) whatever model the parent
session runs on: never Sonnet or Haiku for anything that reasons. Assurance is the priority and a missed critical costs
more than the inference. Keep your own turns for coordination and verification.

What the campaign does (`references/campaign.md` has the full manual): x-ray narrative, threat model, goal plan,
eight independent invariant lenses merged (`INV-n`), a dynamic strategy node with at least one moonshot, property
fuzzing of the merged invariants, looped roster hunts, a roaming pass, a drain that closes every frontier row with a
receipt, a triage panel that judges every candidate by quorum, a deterministic reportability gate, proofs, an
independence audit, and the report. The engine renders each prompt, validates each artifact against a versioned
contract, and refuses to advance on anything that does not satisfy it.

**Web targets**: put recon inputs in `.sieve/inputs/` (OpenAPI, HAR, URL lists). The `browser-recon` node drives a real
browser through CloakBrowser (XHR, WebSocket frames, storage, forms) for every in-scope URL, checked against the fence
in code, and only when the scope card permits active testing. One headed pass signs the dedicated test identity in
(`scripts/browser-recon.py --setup`). Burp is driven over its MCP server (`sieve config get tools.burp.mcp`; `sieve preflight` confirms it answers) for
everything authenticated, cross-identity or racy (`local-tooling.md` 1.2), through the proxy on `tools.burp.proxy`. The
test identity (dedicated mailbox and, for a dApp, wallet extensions) is checked without touching a page by
`python scripts/browser-recon.py --check`; wallet extensions resolve by ID to their newest installed version. `scripts/race.py`, `scripts/js-recon.py` and `scripts/secrets-sweep.sh` are the
scriptable fallbacks; `race.py` refuses to fire unless the fence lists the host and allows active testing.

**Prove, deterministically.** For each cleared finding the prover writes the PoC **and a negative control**. The
engine runs it several times, checks the signature is stable, runs the control (ideally the same command against a
patched copy of the target), and refuses a proof the control also satisfies. It re-reads every `file:line` and hashes
the code. `confirmed` is a value the tool computes. No way to execute it: it ships as trace-verified with the reason on
record, never as confirmed (`validation.md`).

**Turn 5: report and learn.** The campaign ends by assembling `.sieve/report/report.md` with each finding's
**computed** tier (confirmed, trace-verified, unvalidated, rejected), whatever its own `status:` line says. Then:

```
sieve vault export     # the engagement into the Sieve Obsidian vault: invariants, findings, dead ends, coverage gaps
sieve finish
```

`kb writeback` ran inside the campaign: confirmed findings, false positives and dead ends are now cards the next
engagement reads first. Close by telling the operator, in a few plain sentences: what was found at each tier, what is
still coverage debt and why, where the report and the vault notes are. Do not narrate your own process.

## Steering, and recovering

`sieve status` names the current step and the exact next command; read it whenever you are unsure and never improvise
a different order. Nodes are recoverable: `sieve campaign retry <node>`, `reset <node>` (cascades downstream),
`skip <node> --reason ...` (printed as coverage debt), `run --rerun-stale` after an upstream artifact changed.
`.sieve/campaign/topology.yml` and `.sieve/campaign/prompts/*.md` are per-engagement copies: tune a prompt for the
target's stack, add a lens for a GraphQL-heavy app, then `sieve campaign init --resume`. `sieve campaign dashboard`
serves a loopback view. `sieve selftest` runs the skill's own tests. `references/dispatch.md` explains how a single hunt
node works underneath, for when one needs debugging by hand.

## Persistence

`shared-rules.md` has the doctrine. A Stop hook (`sieve hooks install`) blocks the turn from ending while the frontier
has open rows and the persistence budget is not spent, and names a permission-seeking ending ("would you like me to
continue?") by name. Internalize the doctrine (`shared-rules.md`, `methodology.md` Parts 0 and 6b) rather than
satisfying the hook mechanically. `sieve status` shows whether the hook is wired in.

## References

| Group | Files (all under `references/`) | When |
|---|---|---|
| **Core discipline** | `shared-rules.md` · `methodology.md` · `hypothesis-craft.md` · `judging.md` · `validation.md` · `local-tooling.md` | Turn 1, every engagement, in full |
| **Lifecycle** | `scope-intake.md` · `xray.md` · `campaign.md` · `dispatch.md` | intake; the x-ray and campaign nodes; debugging a hunt |
| **Knowledge and seams** | `knowledge.md` · `crossover.md` | prime and learn; when two or more packs ran |
| **Field craft** | `recon-resilience.md` · `vm-gates.md` · `solana-scan.md` | when the target pushes back; non-EVM chains |
| **Closing** | `report-formatting.md` · `cvss-guide.md` | per Critical/High/Medium finding |
| **Fuzzing** | `property-fuzzing.md` | the `fuzz` node, or a target that ships property tests |

**Agents**: `agents/README.md` (roster and bundle spec), `packs/<pack>/agents/*.md` (the lenses), `packs/<pack>/vectors/*.md`
(fast-recall attack cards), `packs/<pack>/judging.md` (pack-specific gate additions). **Campaign**:
`campaigns/campaign.yml` (topology and profiles), `campaigns/prompts/` (every node's editable prompt),
`campaigns/rules/` (static rules). **Setup**: `setup.md`; `AGENTS.md` for the host-capability contract.

## Non-negotiables

```
EVIDENCE OR SILENCE       no finding without file:line, request/response, or a runnable PoC
CONFIRMED IS COMPUTED     a machine re-runs the proof with a negative control and re-reads every
                          citation; the report prints that tier, never an agent's claim (validation.md)
DISCOVERER != VERIFIER    the actor that found it never gates its own finding (`sieve judge` refuses it)
REAL TOOLS DO THE WORK    Burp, Slither, Ghidra, subfinder and a real browser do the scanning; this skill
                          decides where to point them and what their output means
NEVER ASK PERMISSION      for a decision you can make: record it and continue (shared-rules.md)
A DEAD END NEEDS A RECEIPT   >=3 attempts on >=3 different ladder rungs, or it isn't dead yet
SCOPE IS THE FENCE        never touch what case.md didn't list; browsers, races and proof runs are
                          fence-checked in code
VERIFY, DON'T RECALL      names, flags, numbers, and "it doesn't exist" are checked in this turn
LEARN EVERY ENGAGEMENT    confirmed findings, false positives, killed hypotheses and your own mistakes
                          feed the next one
```
