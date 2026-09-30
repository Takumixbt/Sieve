# X-ray - the pre-hunt map, every engagement, every pack

The right division of labor for this step: **grep is the source of truth for which lines are
candidates; the agent reads the source and classifies each one.** A script
that tried to do the classification would be re-implementing Slither/Aderyn (web3) or a real
crawler (web) worse than they do it. `sieve xray <pack>` only ever does the mechanical half -
discovery, line counts, test inventory, and a grep pass - and hands you a list to read.

Output lands in `.sieve/xray/`: `facts.json` (the mechanical layer, per pack), and the narrative
files below, which you write by reading the source facts.json points at.

## Phase 0 - run the mechanical layer, static analysis first

```
sieve xray web3 [--slither report.json] [--aderyn report.json] [--no-auto-static]
sieve xray web  [--openapi doc.json] [--har capture.har] [--url-list urls.txt]
sieve xray git                                   # git-history security pass, any pack
sieve xray map                                   # renders xray/architecture.json you write below
```

**Static analysis is not something the operator supplies if they happen to have it lying around -
it's this command's own first move.** `sieve xray web3` auto-invokes `slither` and `aderyn` itself
(exactly the invocation named in `local-tooling.md` 2.1) whenever they're on PATH and no
`--slither`/`--aderyn` path was given, writes their raw JSON to `.sieve/xray/{slither,aderyn}.json`,
and folds the result into `facts.json["tool_leads"]` before you ever start reading source by hand.
Check the printed `auto-ran: ...` line - if it's empty and neither flag was passed, the tool
genuinely isn't installed on this host (run `sieve doctor`, then `setup.md`) or the project failed
to compile (read the note, fix the build, re-run); either way that's now a recorded, visible gap,
never a silent one. `--no-auto-static` is the explicit opt-out for a target where running a
compiler-dependent tool isn't safe or desired (e.g. an unverified bytecode-only target - go straight
to `heimdall` decompilation instead, `local-tooling.md` 2.1).

**Why static analysis runs before you read a single line of source, not after:** a detector's
finding is cheap, mechanical, and exhaustive in a way a first read never is - it will not miss a
function because it looked boring. Reading `tool_leads` before Phase 1's manual walk means every
hand-read of an entry point starts already knowing what the two best-maintained detector suites in
the ecosystem think is wrong with it, instead of rediscovering the same access-control gap by eye an
hour later. A detector finding is still a LEAD, still gated by `judging.md` like a Solodit precedent
(`knowledge.md`) - the ordering change is about when you see it, not about trusting it more.

Each entry in `tool_leads` carries a `corroborated` field: `true` when slither and aderyn
independently flagged the same `file:line` (within a couple of lines), `false` when only one tool
did. Two independent detector engines agreeing is a meaningfully stronger signal than either alone -
read corroborated leads first, and route them through `judging.md`'s new complexity triage as
**straightforward** by default unless something about the specific finding says otherwise.

`sieve xray web3` also auto-invokes `trailmark` when it's on PATH (`uv tool install trailmark`),
writing `.sieve/xray/graph.json` - a call/reference graph you can query instead of hand-tracing
"who calls this" or "what's the blast radius of this function" for Phase 1's call-chain step and
Phase 3's architecture map. It's an accelerant, never a requirement: its absence is a light note, not
coverage-debt, and a manual call-chain read is always the fallback.

