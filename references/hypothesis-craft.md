# Hypothesis craft — seeing what no one else sees

`methodology.md` says how to *read*. This file says how to *think once you've read*: how to turn a
codebase, an API, or a binary into a short list of sharp, falsifiable ideas that nobody else on the
program has tested. It is the part of the skill where you are expected to have a mind of your own —
inside the bright lines `shared-rules.md` sets (imagination generates, evidence promotes).

Four habits, in the order they pay: **invariants** (what must stay true), **asymmetries** (where the
system is lopsided), **history** (what already went wrong, here and elsewhere), and the
**roaming pass** (what nobody would have looked for). Then the standard a hypothesis has to meet
before it costs you an hour.

---

## 1 · A hypothesis is a bet with a price tag

A hypothesis is not "this looks risky." It is a claim that can lose. Every one you write down — in
`raw/`, in a `HYPOTHESIS` block, in a frontier row's note — carries five things:

```
assumption:   the specific belief the code/system is relying on            ("the caller already validated this")
break:        the one action that would make that belief false               ("send X in a form the validator never sees")
observable:   what you'd see if the belief is false                          ("a 200 with another tenant's row")
cheapest test: the smallest experiment that would show it in minutes         ("replay one request under session B")
why-unseen:   why this hasn't been found already                             ("the only prior audit excluded this module")
```

**Kill-first ordering.** Rank hypotheses by *(value at stake × probability the assumption is false)
÷ cost of the cheapest test*, and run the cheap, high-value ones first. A hypothesis whose cheapest
test is expensive earns a smaller test first (a read, a single request, a fork-test stub) before it
gets a real one.

**The falsifiability check.** If you can't say what result would kill it, it's a worry, not a
hypothesis. Rewrite it until a single experiment can lose.

