# Methodology — how to think, not just what to check

A vector card catalog catches the bugs that already have a name. The bugs that pay the most are
the ones nobody named yet — they come from *how* you reason about a system, not from a longer
checklist. This file is that reasoning, credited to where Sieve learned it, plus the discipline
that keeps creative reasoning from turning into unfounded speculation.

## Part 1 — the three mental tools

Adapted directly from Pashov Audit Group's `senior-auditor-sop.md` (MIT-licensed;
`third_party/pashov-skills-LICENSE`). They generalize past Solidity without changing shape.

### 1. Feynman, first, always

Before reasoning about any function, endpoint, or routine: explain what it does to someone who
doesn't know the language. Try it out loud (or in your working notes). The place where your
explanation goes fuzzy — where you reach for jargon instead of plain meaning — is where you're
papering over an assumption, and that's where the bug is.

*"It picks up the protocol's commission off the user's payment and moves it to the treasury."*
Now: what if the payment arrives in a form this sentence didn't account for? Native ETH where the
code assumes an ERC-20 call? A multipart upload where the code assumes a single file? A signed
message where the code assumes a fresh nonce? The plain-English version breaks. That's the bug.

### 2. Socratic questioning

For every line: why is this here? What does it assume? What happens when the assumption breaks?
Don't accept "because that's how it's written" or "the name says so." The first answer is usually
a restatement of the code; the real assumption is two or three "whys" deeper.

```
if (asset != NATIVE) IERC20(asset).transferFrom(msg.sender, address(this), amount);
```
- Why the branch? → native tokens aren't ERC-20-transferable.
- Why no `else`? → the developer assumed native value arrives via `msg.value`.
- Where is `msg.value == amount` enforced on that path? → nowhere. Bug.

### 3. Inversion

After you understand what the code is *supposed* to do, ask how you'd make it *not* do that.
Same code, attacker's eye instead of builder's eye. For every check: what value slips past it? For
every state update: what state am I in the instant before it runs? A clean-looking path gets one
backward pass before you trust it — this is the same discipline `shared-rules.md`'s persistence
rule requires before closing a frontier row `--clean`.

**When to reach for which:** Feynman is always first, on anything new. Socratic fires the moment a
line's purpose isn't immediately obvious. Inversion fires when a path looks too clean, or the
moment you've reached a "this is fine" conclusion — that conclusion is exactly the trigger to
invert it, not to move on.

## Part 2 — the creativity techniques (the "think sideways" toolbox)

These exist because pattern-matching against known classes has a ceiling, and the highest-value
bugs sit above it. Use at least one per component beyond the obvious checklist pass — the
persistence rule in `shared-rules.md` requires a `transplant` attempt before any row closes clean.

- **Transplant.** Take a vector that's native to a *different* pack and ask if it applies here.
  Web's race-condition ("fire two requests, see which check-then-act loses") applied to a
  contract's two-step withdrawal flow. Web3's donation/first-depositor inflation attack applied to
  a web app's "first user of a shared resource sets its price" logic. A binary's TOCTOU applied to
  an API's "check permission, then act 200ms later" pattern. The three packs rarely talk to each
  other's playbooks; that gap is exploitable *by you*, not just by an attacker.
- **Inversion of intent.** State the feature's purpose in one sentence, then ask: what's the
  cheapest way to make the system do the opposite while every individual step "succeeds"? This is
  how you find bugs no CWE has a number for (pashov's `first-principles-agent.md` calls these
  "bugs that have no name").
- **Combinatorial stress.** Take two features that were built and tested independently and ask
  what happens when they run *at the same time*, in *either order*, or when one is mid-flight when
  the other starts. Most integration bugs live here, and most single-feature test suites can't see
  them.
- **The sibling rule.** The single highest-yield web pattern known: the same operation, implemented
  two ways, where one path enforces a check the other forgot. A guarded `GET` with an unguarded
  `PUT`/`PATCH`/`DELETE` sibling. A validated form submission next to an unvalidated bulk-import
  endpoint doing the same write. Whenever you find *any* guard, immediately go looking for the
  sibling that might not have it.
- **Degenerate inputs.** Zero, the maximum representable value, an empty collection, the very
  first caller, the very last one, a value equal to a boundary constant exactly. Systems are
  usually tested in the middle of their input space and rarely at its edges.
- **Follow the money/trust, backward.** Pick the single most valuable state a compromised
  component could reach (an admin key, a large balance, a root shell) and walk backward: what is
  the cheapest, least-privileged action that starts a chain ending there? This backward-critical
  pass is how you rank *where to spend the next hour*, not just what to check.
- **Moonshot quota.** Every hunt writes down at least one hypothesis that feels like a stretch
  before it's investigated — the ones a checklist-only pass would never generate. Most moonshots
  die fast (that's fine, that's what `sieve frontier dead` is for); the ones that survive first
  contact are disproportionately the bugs nobody else submits.

## Part 3 — the deepen loop: a confirmed finding is a root, not a finish line

A CONFIRMED finding earns its severity once. Before it ships, re-attack it along three axes and
take the worst that survives `judging.md`:

1. **Chain it.** Does this bug, combined with a second weakness (even a DEMOTE-tier one), reach
   further? A medium IDOR that reaches a multisig proposal queue is a critical.
2. **Alternate trigger.** Is there a second, cheaper, or more-permissioned-free way to reach the
   same vulnerable state? The cheapest trigger sets the real severity.
3. **Lower the precondition.** Does the bug require "the admin misconfigures X"? Can you show an
   *unprivileged* amplifier instead (a race, a retroactive sweep, an asymmetric formula) that gets
   there without that assumption? `judging.md` Gate 3 requires exactly this for any admin-adjacent
   finding to clear at all.

Schedule effort by `score = severity_so_far + evidence_strength + blast_radius` — spend the next
expensive step (a fork test, a live PoC, a fuzzing campaign) on the highest-scoring root first, not
spread evenly.

## Part 4 — chaining low findings into one submission (A→B chains)

Two mediums are sometimes one critical. An HTTP request-smuggling primitive that by itself is
"low confidence, unclear impact" becomes a session-hijack when chained with an open redirect on
the same host. A leaked internal API key (low, "just an internal tool") becomes critical when that
tool turns out to hold a deploy credential. When you find a finding that feels capped, actively
search the rest of this engagement's findings and leads for a second half — see
`references/crossover.md` for the cross-pack version of this same idea (a web control that gates a
web3 privilege, and so on).

## Part 5 — Focus mode

When the operator names a specific question (`case.md`'s scope, or an explicit `--focus`), every
turn scopes to it. Read `Part 1–4` the same way, but the frontier (`sieve frontier`) is seeded
only from the named question and its natural neighbors — not the whole surface. Focus mode still
obeys every persistence rule in `shared-rules.md`: a narrow scope is not an excuse for a shallow
one.

## What this file is not

It is not a substitute for the vector cards (`packs/<pack>/vectors/*.md`) — those are the
concrete, fast-recall catalog of what already pays. This file is what you reach for *between* the
cards, when the card catalog runs out and the bug is still there.
