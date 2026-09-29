# Dispatch — from scope card to a bundle every actor can run on

Read this immediately after intake, every engagement. It turns `case.md` into the exact plan the
pass commands execute: which pack(s), which agents, what's in each bundle, and what comes back.
The mechanical half is code — `sieve bundle`, `dispatch`, `rollcall`, `merge`, `absorb` (`sieve/pipeline.py`,
`sieve/merge.py`) — so an orchestrator cannot narrate it instead of running it. (Running the campaign
instead? `campaign.md`: the same steps are nodes, and the engine drives them.)

```
sieve pass N  ->  sieve bundle --all  ->  (spawn the roster)  ->  sieve dispatch
              ->  (agents write .sieve/raw/pass-N/<pack>--<agent>.md)
              ->  sieve rollcall  ->  sieve merge  ->  sieve absorb  ->  next pass / roaming
```

## Classify the target

From the scope card and the x-ray's file discovery (`xray.md` Phase 0): pick the pack(s). A target
is often more than one — a dApp is web3 + web at minimum, and `packs/seams/` runs once both have
produced output (`crossover.md`). Write the decision and why to `.sieve/plan.md` before dispatching
anyone; this is the receipt that classification happened, not something narrated after the fact.

## The roster

Each pack's `agents/README.md` names its full roster and which are core (★, run in `--quick` mode)
vs. deep (the rest, run by default — `sieve init --mode deep` is the default for a reason: the
class of bug that pays best is usually the one a quick pass skips). `sieve bundle` reads the roster
from the agent files themselves (`packs/<pack>/agents/*.md` frontmatter: `name`, `owns`, `tier`,
`enumeration_only`). Binary always includes the mobile agents when the target is an APK/IPA; web3
adds the per-VM specialist matching the language(s) `xray.md` found; from pass 2 on, an engagement with two
or more packs adds `packs/seams/agents/crossover-agent`.

## Bundles — built by code, sized on the terminal

`sieve bundle --all` writes one file per actor to `.sieve/bundles/pass-N/<pack>--<agent>-bundle.md`
and **prints every bundle's line count** — a bundle you cannot state the size of was not built, and
that one printed number is the check that most directly stops an orchestrator narrating the lifecycle
instead of running it. Each bundle has nine numbered sections, the agent's own file last so its lens is
the most recent thing in context when hunting starts:

1. the scope card (`.sieve/case.md` — the fence)
2. the x-ray (`x-ray.md`, `entry-points.md`, `invariants.md`, authz matrix / attack surface, threat model, goal plan,
   merged invariants, strategy, static rule hits, precedents — whichever exist)
3. the plan (`.sieve/plan.md`, the ranked hit list from PRIME)
4. the frontier rows assigned to this lens, plus (pass ≥ 2) the ledger of what earlier passes already merged
5. a source / surface index (files with nSLOC, entry-point candidates, static-analysis leads with cross-tool
   corroboration marked ★, the web surface, fix-scored commits) — the agent reads the source itself
6. the method (`methodology.md`, `hypothesis-craft.md`, `shared-rules.md`)
7. the pack's vector cards (narrowed by the agent's `vectors:` frontmatter when it sets one)
8. **the OUTPUT CONTRACT** — generated per agent, binding (below)
9. the agent's own lens file

`--only <name,...>` builds a subset; `--roaming` builds the lens-free roaming bundle (below).

### The output contract

Section 8 tells the agent exactly what to produce, and `sieve rollcall` checks the same numbers:

- **One file**: `.sieve/raw/pass-N/<pack>--<agent>.md` — the only file it may create (hunters are read-only inside the
  target otherwise; `shared-rules.md`).
- **Quotas computed for this target**: distinct hypotheses (FINDING + LEAD + HYPOTHESIS blocks), distinct techniques
  (`technique:` on each block), a moonshot (`moonshot: true`), and `[Feynman: …]` / `[Socratic: …]` / `[Inversion: …]`
  markers scaled by kLOC (`sieve.yaml` → `audit.hypothesis_quota`, `audit.markers`).
- **A `## COVERAGE` section** — one line per frontier row examined: `R-0007 | finding | <group_key>`,
  `R-0008 | clean | <the guard, file:line> | inversion: …; input: …`, `R-0009 | dead | layer: …; sibling: …; precedent: …`,
  `R-0010 | open | <what is left>`. This is what lets rows close without the agent running any CLI.