**Why-unseen is the asymmetric part.** If your answer is "no reason — anyone would find this," it's
probably already reported, or already handled: run the prior-art sweep (`knowledge.md`) before
spending effort. If your answer is specific ("the scope notes of three audits all exclude it"; "it
only breaks after the second upgrade"; "it's on the path only reachable from the mobile client"),
you have found unclaimed ground — spend the hour there.

---

## 2 · Intelligent invariants

An invariant is a statement the system's designers rely on without enforcing everywhere. Most
serious bugs are an invariant that held at every place someone looked and failed at one place
nobody did. The craft is deriving the *right* invariants — not the obvious ones the tests already
cover, and not so many that none get properly attacked.

### 2.1 Derive through independent lenses, then merge

A single perspective produces the invariants that perspective finds natural, and misses the rest.
So derive them the way a panel would: **several lenses, each run cold, then a merge.** Write each
lens's candidates to its own scratch list before reading any other lens's list — the point is
independence, not agreement.

| Lens | Question it asks | Example candidate |
|---|---|---|
| **Accounting** | What quantities are conserved, and which writers touch each term? | `Σ balances == totalSupply`; credits − debits == held funds |
| **Authority** | Who is *allowed* to change each piece of state, and who *can*? | Only the role holder can raise the cap — is every writer gated? |
| **Ordering / time** | What must be true across a sequence, or between two moments? | Rate never decreases; a token used once stays used |
| **Equivalence** | Which two paths are meant to reach the same outcome? | Bulk import ≡ N single creates; `exactIn` ≡ `exactOut` up to rounding |
| **Bounds & monotonicity** | What must never exceed, underflow, or go backward? | Debt ≥ 0; fee ≤ 100%; nonce strictly increasing |
| **Trust boundary** | What does each component assume about the one before it? | "The API already authenticated this call" — does anything re-check? |
| **Promise vs. enforcement** | What do the docs, comments, UI, or marketing promise that no code enforces? | "Funds are always withdrawable"; "users only see their own data" |
| **Adversary profit** | Over any sequence of legal actions, can an unprivileged actor end with net profit? | Deposit → donate → redeem loop returns more than it costs |

Web and binary targets use the same lenses with different nouns: tenant isolation (authority),
idempotent retries (equivalence), object lifetime and length provenance (accounting / bounds),
"the parser trusts this field" (trust boundary).

**Merge step.** Pool the lists, drop duplicates, and for every survivor write one line:

```
INV-<n> | statement | derived-from: <lens> | writers/violators to check: <list> | how to test: <assert / fuzz property / request diff>
```

Rank by value gated × likelihood of a hole. This numbered list is what `judging.md` Gate 4 checks
findings against and what the report's Coverage section counts probed vs. unprobed against
(`xray.md` Phase 2). An invariant you never attacked is a hope, not a verified property.

### 2.2 The invariant must be able to fail (anti-vacuity)

A property test that cannot fail is worse than no test — it manufactures confidence. Before you
trust any "the invariant held" result (a fuzz run, a symbolic run, a request sweep):

- **Plant the bug.** Temporarily weaken the guard in your scratch copy (or pick a known-broken
  variant) and confirm the property *does* fail. If it doesn't, the harness is vacuous.
- **Check the handlers reach the risky code.** A fuzz harness whose actions never call the function
  you care about, or whose preconditions are never true, proves nothing. Look at coverage for the
  specific lines the invariant protects (`property-fuzzing.md`).
- **Don't let the harness fix the bug for you.** Handlers that clamp inputs to "reasonable" values
  can make a real failure unreachable. Bound for *feasibility*, not for *safety*.

### 2.3 Independent references

When you compare the target against a reference — a standard's reference implementation, a spec, a
second library, a previous version — first check the reference is *independent*: not copied from the
same source, not sharing the bug. Then classify every mismatch instead of defaulting to "bug found":

`target defect` · `reference defect` · `harness defect` · `spec ambiguity` · `unknown (needs a tie-break)`

Only the first is a finding. The others are still worth a note — a spec ambiguity is where the next
implementation goes wrong.

---

## 3 · Asymmetric thinking

Systems are built symmetrically in the designer's head and lopsided in reality. The bugs live in the
lopsidedness. For each component, go through this list and write one line per imbalance you find —
each line is a hypothesis waiting for its cheapest test.

1. **Attention.** Where did everyone else spend nothing? Explicit scope exclusions in prior audits,
   legacy and deprecated code still holding value, glue/config/deploy scripts, admin tooling, the
   mobile client's API, the module that "just works." Read the prior audits' *exclusions* first.
2. **Cost.** What does it cost to control the mechanism versus what it gates? Quorums, auctions,
   rate limits, bonds, reward caps — compute the price of tipping each against the value behind it.
3. **Information.** What does the attacker know that the system assumes they don't (public
   parameters, mempool/queue visibility, an identifier that "isn't secret" but is treated as if it
   were), and what does the system assume the attacker *can't compute*?
4. **Time.** The attacker chooses *when*. Ordering, staleness, races, the moment between check and
   use, the moment between process start and policy in force, the window after an upgrade.
5. **Layers.** Which layer has the final word — and is it the one everyone assumes? A component's
   own access control means little if a layer above it can overwrite it.
6. **Pairs.** Operations that should mirror and don't: deposit/withdraw, create/delete, encode/
   decode, lock/unlock, read/write, the guarded verb and its unguarded sibling, the API and the
   admin UI hitting the same store.
7. **Failure.** What does the system do when a dependency is down, a call partially succeeds, a
   value is zero, empty, maximal, or the very first/last of its kind? Happy paths get tested; error
   paths get trusted.
8. **Scale and order.** First user, last user, N = 0, N = huge, batch vs. single, concurrent vs.
   serial.

You don't need all eight on every component — you need to have *looked* through all eight and
recorded which ones produced nothing. Two or three lines per component is normal; zero means the
lens wasn't applied.

### 3.1 Two moves that generate non-obvious ideas

