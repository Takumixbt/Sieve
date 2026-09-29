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
   GATE 0 ── hedge/theoretical language? ─────────────────► DEMOTE (send back for a real trace)
        │ clears — cheap pre-filter, run before the rest
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

Before running the sequence, ask the one question that matters: *can an attacker do this right
now, against a real user who took no unusual action, causing real harm?* Kill on sight, before
Gate 1, any finding whose own wording contains:

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

The report says which findings are PoC-proven and which are trace-only. Never disguise the
difference.

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
