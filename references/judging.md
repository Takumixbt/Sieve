# Judging — the gate every finding must pass

A raw finding is a hypothesis. This is where it becomes a result, or dies. **Discoverer ≠
verifier**: the actor, pass, or agent that raised a finding never runs this file over its own
work. The orchestrator (or a dedicated verifier agent, dispatched fresh — no memory of having
found the thing) runs it after convergence. If you cannot name who discovered a finding, it isn't
ready to be gated (see `dispatch.md`'s bundle spec).

During the hunt you deepen a finding (`methodology.md` Part 3). Here, and only here, you try to
kill it. Fail any gate → **REJECT** or **DEMOTE** to a lead; later gates are not evaluated.

```
   raw finding (SUSPECT)
        │
        ▼
   GATE 0 ── restate in plain words, then hedge/theoretical language? ──► DEMOTE
        │ clears — cheap pre-filter, run before the rest
        ▼
   TRIAGE ── straightforward or complex? ───────────────── complex → second verifier on Gates 1 & 6
        │
        ▼
   GATE 1 ── Refutation ── a real guard blocks the exact step? ──► REJECT / DEMOTE
        │ clears
        ▼
   GATE 2 ── Reachability ── can the vulnerable state exist live? ──► REJECT / DEMOTE
        │ clears
        ▼
   GATE 3 ── Trigger ── unprivileged actor, profitably? ───────► REJECT / DEMOTE
        │ clears
        ▼
   GATE 4 ── Invariant / Intent ── does it break a stated promise? ──► DEMOTE if none named
        │ clears
        ▼
   GATE 5 ── Impact ── material harm to an identifiable victim? ──► REJECT / DEMOTE
        │ clears
        ▼
   GATE 6 ── Proof ── PoC or exact re-read trace exists? ───────► ships as CONFIRMED,
        │                                                          or a labeled strong lead (F9)
        ▼
   CONFIRMED → sieve prove record → verified, ships in the report
```

## Gate 0 — the cheap pre-filter

**Step one, before anything else: restate the finding in one or two plain sentences, with no
jargon copied from the original write-up.** "The function trusts a value that can be manipulated in
the same transaction it's read" is a restatement; "manipulatable price oracle read" is not — it's
just the claim's own vocabulary repeated back. Trail of Bits' own false-positive-elimination work
found that roughly half of false positives collapse at exactly this step: the claim stops making
coherent sense the moment it has to be said plainly instead of in the shape it was pattern-matched
in. If the restatement is circular, vague, or doesn't actually name an attacker action and a
consequence, **DEMOTE before spending any more gate time on it** — this is cheaper than Gate 1 and
catches a different failure mode (an incoherent claim, not a blocked one).

Then ask the one question that matters: *can an attacker do this right now, against a real user who
took no unusual action, causing real harm?* Kill on sight, before Gate 1, any finding whose own
wording contains:

```
"could theoretically..."           "in a worst-case scenario..."
"with the right preconditions..."  "if an attacker were somehow able to..."
"this may allow..." / "might permit..."   (without a traced path proving it does)
"under certain conditions..."      (without naming the conditions and proving they're reachable)
a reference to dead/unreachable code presented as if it were live
```

This wording usually means the discovery pass pattern-matched a shape and described it
defensively instead of tracing attacker → guard → consequence. **DEMOTE to a lead and send it back
for a real trace; do not just delete the hedge words and reclassify it as a finding** — that swaps
the symptom for the disease.

## Triage — route by complexity, not by severity

Once Gate 0 clears, classify the finding before running Gates 1–6:

- **Straightforward**: a single component, a clear mechanism, matches a known `vectors/*.md` card or
  a named CWE pattern directly. Run the six gates as written — one verifier, normal pace.
- **Complex**: reaches across two or more components, the claim is ambiguous, it's a race condition,
  or there's no written spec/invariant to check the claim against (so Gate 4 will require judgment
  rather than a citation). For a complex finding, **Gate 1 (Refutation) and Gate 6 (Proof) each get a
  second, independent pass** — a different verifier (or the same verifier on a fresh read, with no
  memory of the first pass's conclusion) re-runs just those two gates. Disagreement between the two
  passes is itself a signal: DEMOTE rather than average the two verdicts.

This is a routing decision, not a severity one — a Critical finding with a clean, single-component
mechanism is still straightforward; a Low finding that only makes sense as a three-component chain is
still complex. Getting this wrong in the cheap direction (calling something straightforward that
wasn't) is exactly how a plausible-looking but wrong finding survives a single verifier's blind spot;
getting it wrong in the expensive direction only costs a redundant pass.

## Gate 1 — Refutation

Construct the **strongest argument that the finding is wrong**. Find the guard, check, or
constraint that would kill the attack — quote the exact line, re-read it in this turn (never from
memory — `shared-rules.md`'s anti-hallucination rule applies here specifically), and trace how it
blocks the claimed step.

- **Concrete refutation** — a specific guard blocks the exact claimed step → **REJECT** (or
  **DEMOTE** if a real code smell remains worth a note).
- **Speculative refutation** — "probably wouldn't happen," "the caller would surely check,"
  "likely intended" without finding the actual check → **clears**. A vague defense never kills a
  finding; only a guard you can cite does.

## Gate 2 — Reachability

Prove the vulnerable state can exist in a live, deployed system.

- **Structurally impossible** (an enforced invariant prevents it) → **REJECT**.
- **Requires privileged misconfiguration** (an admin must act against documented intent, a
  multisig must collude) → **DEMOTE**.
- **Achievable through normal usage** — ordinary calls, common token behaviors (fee-on-transfer,
  rebasing), ordinary user sequences, standard request flows → **clears**.

## Gate 3 — Trigger

Prove an unprivileged (or minimally privileged) actor can execute it, profitably where relevant.

- **Only a trusted role can trigger** → **DEMOTE**, and report at the lower severity — never
  critical.
- **Admin-action findings — REJECT outright (not even a lead) unless a concrete unprivileged
  amplifier is named.** This applies only when the *harmful* action requires an admin/owner/keeper
  to act, not to ordinary attacker actions. Clears only with one of:
  - **race** — the admin sets X mid-flow; an unprivileged user exploits the window before the
    update propagates.
  - **retroactive sweep** — an admin update overwrites a value already credited to someone.
  - **asymmetric formula** — the admin's output feeds a formula an unprivileged actor profits from.
  - **access gap** — the "admin" gate is itself the bug (missing guard, tautological check, missing
    init guard).
  No amplifier named → **REJECT**. Named → judge the *unprivileged* path from here on.
- **Cost exceeds extraction** → **REJECT** — but re-check with a flash loan or an equivalent
  atomic-borrow primitive first: "needs $10M" is not a defense if that capital is borrowable
  inside one transaction.
- **Unprivileged actor triggers profitably** → **clears**.

## Gate 4 — Invariant / Intent

State the specific promise this finding breaks — a conservation law, an access boundary, a stated
protocol guarantee, a documented business rule (`x-ray`'s invariant catalog for web3;
"authenticated users can only see their own records" for web; a memory-safety or trust-boundary
guarantee for binaries). If you cannot name one, this is a code-quality observation, not a
security finding — **DEMOTE**. This gate exists specifically to stop a real-looking bug from
shipping when it doesn't actually violate anything the system promised.

## Gate 5 — Impact

Prove material harm to an identifiable victim.

- **Self-harm only** (attacker loses their own funds/data, no other victim) → **REJECT**.
- **Dust-level, non-compounding, no cascade** → **DEMOTE** to low/informational.
- **Material loss** — user funds drained, protocol insolvent, data breached, account taken over,
  arbitrary code execution — → **CONFIRMED**.

## Gate 6 — Proof

A finding that clears Gates 1–5 still needs a receipt before it ships (`sieve prove record`):

- **CRITICAL/HIGH with a runnable PoC** (a fork test, a live request/response pair, a crash under
  a sanitizer, a Frida trace) → **CONFIRMED**, proof-backed.
- **CRITICAL/HIGH with no runnable PoC available** (the harness can't execute code, the target
  can't be safely tested live) → ships as a **strong lead**, explicitly labeled "trace-verified,
  PoC pending," with the exact PoC that *would* confirm it named. Never presented as a proven
  critical — this is the honest floor when execution isn't available, not a way to skip proving.
- **MEDIUM/LOW** — a complete, re-read code trace is acceptable proof on its own.

**Attempt a negative PoC alongside the positive one wherever a runnable PoC is possible at all** —
a second test that asserts the claimed-safe condition and expects the bug to *not* fire under it. A
negative PoC that unexpectedly succeeds (the bug fails to trigger under a condition the finding
claimed was irrelevant) is not a formality that failed; it's active evidence the finding's mental
model of the bug is wrong, and the finding goes back to Gate 1, not straight to CONFIRMED with a
footnote. This catches the specific failure mode Gate 1's refutation pass can miss: a PoC that
happens to work for a reason *other than* the one the finding claims (the "right answer, wrong
mechanism" trap), which a positive PoC alone can never surface since it only ever tests the
condition the discoverer already believed in.

The report says which findings are PoC-proven and which are trace-only, and whether a negative PoC
was attempted and what it showed. Never disguise the difference.

## Confidence

Start at **100**; deduct: partial attack path **−20**, bounded/non-compounding impact **−15**,
requires a specific-but-achievable state **−10**. Confidence ≥ **75** gets a full write-up
(description + fix); below 75 gets description only. The threshold is 75 and not some other number
because every lead-promotion rule below lands a promoted lead at exactly 75 — moving this number
means moving those three rules with it.

**Severity adjustment after the gates**, before computing CVSS (`cvss-guide.md`): attack needs
specific timing (a one-block/one-request window) → −1 level; needs non-trivial *non-borrowable*
capital → −1 level; impact is bounded (profit but not full drain) → −1 level; a fix is already
deployed but not in the reviewed commit → **DEMOTE + note it**.

## Lead promotion

Some leads deserve promotion even without one agent completing a solo path:

1. **Cross-component echo** — the identical root cause is CONFIRMED in component A → promote the
   same pattern in component B (confidence 75).
2. **Multi-agent convergence** — two or more agents independently flagged the same area and it was
   DEMOTED (not REJECTED) → promote (confidence 75).
3. **Partial-path completion** — the only gap is an incomplete trace, but the path is reachable
   and unguarded → promote (confidence 75, description only — deliberately no Fix block, since the
   trace that would justify one was never completed).
4. **Crossover chain** (`crossover.md`) — a finding on one pack that reaches power on another
   (a web admin panel that holds a contract's minter key; a leaked secret that is also a signing
   key) → chain and promote to the combined severity.

## Do Not Report — universal (pack-specific additions live in each `packs/<pack>/judging.md`)

- Theoretical issues with no reachable path on this target.
- Anything requiring the target to already be compromised.
- Best-practice deviations with no demonstrated exploit (missing headers with no shown impact,
  missing NatSpec/docstrings, gas or performance micro-optimizations, linter warnings, naming).
- Admin privileges functioning exactly as documented, with no concrete unprivileged amplifier
  (Gate 3).

When choosing between DEMOTE and REJECT: mechanism real but impact small → DEMOTE to low/info;
mechanism wrong or fully blocked → REJECT. **Never inflate to hit a payout tier.** A calibrated
medium protects the operator's — and your — credibility; an inflated "critical" that a triager
closes as informational costs it.