- **A last line** `SIEVE-AGENT-DONE <slug> pass N` — a file without it is a crashed agent.

## Dispatch

Spawn every agent in the roster as a parallel background call, **in one message**, then run `sieve dispatch` —
it verifies each bundle on disk is intact (the SHA-256 recorded at build time; a truncated or edited bundle is refused),
records the spawn, and sets the waiting state the Stop hook honours. It prints each agent's prompt, which is exactly:
*"Read `{bundle}` (NNNN lines) in full before hunting — it holds your scope, your lens, the finding format, and the
anti-hallucination protocol. Do not re-derive any of it. Write your output to the file its OUTPUT CONTRACT names and finish it
with `SIEVE-AGENT-DONE …`. Emit findings in the shared-rules.md format at SUSPECT or REACHABLE. You do not gate, dedup, or
verify. Be your own devil's advocate — do not finish until coverage feels complete."* Never "go read these five files and
hunt" — that phrasing leaves the actor discretion over whether it actually reads the bundle, and that discretion is exactly how
findings ship unguarded by `judging.md`.

**No parallel dispatch?** `sieve dispatch --sequential` hands out one agent at a time, in roster order; run each in its own
context, let it write its file, call it again. Everything after is identical, and `.sieve/` (not your context window) is the
source of truth, so a reset loses nothing.

Wait for every completion notification — do not poll, do not proceed early.

## Roll call, merge, absorb

- **`sieve rollcall`** reads what each agent wrote. `lost` = no file or no `SIEVE-AGENT-DONE` line (recorded as coverage debt;
  never respawn a dead agent mid-pass — the next pass covers its ground). `thin` = below quota or markers: send the agent
  back with the exact shortfall it prints, or accept the debt on the record (`--accept "reason"`). Exit code 1 when anything
  is lost or thin, so it cannot be missed.
- **`sieve merge`** parses every block, applies the deterministic checks and writes `.sieve/findings/F-NNN.md`. Nothing is ever
  *promoted*: a FINDING with no real `proof:`, hedge wording (*could theoretically, might allow…*), a bad severity, a web3
  finding with no citation, or **any `file:line` that does not resolve to a real line (or whose quoted snippet is not there)**
  is kept as a LEAD with the reason written on it. Same `group_key` from several agents or passes → one file whose `found_by`
  lists them all (the corroboration signal, and what `sieve judge` uses to refuse a self-verifier).
- **`sieve absorb`** applies the `## COVERAGE` lines to the frontier — through the same receipt rules as `sieve frontier`
  (`clean` needs ≥2 attempts including `inversion`; `dead` needs ≥3 attempts on ≥3 rungs). A citation that does not check out,
  or the same "why it holds" pasted across three rows, is refused; refused rows stay open and the refusal is printed.

## Exclusions, pinned before hunting starts

Write the program's known-issue list and out-of-scope classes into `.sieve/plan.md` now, from the
prior-art sweep (`knowledge.md`). Nothing hunts a class the scope card excludes; nothing ships a
finding that matches a known, already-reported issue — the gate rejects it on sight, but it's
cheaper never to spend the effort.

## Multi-pass

`sieve pass N` runs the roster again, this time with `.sieve/plan.md` and the frontier's remaining
open rows telling every agent what earlier passes already covered — spend effort on new ground,
but **report every bug you find in full, listed or not**: a bug you reach again is a bug that is
still there, and silence reads as "nobody found this," which corrupts the coverage numbers
downstream. Convergence (no new findings across a full pass) requires **all** roster agents to have
run at least once in that state, never declared after a partial pass.

**The last pass before convergence is the roaming pass** (`hypothesis-craft.md` §5): no lens, no
vector cards — one actor lists every class already covered, asks what is unusual about *this specific system*, and tests at
least three hypothesis classes nobody on the roster was looking for. `sieve bundle --roaming` builds its bundle (the ledger,
every closed row, every class already raised), it writes `raw/roaming.md` (dead ends included), and
`sieve rollcall --roaming` → `sieve merge` → `sieve absorb` close it. `sieve status` will not offer `converge` until it has run.
