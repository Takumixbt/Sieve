# Dispatch — from scope card to a bundle every actor can run on

Read this immediately after intake, every engagement. It turns `case.md` into the exact plan
`sieve pass`/`sieve frontier` execute against: which pack(s), which agents, what's in each
bundle, and what's excluded before hunting starts.

## Classify the target

From the scope card and the x-ray's file discovery (`xray.md` Phase 0): pick the pack(s). A target
is often more than one — a dApp is web3 + web at minimum, and `packs/seams/` runs once both have
produced output (`crossover.md`). Write the decision and why to `.sieve/plan.md` before dispatching
anyone; this is the receipt that classification happened, not something narrated after the fact.

## Build the roster

Each pack's `agents/README.md` names its full roster and which are core (★, run in `--quick` mode)
vs. deep (the rest, run by default — `sieve init --mode deep` is the default for a reason: the
class of bug that pays best is usually the one a quick pass skips). Binary always includes the
mobile agents when the target is an APK/IPA; web3 always adds the per-VM specialist matching the
detected language(s) from `xray.md`.

## Build every bundle before dispatching anyone

One file per actor, concatenated (`cat`, or PowerShell `Get-Content` on Windows — never a shell
variable or heredoc, which silently truncates on large source):

```
{bundle}/<agent>-bundle.md =
    .sieve/case.md                      (the scope card — the fence)
  + .sieve/xray/x-ray-verdict.md         (the executive summary; no actor starts cold)
  + .sieve/plan.md                       (the ranked hit list from PRIME — knowledge.md)
  + the in-scope source / surface excerpt relevant to this actor
  + references/methodology.md
  + references/shared-rules.md
  + packs/<pack>/vectors/<the cards this agent owns>.md
  + agents/<agent>.md
```

**Print the line count of every bundle before dispatch.** A bundle you cannot state the size of was
not actually built — this one printed number is the single check that most directly prevents an
orchestrator from narrating the lifecycle instead of running it (a real, observed failure mode in
this skill's predecessors: a fluent "I built the bundles and dispatched the agents" with no
underlying Read/Bash/Agent calls, shipping findings that never actually passed through
`judging.md`). If you cannot show the byte or line count, you have not done this step.

## Dispatch

Spawn every agent in the roster as a parallel background call, **in one message**. The prompt is
exactly: *"Read `{bundle}` (NNNN lines) in full before hunting — it holds your scope, your lens,
the finding format, and the anti-hallucination protocol. Do not re-derive any of it. Emit findings
in the shared-rules.md format at SUSPECT or REACHABLE. You do not gate, dedup, or verify. Be your
own devil's advocate — do not finish until coverage feels complete."* Never "go read these five
files and hunt" — that phrasing leaves the actor discretion over whether it actually reads the
bundle, and that discretion is exactly how findings ship unguarded by `judging.md`.

Wait for every completion notification — do not poll, do not proceed early. When an agent dies,
continue with the rest and record the loss by name in the pass summary and the report's Coverage
section (`sieve rollcall` is the mechanical check for this — never respawn a dead agent mid-pass;
the next pass covers its ground).

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
