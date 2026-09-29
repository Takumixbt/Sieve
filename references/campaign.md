# Campaign — a topology-driven static-analysis campaign

The classic hunt (`dispatch.md`) is a loop you drive by hand: build bundles, spawn agents, roll call, merge. The
**campaign** is the same back end driven by a *topology* — a DAG of nodes the engine schedules, prompts, and
validates. It exists because the best results in this kind of work come from a chain of reasoning steps
(threat model → goals → independent invariant lenses → strategies → hunts → adversarial triage → machine proofs), each
handing the next a **checked** artifact instead of a paragraph. The engine never calls a model; it decides what is ready,
tells each agent exactly what to do, and refuses to advance on anything that does not satisfy its contract.

```
sieve init <target> --pack web3          # + fill in .sieve/case.md (the scope fence)
sieve campaign init --profile default    # smoke | default | exhaustive
sieve campaign run                       # do everything mechanical; accept finished agent artifacts
sieve campaign next                      # render ready agent prompts — spawn ALL in ONE message
   … agents write their artifacts and run `sieve campaign submit <node>` …
sieve campaign run                       # repeat until "Campaign complete"
sieve campaign status | dashboard        # look at it
```

## Node kinds

| kind | who runs it | example |
|---|---|---|
| `meta` | the engine, in-process | `xray`, `rules`, `seed`, `pass-merge`, `reportability`, `prove-run`, `report`, `finish` |
| `agentic` | an agent the orchestrator dispatches; the engine validates its artifact | `threat-model`, `lens-*`, `hunt-*`, `triage-*`, `prove` |
| `reference` | nobody — a document inlined into the prompts of nodes that depend on it | `ref-methodology`, `ref-judging` |

## The default topology (`campaigns/campaign.yml`)

```
phase-xray → xray → rules → narrative-<pack> → precedents
   → threat-model → goal-plan
   → lens-{accounting, authority, ordering-time, equivalence, bounds-monotonicity, trust-boundary,
           promise-vs-enforcement, adversary-profit}   (8 independent nodes — cold derivation)
   → invariants-merge → strategy (the dynamic strategy generator; ≥1 moonshot required)
   → seed → phase-prime → plan → phase-hunt
   → hunt-<agent>-loopN  ×  roster  ×  loops   (series: loop N+1 waits for loop N's merge)  → hunt-merge-loopN
   → roaming → roaming-merge → drain (close every frontier row with a receipt)
   → phase-converge → merge-final → phase-gate
   → triage-panelistK × quorum (independent; each judges every candidate)  → reportability (deterministic gate)
   → phase-prove → prove (PoC + negative control for each cleared finding) → prove-run (the engine runs them)
   → independence-audit → audit-gate → verify → phase-report → report → writeback + map → finish
```

**Profiles** change the shape without editing the file: `smoke` (3 lenses, core roster, 1 loop, no independence audit — ~41
nodes for a web3 target), `default` (8 lenses, full roster, 2 loops, quorum 2 — ~69), `exhaustive` (3 loops, quorum 3 — ~83).
More packs, more nodes (three packs on `exhaustive` is ~135).

## What the engine enforces

- **Topology rules** (checked at `init`, by `sieve campaign validate`, and by `sieve lint`): unique ids; every dependency
  resolves; no cycles; **exactly one primary output per node**; every agentic node declares an output with a versioned contract.
- **Artifacts are contracts, not prose.** `sieve campaign schema <name>` prints one (`threat-model@1`, `goal-plan@1`,
  `properties@1`, `properties-merged@1`, `strategy@1`, `triage@1`, `proofs@1`, `audit@1`, plus the x-ray file sets). An agent's
  artifact is validated *before* the node is done; a rejection lists JSON-path errors (`$.goals[2].priority: 9 is above the
  maximum 5`), three rejections fail the node. Semantic checks ride on top: a triage panelist must judge **every** candidate and
  name themselves `triage-K`; the prove artifact must cover every cleared finding, and a `patch` control must point at a file
  that exists; the drain node is done only when the frontier is empty.
- **Hunt output is validated by roll call** — the same contract as classic passes (quotas, markers, `SIEVE-AGENT-DONE`).
- **Resumable and honest about change.** State lives in `.sieve/campaign/state.json`; a crash or a context reset loses
  nothing. Each finished node records the SHA-256 of its artifacts and of its inputs; edit an upstream artifact and everything
  downstream is **stale** (`sieve campaign run --rerun-stale` re-opens it and its descendants). Editing the topology needs
  `sieve campaign init --resume` — finished nodes keep their results.
- **Everything is recoverable and on the record**: `retry`, `reset <node>` (cascades), `skip <node> --reason …` (printed as
  coverage debt in the report).

## The reportability gate and the panel (deterministic)

`triage` runs `quorum` independent panelists, each with Gates 0-5 of `judging.md` and no sight of the others. The
`reportability` node then runs **hard checks first** — every cited file inside `scope.paths`, the finding's class not under
`out_of_scope.vulns` — before recording each panelist's verdict as a vote through the same code `sieve judge` uses
(`sieve/judging.py`). The quorum and disagreement rules live there: a complex finding needs every panelist to agree;
any dissent demotes rather than averages; the panel's most conservative severity wins. **Reportability comes before severity.**

## The proofs and the independence audit

`prove` writes PoCs and controls; `prove-run` executes each (`validate.run_proof`) and records `confirmed` only on a pass —
repeated, stable, with a silent negative control (`validation.md`). A finding with no possible execution is listed with
`trace_only: true` and ships as trace-verified with the reason on record. `independence-audit` (default/exhaustive) asks the
question the machine cannot: is the oracle independent of the code it judges? A "no" caps the finding at trace-verified; a
"yes" is the second verifier a complex finding needs at the proof stage.

## Static rules (`campaigns/rules/*.yml`)

The `rules` node is the always-available first look: ~55 anti-pattern regexes across web3, web and binary
(`tx.origin`, `delegatecall`, `ecrecover`, string-built SQL, `android:exported="true"`, `strcpy`, …) plus every vector card's
`tell:` regex. A hit is a frontier row somebody closes with a receipt — never a finding. It does not compete with Slither,
Semgrep or CodeQL; those run first and their output is folded in. Add your own rules in `.sieve/campaign/rules/*.yml`.

## Editing the campaign

`.sieve/campaign/topology.yml` and `.sieve/campaign/prompts/*.md` are per-engagement copies — tune a prompt for a target's
stack, add a node (say, a `graphql-schema` lens for a GraphQL-heavy app), change a profile. `sieve campaign validate --topology
FILE` checks an edited copy; `sieve campaign init --resume` adopts it. Prompts use `{{lens}}`, `{{panelist}}`,
`{{triage_quorum}}`, `{{candidates}}`, `{{cleared}}`, `{{proven}}` and `{{packs}}`.

## The dashboard

`sieve campaign dashboard` serves a read-only page on `127.0.0.1` (Host-header checked, GET only, no file serving): the node
graph by dependency layer, progress, findings by machine tier, frontier by kind, the event log. `--once` writes a static
snapshot to `.sieve/campaign/dashboard.html`.

## Classic or campaign?

Campaign for a real engagement — the structure is the point, and the artifact contracts are what keep an agent from
narrating. Classic passes for a small target, a quick look, or when you want to steer each step. Both end in the same
merge → judge → prove → verify → report.