- **Same mistake, different place.** The developer who wrote one unchecked comparison wrote others.
  Once anything is found — by you, by a past fix-commit, by a precedent — grep for its *shape*, not
  its name (`knowledge.md`'s "what changed" method).
- **Assume it's broken; build the exploit; find where it won't build.** Write the attack as if the
  bug existed. The step where it fails to compile or run is either the guard you missed (the bug
  is dead) or the precondition you can manufacture (the bug is alive). This is the `construct`
  rung of the stuck ladder used as a discovery tool, not just an unstick tool.

---

## 4 · Learning from history — the target's, the field's, and your own

Persistence without memory just repeats itself. Three ledgers, read *before* the hunt and written
*after* it:

**The field's ledger — precedent.** `sieve kb prime` (`knowledge.md`), disclosed reports for the
same stack, post-mortems for the same protocol shape. Read for the *question the researcher asked*,
not the payload.

**The target's ledger — its own past.** `sieve xray git` fix-commits and dangerous-area churn; prior
audit reports; past incidents; previous versions. Three standing questions:

- *Fix → siblings.* Every fix is a confession of a mistake. Where else did the same author, module,
  or copy-pasted pattern make it? (`xray.md` Phase 4's Five Whys.)
- *Audit → gaps.* What did the last review exclude, time-box, or never reach? That's where the next
  finding is; the prior report is a map of unlooked-at ground.
- *Regression.* Is a past fix still in place, or has a refactor quietly undone it?

**Your own ledger — lessons.** The most under-used source. `sieve kb lesson` writes a card for each of:

| Kind | Write one when | What the card captures |
|---|---|---|
| `false-positive` | A finding died at the gate | The wrong assumption that made it look real; the guard that saved the target |
| `miss` | Something you didn't find surfaced later (another hunter, a post-mortem) | The lens that would have caught it |
| `revived` | A dead end turned out alive | Which ladder rung revived it |
| `technique` | A move unexpectedly paid | The move, and the target shape it worked on |

`sieve kb prime` surfaces the lessons that match this engagement's domain and stack, so the same
false-positive shape doesn't cost you a day twice. At the end of every engagement, `sieve kb
writeback` turns confirmed findings *and* the killed hypotheses (frontier rows closed `dead`, with
their ladder attempts) into cards — non-production outcomes are data, not waste.

**The post-mortem (five minutes, every engagement).** For each hypothesis that died: what belief
did I hold that turned out false? For each finding: what made it findable — which lens, which
asymmetry, which precedent? For each hour that produced nothing: what should I have tried first?
Write the answers as lessons; the next engagement reads them.

---

## 5 · The roaming pass — hunt what nobody would have looked for

Every engagement ends its hunting with a pass whose only job is to find the *category* you and the
lens agents didn't consider. It runs when the frontier drains and before convergence is declared
(`dispatch.md`).

1. **List the negative space.** Write down every class the vector cards, the lens agents, and your
   own hypotheses covered. That list is what you *did* look for.
2. **Ask what this specific system is, and what's unusual about it.** A bridge, a checkout flow, a
   parser, an SSO integration, an upgrade path, an AI feature — what is the one thing this kind of
   system does that generic bug classes don't describe? Its state machine, its finality assumptions,
   its recovery flow, its message ordering, its migration.
3. **Generate at least three hypothesis classes not on the list from step 1**, each with the five
   parts from §1, and run their cheapest tests. Most die. The ones that don't are the findings that
   make the engagement different from everyone else's.
4. **Record it.** Roaming-pass hypotheses go to `raw/roaming.md` with their outcome, including the
   dead ones — they seed the next engagement's lessons.

---

## 6 · Working freely without going off the rails

The freedom in this file is in *generating and testing* ideas. It never extends to *reporting* them:

- Imagination proposes; a re-read, a request, a trace, or a fork test promotes. Nothing you invented
  from memory is a fact until you've verified it in this turn.
- When you catch yourself writing *presumably*, *likely*, *should*, *typically*, or *I recall* about
  something a finding depends on — stop and check it with a tool. Those words mark the moment
  a guess is about to be laundered into a claim (`shared-rules.md`'s tripwires).
- A hypothesis that can't be tested with what you have isn't discarded — it becomes a `blocked`
  frontier row naming exactly what's missing (`sieve frontier block --reason tooling|credentials`),
  so the gap is on the record instead of in your head.
- When this skill is silent, decide — maximise coverage, record the choice in
  `.sieve/assumptions.md`, keep moving. When it speaks (a gate, a fence, a proof requirement),
  comply exactly; a clever reason to skip a bright line is the signal you're about to make an error.
