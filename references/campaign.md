# Campaign: the topology that runs every engagement

An engagement is a chain of reasoning steps (threat model, goals, independent invariant lenses, strategies, hunts,
adversarial triage, machine proofs), each handing the next a **checked** artifact instead of a paragraph. The
**campaign** is the engine that schedules that chain: a DAG of nodes it decides are ready, tells each agent exactly what
to do, and refuses to advance on anything that does not satisfy its contract. It never calls a model. There is one way to
run an engagement; depth is a dial (the profile), not a choice between modes.

```
sieve scan <root>                         # mechanical head: x-ray, analyzers, rules, precedents, frontier seed
sieve campaign init --profile exhaustive  # lite | default | exhaustive (default: what the scan recommended)
sieve campaign run                        # do everything mechanical; accept finished agent artifacts
sieve campaign next                       # render ready agent prompts: spawn ALL in ONE message
   ... agents write their artifacts and run `sieve campaign submit <node>` ...
sieve campaign run                        # repeat until "Campaign complete"
sieve campaign status | dashboard         # look at it
```

## Scan first, then the campaign

`sieve scan` is the deterministic head of every engagement, and it is usable on its own (in CI, or before anyone has
decided how deep to go). No model, no traffic to a target:

1. detects which packs the source tree needs (web3, web, binary) and creates the engagement if there is none
2. runs the x-ray, every installed static analyzer (Slither, Aderyn, trailmark), the git-history security pass
3. runs the static rule pass and folds the analyzer output into the frontier
4. primes the knowledge base (precedents and your own lessons) and seeds the frontier
5. measures the tree (kLOC, entry points, analyzer leads, rule hits) and prints, for each profile, how many agent runs
   it would dispatch, plus a recommendation

The campaign's `xray` and `rules` nodes reuse the scan's output while the source tree is unchanged (a fingerprint of
path, size and mtime), so a scan is never wasted work and an edit invalidates it. Local source trees only: live hosts and
deployed contracts are never auto-scoped, they stay in the scope card.

## Profiles: depth is a dial

| Profile | Shape | Use it for |
|---|---|---|
| `lite` | core roster, one hunt loop, quorum 2, no lens fan-out, no strategy node, no fuzz node, no independence audit. Same hunt, same gates, same proofs. About 12 agent runs for a one-pack target | a tiny target, a quick look |
| `default` | eight lenses, full roster, two hunt loops, quorum 2, property fuzzing, independence audit. About 44 agent runs for web3 | a normal repo review |
| `exhaustive` | as `default` with three hunt loops and a triage quorum of three. About 57 agent runs for web3, more with more packs | a live bounty with real money in scope; a full audit |

`sieve campaign init` prints the agent-run count before anything is dispatched. Profiles change the shape without
editing the file; the topology itself is editable per engagement.

## Node kinds

| kind | who runs it | example |
|---|---|---|
| `meta` | the engine, in-process | `xray`, `rules`, `seed`, `browser-recon`, `pass-merge`, `fuzz-absorb`, `reportability`, `prove-run`, `report`, `finish` |
| `agentic` | an agent you dispatch; the engine validates its artifact | `threat-model`, `lens-*`, `fuzz`, `hunt-*`, `triage-*`, `prove` |
| `reference` | nobody: a document inlined into the prompts of nodes that depend on it | `ref-methodology`, `ref-judging` |

## The default topology (`campaigns/campaign.yml`)

```
phase-xray -> xray -> rules -> narrative-<pack> (+ browser-recon for web) -> precedents
   -> threat-model -> goal-plan
   -> lens-{accounting, authority, ordering-time, equivalence, bounds-monotonicity, trust-boundary,
           promise-vs-enforcement, adversary-profit}   (8 independent nodes: cold derivation)
   -> invariants-merge -> strategy (the dynamic strategy generator; at least one moonshot required)
   -> seed -> phase-prime -> plan -> phase-hunt
   -> fuzz -> fuzz-absorb                    (web3: property-fuzz the merged invariants)
   -> hunt-<agent>-loopN  x  roster  x  loops   (series: loop N+1 waits for loop N's merge)  -> hunt-merge-loopN
   -> roaming -> roaming-merge -> drain (close every frontier row with a receipt; waits for the fuzzer too)
   -> phase-converge -> merge-final -> phase-gate
   -> triage-panelistK x quorum (independent; each judges every candidate)  -> reportability (deterministic gate)
   -> phase-prove -> prove (PoC + negative control for each cleared finding) -> prove-run (the engine runs them)
   -> independence-audit -> audit-gate -> verify -> phase-report -> report -> writeback + map -> finish
```

More packs, more nodes (three packs on `exhaustive` is about 135).

## What the engine enforces

- **Topology rules** (checked at `init`, by `sieve campaign validate`, and by `sieve lint`): unique ids; every dependency
  resolves; no cycles; **exactly one primary output per node**; every agentic node declares an output with a versioned contract.
- **Artifacts are contracts, not prose.** `sieve campaign schema <name>` prints one (`threat-model@1`, `goal-plan@1`,
  `properties@1`, `properties-merged@1`, `strategy@1`, `fuzz@1`, `triage@1`, `proofs@1`, `audit@1`, plus the x-ray file
  sets). An agent's artifact is validated *before* the node is done; a rejection lists JSON-path errors
  (`$.goals[2].priority: 9 is above the maximum 5`), three rejections fail the node. Semantic checks ride on top: a triage
  panelist must judge **every** candidate and name themselves `triage-K`; the prove artifact must cover every cleared
  finding; a fuzz run that reports `broken` must carry the shrunk call sequence; the drain node is done only when the
  frontier is empty.
