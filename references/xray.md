# X-ray — the pre-hunt map, every engagement, every pack

The right division of labor for this step: **grep is the source of truth for which lines are
candidates; the agent reads the source and classifies each one.** A script
that tried to do the classification would be re-implementing Slither/Aderyn (web3) or a real
crawler (web) worse than they do it. `sieve xray <pack>` only ever does the mechanical half —
discovery, line counts, test inventory, and a grep pass — and hands you a list to read.

Output lands in `.sieve/xray/`: `facts.json` (the mechanical layer, per pack), and the narrative
files below, which you write by reading the source facts.json points at.

## Phase 0 — run the mechanical layer

```
sieve xray web3 [--slither report.json] [--aderyn report.json]
sieve xray web  [--openapi doc.json] [--har capture.har] [--url-list urls.txt]
sieve xray git                                   # git-history security pass, any pack
sieve xray map                                   # renders xray/architecture.json you write below
```

Slither/Aderyn output (web3) and OpenAPI/HAR/URL-list input (web) are **corroboration**, not the
x-ray's source of truth — a detector finding lands in `facts.json["tool_leads"]` exactly like a
Solodit precedent (`knowledge.md`): real, but gated (`judging.md`) before it ships. The x-ray never
depends on either being installed; their absence is coverage-debt, never a silent gap
(`shared-rules.md`).

Print what came back before reading further: file count, nSLOC, candidate count. This is the
receipt that Phase 0 actually ran — a summary you narrate without having called the command did
not happen.

## Phase 1 — read the source, classify what grep found

For **web3**, `facts.json["entry_candidates"]` is a list of `{file, line, text}` — every line that
matched a permissionless-shaped pattern (Solidity's `external`/`public` grep, or the per-VM
equivalent). For each one:

1. Read the function. Apply Feynman (`methodology.md`) before anything else.
2. Classify: **permissionless** (no access modifier and no internal `msg.sender`/caller check),
   **role-gated** (a named role/modifier restricts it — record which one), or **admin-only**
   (owner/governance/timelock-only). A function with no *modifier* but an inline
   `require(msg.sender == pendingOwner)` is role-gated, not permissionless — read the body, don't
   trust the signature alone.
3. Trace its call chain: does it call an internal function that writes state? That internal
   function inherits the *weakest* caller's effective access — record that, it's exactly the seam
   the sibling rule and the asymmetry lens both hunt.
4. Note: value flow (in/out/none), reentrancy guard present, pausable, initializer.

For **≤20 files**, read them directly. For **>20**, dispatch subagents in parallel (one per
subsystem, ≤10 files each), each returning the same structured extraction — never a prose summary
you have to re-derive facts from. The grep-verified candidate list from Phase 0 is the tie-breaker
on any conflict between a subagent's summary and the actual line: **the grep result and your own
read of that exact line always win.**

For **web**, `facts.json["surface"]` (also written to `xray/surface.tsv`) is the merged endpoint
table. For each row with `auth: unknown`: read the actual handler (if source is available) or
replay the request in Burp with and without credentials (`local-tooling.md`) and fill it in by
hand — `unknown` is a todo, not a classification.

## Phase 2 — invariants (web3) / authorization model (web) / attack surface (binary)

**Web3 invariants.** Walk the classified entry points for:

- **Conservation** — two state variables that move by equal-and-opposite amounts in one function
  body (`totalSupply += x` paired with `balances[to] += x`) implies `A == Σ B[key]`. Note every
  function that writes one *without* the other — that's a candidate leak, not just documentation.
- **Guard-lift** — a `require` on a storage variable is a **per-call guard** (§1, not falsifiable
  on its own). It becomes a **global invariant** only when you grep *every* write site of that
  variable and confirm each one enforces an equivalent check. One unguarded write site makes the
  lifted invariant **On-chain: No** — record that as a high-signal gap, not a clean pass.
- **State machine** — a variable that moves through discrete values (`require(state == A); state =
  B`) with no path back is a one-shot latch; one that another function flips back is a togglable
  flag, not an invariant.
- **NatSpec/doc-stated** — anything the code or docs explicitly promise ("totalSupply always
  equals the sum of balances") goes straight into the catalog, then gets checked against the
  structural scan the same as an inferred one.

Write `xray/invariants.md`: one numbered `INV-<n>` entry per invariant, its derivation (which lines
prove it), and On-chain: Yes/No. This numbered list is what `judging.md` Gate 4 checks findings
against, and what the report's Coverage section counts probed vs. unprobed against.

**Web authorization model.** Build the `(endpoint × method × identity × object)` matrix from
`surface.tsv`: for every endpoint that takes an object ID, do the sibling paths (same resource,
different verb) all enforce the same check? Write `xray/authz-matrix.md` — the empty cells (an
identity/object combination nobody tested) are exactly what `packs/web/agents/access-control-agent.md`
drains first.

**Binary attack surface.** Run `checksec` (mitigations), then `file`/`strings`/`readelf` for a
first pass (`local-tooling.md`). Enumerate every input boundary: parsed file formats, IPC/socket
handlers, exported native functions called from managed code, CLI argument parsing. Write
`xray/attack-surface.md` — one entry per boundary, the trust level of its input, and which
memory-safety class (`packs/binary/vectors/*.md`) applies to that boundary's shape.

## Phase 3 — the architecture map

Write `xray/architecture.json` (schema in `report-formatting.md`'s Architecture Diagram section —
nodes, edges, groups) and run `sieve xray map` to render `architecture.svg`. This is the one artifact every reader opens first; keep node/edge counts
inside the budget table in `report-formatting.md` and prioritize completeness (every contract or
service that holds funds, gates access, or sits on a critical path is visible) over compression.

## Phase 4 — the git-history security pass

`sieve xray git` is scoped to `HEAD` only and never describes another branch's code. It surfaces,
mechanically: fix-scored commits (message + diff-shape heuristics — a candidate, not a verdict),
per-file hotspots, dangerous-area churn (access control, fund flows, oracle/price, crypto,
signatures — by filename and commit-message pattern), late changes before the engagement started,
internalized forked dependencies, and TODO/FIXME markers with their blame. Read the top
fix-candidates' actual diffs before citing them — the score is a prioritization signal, not proof
that a commit fixed a vulnerability.

## The verdict

Close the x-ray with one paragraph: the protocol/app/binary's type, its trust model in one
sentence, and the 3–5 attack surfaces worth spending the first hour on — ranked by
(invariant/authz gap severity) × (git-history hotspot) × (protocol-type relevance), not
alphabetically. This is what `dispatch.md` reads to build the hit list every hunting agent's
bundle carries.