A detector finding is real but gated (`judging.md`) before it ships, exactly like a Solodit
precedent. OpenAPI/HAR/URL-list input (web) works the same way in spirit but can't be auto-run the
same way - it depends on a live target and the engagement's active-testing permission
(`.sieve/case.md`'s `rules.active_testing`), so it stays operator/agent-supplied from a prior recon
pass rather than something this command launches on its own; run that recon pass (`local-tooling.md`
1.1) as literally the first action of the web x-ray, before manual browsing, for the same reason.
Either pack's tool absence is coverage-debt, never a silent gap (`shared-rules.md`).

Print what came back before reading further: file count, nSLOC, candidate count, and (web3) which
static tools actually ran. This is the receipt that Phase 0 actually ran - a summary you narrate
without having called the command did not happen.

## Phase 1 - read the source, classify what grep found

For **web3**, `facts.json["entry_candidates"]` is a list of `{file, line, text}` - every line that
matched a permissionless-shaped pattern (Solidity's `external`/`public` grep, or the per-VM
equivalent). For each one:

1. Read the function. Apply Feynman (`methodology.md`) before anything else.
2. Classify into one of **four** buckets, not three: **permissionless** (no access modifier and no
   internal `msg.sender`/caller check), **role-gated** (a named role/modifier restricts it - record
   which one), **admin-only** (owner/governance/timelock-only), or **Review Required** - the check
   exists but is computed at runtime (a dynamic lookup, a signature-derived condition, a value read
   from storage that isn't a simple role constant) and can't be resolved by pattern-matching or a
   quick read alone. A function with no *modifier* but an inline
   `require(msg.sender == pendingOwner)` is role-gated, not permissionless - read the body, don't
   trust the signature alone. **Review Required is not a placeholder to clear later - it's the
   bucket most likely to hide a real bug, precisely because it's the one a grep-driven pass can't
   resolve on its own.** Every entry in it gets an explicit follow-up: trace the dynamic condition
   by hand (what can make it evaluate true?) before it's allowed to move to role-gated or
   permissionless - never leave it silently mis-classified as role-gated just because *some* check
   is present.
3. Trace its call chain: does it call an internal function that writes state? That internal
   function inherits the *weakest* caller's effective access - record that, it's exactly the seam
   the sibling rule and the asymmetry lens both hunt.
4. Note: value flow (in/out/none), reentrancy guard present, pausable, initializer.

For **≤20 files**, read them directly. For **>20**, dispatch subagents in parallel (one per
subsystem, ≤10 files each), each returning the same structured extraction - never a prose summary
you have to re-derive facts from. The grep-verified candidate list from Phase 0 is the tie-breaker
on any conflict between a subagent's summary and the actual line: **the grep result and your own
read of that exact line always win.**

For **web**, `facts.json["surface"]` (also written to `xray/surface.tsv`) is the merged endpoint
table. For each row with `auth: unknown`: read the actual handler (if source is available) or
replay the request in Burp with and without credentials (`local-tooling.md`) and fill it in by
hand - `unknown` is a todo, not a classification.

## Phase 2 - invariants (web3) / authorization model (web) / attack surface (binary)

**Web3 invariants.** Derive them through independent lenses - accounting, authority, ordering,
equivalence, bounds, trust boundary, promise-vs-enforcement, adversary profit - each written cold,
then merged into one ranked list (`hypothesis-craft.md` §2). The structural passes below are the
mechanical half of that; run them, then add what only reasoning finds. Walk the classified entry
points for:

- **Conservation** - two state variables that move by equal-and-opposite amounts in one function
  body (`totalSupply += x` paired with `balances[to] += x`) implies `A == Σ B[key]`. Note every
  function that writes one *without* the other - that's a candidate leak, not just documentation.
- **Guard-lift** - a `require` on a storage variable is a **per-call guard** (§1, not falsifiable
  on its own). It becomes a **global invariant** only when you grep *every* write site of that
  variable and confirm each one enforces an equivalent check. One unguarded write site makes the
  lifted invariant **On-chain: No** - record that as a high-signal gap, not a clean pass.
- **State machine** - a variable that moves through discrete values (`require(state == A); state =
  B`) with no path back is a one-shot latch; one that another function flips back is a togglable
  flag, not an invariant.
- **NatSpec/doc-stated** - anything the code or docs explicitly promise ("totalSupply always
  equals the sum of balances") goes straight into the catalog, then gets checked against the
  structural scan the same as an inferred one.

Write `xray/invariants.md`: one numbered `INV-<n>` entry per invariant, its derivation (which lines
prove it), and On-chain: Yes/No. This numbered list is what `judging.md` Gate 4 checks findings
against, and what the report's Coverage section counts probed vs. unprobed against.

**This list is also the target list for symbolic and fuzz tooling, not just a narrative artifact.**
Symbolic runs are slow enough that pointing them at a whole codebase is the wrong tradeoff
(`local-tooling.md` 2.1) - but once `xray/invariants.md` exists you know exactly where to aim them:
every `On-chain: No` guard-lift entry names an unguarded write site, and each such function is the
kind of reachability question `halmos` answers well when you state the property as a Foundry test
(`halmos --function check_<property>`), or a fuzzer answers when the property becomes an
`invariant_*` handler (`property-fuzzing.md`). "The invariant pass already told you which functions
are worth the wait" beats both a blind full-codebase run and picking functions by guesswork.

**Web authorization model.** Build the `(endpoint × method × identity × object)` matrix from
`surface.tsv`: for every endpoint that takes an object ID, do the sibling paths (same resource,
different verb) all enforce the same check? Write `xray/authz-matrix.md` - the empty cells (an
identity/object combination nobody tested) are exactly what `packs/web/agents/access-control-agent.md`
drains first.

**Binary attack surface.** Run `checksec` (mitigations), then `file`/`strings`/`readelf` for a
first pass (`local-tooling.md`). Enumerate every input boundary: parsed file formats, IPC/socket
handlers, exported native functions called from managed code, CLI argument parsing. Write
`xray/attack-surface.md` - one entry per boundary, the trust level of its input, and which
memory-safety class (`packs/binary/vectors/*.md`) applies to that boundary's shape.

## Phase 3 - the architecture map

Write `xray/architecture.json` (schema in `report-formatting.md`'s Architecture Diagram section -
nodes, edges, groups) and run `sieve xray map` to render `architecture.svg`. This is the one artifact every reader opens first; keep node/edge counts
inside the budget table in `report-formatting.md` and prioritize completeness (every contract or
service that holds funds, gates access, or sits on a critical path is visible) over compression.

## Phase 4 - the git-history security pass

`sieve xray git` is scoped to `HEAD` only and never describes another branch's code. It surfaces,
mechanically: fix-scored commits (message + diff-shape heuristics - a candidate, not a verdict),
per-file hotspots, dangerous-area churn (access control, fund flows, oracle/price, crypto,
signatures - by filename and commit-message pattern), late changes before the engagement started,
internalized forked dependencies, and TODO/FIXME markers with their blame. Read the top
fix-candidates' actual diffs before citing them - the score is a prioritization signal, not proof
that a commit fixed a vulnerability.

**Five Whys on every fix-scored commit worth a closer look.** Don't stop at "this commit changed
line 40" - ask why the change was made, then why *that* was necessary, recursively, until the
answer is a root cause rather than a symptom. A commit message reading "fix overflow in withdraw"
prompts: why was withdraw overflow-prone? → because it used raw arithmetic → why raw arithmetic
here specifically when the rest of the file uses SafeMath? → because this function was added later,
copy-pasted from a different module that predates the SafeMath convention. That last answer is
usually where the *pattern* worth checking elsewhere in the codebase actually lives - a symptom-level
read stops at "overflow, now fixed" and never asks whether the same copy-paste-from-an-older-module
pattern reappears somewhere the fix commit didn't touch.

**Regression detection as its own named finding category.** A diff in the *current* review that
touches the same lines a past fix-commit touched, in the reverse direction, is not an ordinary
change - it's a candidate silent revert of a prior security fix. Cross-reference every file in the
current review scope against `sieve xray git`'s fix-candidate list: if a line a past fix-commit
specifically added or changed is absent, altered back, or bypassed in the code under review, record
it explicitly as **REGRESSION**, not as a fresh finding discovered independently - the git-blame
trail *is* the evidence, and citing "this exact protection existed and was removed" is a stronger,
faster-to-verify claim than re-deriving the vulnerability from first principles.

## The verdict

Close the x-ray with one paragraph: the protocol/app/binary's type, its trust model in one
sentence, and the 3–5 attack surfaces worth spending the first hour on - ranked by
(invariant/authz gap severity) × (git-history hotspot) × (protocol-type relevance), not
alphabetically. This is what `dispatch.md` reads to build the hit list every hunting agent's
bundle carries.