- **Hunt output is validated by roll call** (quotas, markers, a `SIEVE-AGENT-DONE` line).
- **Resumable and honest about change.** State lives in `.sieve/campaign/state.json`; a crash or a context reset loses
  nothing. Each finished node records the SHA-256 of its artifacts and of its inputs; edit an upstream artifact and everything
  downstream is **stale** (`sieve campaign run --rerun-stale` re-opens it and its descendants). Editing the topology
  needs `sieve campaign init --resume`; finished nodes keep their results.
- **Everything is recoverable and on the record**: `retry`, `reset <node>` (cascades), `skip <node> --reason ...` (printed
  as coverage debt in the report).

## Live client recon: `browser-recon` (web pack)

A meta node that drives a real browser through **CloakBrowser** (`scripts/browser-recon.py`) for every in-scope URL and
writes `xray/browser-observations.md`: every request the app actually fired, WebSocket frames, storage keys, forms,
console output. The web narrative reads it as ground truth for the surface. Guarantees, all enforced in code:

- every URL passes the scope fence before a browser opens; the fence's host list is handed to the script, which answers
  any main-frame navigation off the list with an empty 204, so a click cannot leave scope
- nothing opens unless the scope card has `active_testing: true` (or `lab: true`); a passive scope is recorded in the file
- a missing CloakBrowser, an unreachable proxy or a page that will not load is **coverage debt on the record**, never silence
- the test identity (a dedicated mailbox and, for a dApp, a dedicated wallet) lives in a persistent profile under
  `~/.sieve/browser/`; one headed `python scripts/browser-recon.py --setup` signs it in. An identity a previous tool left
  in `~/.helix` is adopted in place. Optional per-engagement `.sieve/inputs/browser.json`: `{"urls": [...],
  "click": {"<url>": ["<selector>"]}, "proxy": "http://127.0.0.1:8080", "timeout": 240}`.

## Property fuzzing: the `fuzz` node (web3, default and exhaustive)

After the lenses are merged, an agent turns the strongest `on_chain` invariants into executable properties, runs them
with Echidna, Medusa or Foundry invariant tests, and writes `fuzz.json` (`fuzz@1`). Every green result must carry
anti-vacuity evidence (the property was shown able to fail); a break must carry its shrunk call sequence. The engine's
`fuzz-absorb` node turns a broken invariant into a priority-5 frontier row and a vacuous one into a harness-gap row, so
the drain must close each with a receipt. A run that could not happen (no fuzzer, a non-EVM target) is recorded, never faked.
`references/property-fuzzing.md` is the procedure.

## The reportability gate and the panel (deterministic)

`triage` runs `quorum` independent panelists, each with Gates 0-5 of `judging.md` and no sight of the others. The
`reportability` node then runs **hard checks first** (every cited file inside `scope.paths`, the finding's class not under
`out_of_scope.vulns`) before recording each panelist's verdict as a vote through the same code `sieve judge` uses
(`sieve/judging.py`). A complex finding needs every panelist to agree; any dissent demotes rather than averages; the
panel's most conservative severity wins. **Reportability comes before severity.**

## The proofs and the independence audit

`prove` writes PoCs and controls; `prove-run` executes each (`validate.run_proof`) and records `confirmed` only on a
pass: repeated, stable, with a silent negative control (`validation.md`). Proof commands run under a POSIX shell (`sh`;
on Windows, the one that ships with Git for Windows). A finding with no possible execution is listed with
`trace_only: true` and ships as trace-verified with the reason on record. `independence-audit` asks the question the
machine cannot: is the oracle independent of the code it judges? A "no" caps the finding at trace-verified; a "yes" is
the second verifier a complex finding needs at the proof stage.

## Static rules (`campaigns/rules/*.yml`)

The `rules` node is the always-available first look: about 55 anti-pattern regexes across web3, web and binary
(`tx.origin`, `delegatecall`, `ecrecover`, string-built SQL, `android:exported="true"`, `strcpy`, ...) plus every vector
card's `tell:` regex. A hit is a frontier row somebody closes with a receipt, never a finding. It does not compete with
Slither, Semgrep or CodeQL; those run first and their output is folded in. Add your own rules in
`.sieve/campaign/rules/*.yml`.

## Editing the campaign

`.sieve/campaign/topology.yml` and `.sieve/campaign/prompts/*.md` are per-engagement copies: tune a prompt for a target's
stack, add a node (a `graphql-schema` lens for a GraphQL-heavy app), change a profile. `sieve campaign validate --topology
FILE` checks an edited copy; `sieve campaign init --resume` adopts it. Prompts use `{{lens}}`, `{{panelist}}`,
`{{triage_quorum}}`, `{{candidates}}`, `{{cleared}}`, `{{proven}}` and `{{packs}}`.

## The dashboard

`sieve campaign dashboard` serves a read-only page on `127.0.0.1` (Host-header checked, GET only, no file serving): the
node graph by dependency layer, progress, findings by machine tier, frontier by kind, the event log. `--once` writes a
static snapshot to `.sieve/campaign/dashboard.html`.
