# Methodology - how to think, not just what to check

A vector card catalog catches the bugs that already have a name. The bugs that pay the most are
the ones nobody named yet - they come from *how* you reason about a system, not from a longer
checklist. This file is that reasoning (the craft of turning it into sharp hypotheses and
invariants lives in `hypothesis-craft.md` - read the two together): what "done" actually requires, the mental tools, how to
read code so nothing is skimmed, the creativity toolbox, the deepen and chaining loops, how to use
tool output without outsourcing judgment to it, Focus mode, and the transferable mindset lessons
real 2026 incidents actually teach. Methodology attribution: `CREDITS.md`.

---

## Part 0 - the completeness contract

State this once, plainly, because every part below assumes it: **a pass is not complete because
you read the code once and nothing jumped out.** "I read it and it looked fine" is not a
completed hunt - it's an unstarted one that stopped early. Completeness is measured, not felt.

For every component in scope, before it can be marked clean (`sieve frontier done --clean` -
`shared-rules.md`):

- **At least `audit.hypothesis_quota.min_total` distinct hypotheses were written down and tested**
  (`sieve.yaml`, default 8 per agent output file) - not 8 phrasings of the same idea. A hypothesis
  that's just Part 1's Inversion applied to a different variable name is not a second hypothesis.
- **At least `min_techniques` distinct *techniques* from Part 3 were actually applied** (default
  4) - transplant, inversion-of-intent, combinatorial stress, the sibling rule, degenerate inputs,
  backward-from-value, and so on. Four checkmarks on a mental list, not four attempts at the same
  angle.
- **At least one moonshot** (`min_moonshots`, default 1) - a hypothesis that felt like a stretch
  before you tested it. If every hypothesis you wrote down felt safe and expected, you weren't
  actually looking past the obvious.
- **Every reasoning marker Part 1 requires actually fired** - `shared-rules.md` and each agent's
  own frontmatter set a minimum `[Feynman: ...]`/`[Socratic: ...]`/`[Inversion: ...]` count scaled
  to the component's size (`sieve.yaml`'s `audit.markers`); the orchestrator counts them after the
  pass. A component with zero Socratic markers was skimmed, not read - no exceptions for code that
  "looked simple."
- **The component was looked at through the asymmetry list and the invariant lenses**
  (`hypothesis-craft.md` §2–§3) - at least the imbalances found, and an explicit "nothing here" for
  the lenses that came up empty. Two or three lines per component is normal; none means the lens
  wasn't applied, which is the same as not looking.
- **History was consulted before the hunt and written up after it** (`hypothesis-craft.md` §4):
  precedent, the target's own fix-commits and prior audits, and your own lessons ledger (`sieve kb
  prime` surfaces the last one). A hunt that starts from zero is repeating someone's mistake.

This is not busywork for its own sake. It's the mechanical antidote to the two failure modes this
skill is built to prevent: an agent that stops at the first clean-looking read, and an agent that
narrates having looked without the underlying reasoning ever happening. If you can't point to the
specific hypotheses, techniques, and markers that satisfied this contract for a component, it
wasn't actually audited - it was skimmed and described as audited, which `shared-rules.md`'s
anti-hallucination rule and this skill's own design history treat as the same failure either way.

**Never trade quotas for speed.** If a component is small enough that 8 genuinely distinct
hypotheses feels like a stretch, that's a signal to widen the lens (Part 3's transplant technique
exists exactly for this), not to write four hypotheses and stop. If a component is large enough
that 8 hypotheses obviously undercounts it, write more - the number in `sieve.yaml` is a floor
the persistence engine enforces mechanically, never a target to stop at.

---

## Part 1 - the three mental tools

These generalize past any one language or VM without changing shape - the same three tools apply
whether you're reading Solidity, a Python request handler, or a disassembly listing.

### 1. Feynman, first, always

Before reasoning about any function, endpoint, or routine: explain what it does to someone who
doesn't know the language. Try it out loud (or in your working notes). The place where your
explanation goes fuzzy - where you reach for jargon instead of plain meaning - is where you're
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
backward pass before you trust it - this is the same discipline `shared-rules.md`'s persistence
rule requires before closing a frontier row `--clean`.

**When to reach for which:** Feynman is always first, on anything new. Socratic fires the moment a
line's purpose isn't immediately obvious. Inversion fires when a path looks too clean, or the
moment you've reached a "this is fine" conclusion - that conclusion is exactly the trigger to
invert it, not to move on.

---

## Part 2 - the reading discipline (how not to skim)

Mental tools only work on code you actually read. This part is the mechanical half: what "reading
a component" means before Part 1's tools are even applied.

- **Read the whole function before forming an opinion about any line in it.** A guard on line 3
  that looks sufficient is not sufficient if line 11 branches around it. Judging a check in
  isolation, before seeing every path that reaches or bypasses it, is the single most common
  source of a missed finding.
- **Read every caller before trusting a callee's contract, and every callee before trusting a
  caller's assumption.** "This is validated upstream" and "the caller already checked this" are
  claims, not facts, until you've actually opened the upstream file and confirmed it in this same
  session (`shared-rules.md`'s anti-hallucination rule applies to your own reasoning chain, not
  only to citations you put in a finding).
- **Read the tests, deliberately, for what they reveal about intent.** A test asserting a specific
  behavior is the closest thing to a developer stating an invariant out loud - and a test that's
  conspicuously *absent* for an otherwise-tested class of function is itself a signal worth a
  frontier row of its own.
- **Read the diff, not just the current state, for anything git-history flagged.** `sieve xray
  git`'s fix-candidates and dangerous-area hotspots (`references/xray.md` Phase 4) are pointers,
  not conclusions - open the actual commit and read what changed and why before deciding it's
  relevant or irrelevant.
- **Never let a tool's summary substitute for your own read of the cited line.** A subagent's
  structured extraction, a Slither finding's description, a `grep` hit's surrounding context - all
  of them are leads to the real location, never a replacement for opening that location yourself.
  This is `xray.md`'s "the grep result and your own read of that exact line always win" rule,
  restated as a universal reading habit, not just an x-ray-phase rule.
- **Re-read after you think you're done.** The single highest-yield free action in an audit is a
  second pass over code you've already read once, now armed with everything the rest of the
  engagement has taught you about this system's actual conventions and failure shapes. A bug
  invisible on the first read is frequently obvious on the second, once you know what this
  particular codebase's mistakes tend to look like.

## Part 3 - the creativity techniques (the "think sideways" toolbox)

These exist because pattern-matching against known classes has a ceiling, and the highest-value
bugs sit above it. Part 0's contract requires at least four of these per component, genuinely
distinct, before it can close.

- **Transplant.** Take a vector that's native to a *different* pack and ask if it applies here.
  Web's race-condition ("fire two requests, see which check-then-act loses") applied to a
  contract's two-step withdrawal flow. Web3's donation/first-depositor inflation attack applied to
  a web app's "first user of a shared resource sets its price" logic. A binary's TOCTOU applied to
  an API's "check permission, then act 200ms later" pattern. *Worked example:* a web session-fixation
  idea ("does the identifier survive a privilege change?") transplanted onto a contract's role
  system asks "does a role assignment survive whatever the contract calls a 'reset'?" - a question
  the access-control vector cards don't phrase this way, and a bug class they'd otherwise miss.
  The three packs rarely talk to each other's playbooks; that gap is exploitable *by you*, not
  just by an attacker.
- **Inversion of intent.** State the feature's purpose in one sentence, then ask: what's the
  cheapest way to make the system do the opposite while every individual step "succeeds"? This is
  how you find bugs no CWE has a number for - `packs/web3/agents/first-principles-agent.md` calls
  these "bugs that have no name," and the label applies equally outside web3. *Worked example:* a
  "rate limiter" exists to slow an attacker down; ask what makes the rate limiter itself slow down
  a *legitimate* user instead (a shared counter keyed by something an attacker can force onto a
  victim, like an IP behind a shared NAT or proxy).
- **Combinatorial stress.** Take two features that were built and tested independently and ask
  what happens when they run *at the same time*, in *either order*, or when one is mid-flight when
  the other starts. Most integration bugs live here, and most single-feature test suites can't see
  them. *Worked example:* "export to CSV" and "user can set a display name containing arbitrary
  Unicode" were each tested alone; combined, a display name starting with `=` becomes a formula-
  injection payload the moment the CSV opens in a spreadsheet application.
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
- **Mutation of a working exploit.** Once you have one confirmed bug, don't move on immediately -
  mutate the exact payload/call sequence that worked: change the target object, the encoding, the
  order of operations, the actor. A confirmed bug's neighborhood is disproportionately likely to
  hold a second one, because it shares a root cause or a developer's blind spot.
- **Read the error messages and logs as a map.** A stack trace, a verbose error, or a debug log
  line leaked in a response frequently states outright which internal check just ran and what it
  compared - treat every such leak as free reconnaissance pointing at the exact boundary worth
  attacking next.
- **Moonshot quota.** Every hunt writes down at least one hypothesis that feels like a stretch
  before it's investigated - the ones a checklist-only pass would never generate. Most moonshots
  die fast (that's fine, that's what `sieve frontier dead` is for); the ones that survive first
  contact are disproportionately the bugs nobody else submits.

## Part 4 - the deepen loop: a confirmed finding is a root, not a finish line

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

Schedule effort by `score = severity_so_far + evidence_strength + blast_radius` - spend the next
expensive step (a fork test, a live PoC, a fuzzing campaign) on the highest-scoring root first, not
spread evenly.

## Part 5 - chaining low findings into one submission (A→B chains)

Two mediums are sometimes one critical. An HTTP request-smuggling primitive that by itself is
"low confidence, unclear impact" becomes a session-hijack when chained with an open redirect on
the same host. A leaked internal API key (low, "just an internal tool") becomes critical when that
tool turns out to hold a deploy credential. When you find a finding that feels capped, actively
search the rest of this engagement's findings and leads for a second half - see
`references/crossover.md` for the cross-pack version of this same idea (a web control that gates a
web3 privilege, and so on).

## Part 6 - using tools without outsourcing judgment to them

`references/local-tooling.md` names dozens of real tools. Every one of them produces *signal*, and
none of them produces a *verdict*:

- **A scanner's finding is a hypothesis with a head start, not a conclusion.** Run `slither`,
  `nuclei`, `MobSF`, or any other automated tool, and treat every single result the same way you'd
  treat a hand-derived hypothesis: read the actual cited location yourself, apply Part 1's tools to
  it, and only then decide whether it survives contact with the real code. A tool that flags 40
  things and you paste 40 things into `raw.md` is not 40 hypotheses tested - it's zero hypotheses
  tested and 40 unverified claims, which `judging.md` Gate 0 will (correctly) treat as hedged,
  untraced language.
- **A clean scan is not a clean component.** `nuclei` finding nothing means nuclei's templates
  didn't match - it says nothing about a business-logic bug, a first-principles violation, or
  anything Part 3's techniques would find. Never write "no issues found" for a component because
  an automated tool came back empty; write what was actually checked, by hand, and what wasn't.
- **Two tools disagreeing is information, not noise.** When Slither and Aderyn produce different
  results on the same contract (`references/local-tooling.md` 2.1 flags this explicitly), the
  disagreement itself is worth reading into - it usually means the pattern is genuinely ambiguous
  and deserves a closer manual look, not that one tool is simply wrong.
- **A fuzzer or symbolic engine's silence is bounded, not absolute.** A long, clean Echidna run or
  an `angr` exploration that didn't find a path only covers the state space, corpus, and action set
  it was actually given (`references/property-fuzzing.md`'s "reading a pass" section) - say so in
  the coverage write-up.

## Part 6b - when you feel finished (you aren't yet)

The moment a hunt feels complete is the most reliable signal to keep going, because "feels done"
is what every abandoned engagement felt like. Before closing anything, do these five things - each
one is cheap, and each has produced findings on engagements that "felt done":

1. **Write down three things you have not tried** on this component (a different actor, a different
   layer, a different order, a different precondition). Then try the cheapest one.
2. **Re-read your own clean claims** with the inversion question: what would have to be true for
   this to be exploitable, and can I make it true? A clean claim with no inversion attempt on
   record is a guess.
3. **Look at the seams between what you covered** - the boundary between two components you each
   audited separately is a component nobody audited (`crossover.md` for cross-pack seams).
4. **Run the roaming pass** (`hypothesis-craft.md` §5): three hypothesis classes you weren't
   looking for.
5. **Ask what a competitor would do next.** Someone else is on this program with the same tools.
   Their obvious next step is a duplicate; yours should be the step they wouldn't take.

A frontier that's empty is not the same as a component that's exhausted. The persistence engine
enforces the first; this list is how you earn the second.

---

## Part 7 - Focus mode

When the operator names a specific question (`case.md`'s scope, or an explicit `--focus`), every
turn scopes to it. Apply Parts 1–6 the same way, but the frontier (`sieve frontier`) is seeded
only from the named question and its natural neighbors - not the whole surface. Focus mode still
obeys every persistence rule in `shared-rules.md` and Part 0's completeness contract in full: a
narrow scope is not an excuse for a shallow one.

---

## Part 8 - mindset lessons from 2026's real incidents

The `2026-incident-patterns.md` vector cards in every pack (`packs/<pack>/vectors/`) are the
concrete attack shapes; this part is the transferable *thinking* behind them - the framing that let
a researcher or attacker find each one, generalized past the specific domain it happened in. A 2026
incident in web3 and one in a browser sandbox escape frequently share the same underlying question;
learning the question is worth more than memorizing either incident.

1. **Read what the audit explicitly excluded.** An auditor's own scope notes are a map of where
   nobody has looked, not a list of settled ground. *Worked example:* Makina's five independent 2026
   audits all marked oracle/liquidity-pool manipulation out of scope; the attacker's entire method
   was reading those scope notes and going straight for the one surface every firm had agreed not to
   examine. Whenever a target has prior audit reports, read their scope-exclusion sections first,
   not last.
2. **The patch diff is the disclosure.** A vendor withholding root-cause detail buys almost no time
   once a fix ships - the diff itself says exactly where the vulnerable path was. *Worked example:*
   watchTowr reproduced GitLab's CVE-2026-19478 within minutes of the patch landing, using only the
   advisory and the diff; Cosmos Labs' still-unpatched release branches were exploited roughly 20
   hours after the upstream fix went public. A target with a recent upstream security fix not yet in
   its own tagged release is a countdown, not a footnote - diff first (`WEB3-SUPPLY-01`).
3. **Ask what a boundary actually captures, not whether it exists.** A cache key, a signature check,
   a credential comparison - the real question is never "is there a check," it's "does the check's
   *input* fully and uniquely capture what it's supposed to verify, and do every two components that
   rely on it agree about what bytes they're looking at." *Worked example:* Liquid Network's
   rangeproof cache was keyed on data that omitted asset ID and script context, so a valid proof for
   one transaction replayed as "valid" for a different one; RouterOS's SSH auth compared an RSA
   key's modulus but silently skipped its exponent; SAML's "fragile lock" research found the module
   that validates a signature and the module that later processes the assertion can be made to see
   two different logical documents from the same bytes. Apply this question to every comparison,
   cache, or verification step you find - not only the ones that look cryptographic.
4. **Compute cost-to-attack versus value-at-risk - some of 2026's biggest losses needed no code bug
   at all.** *Worked example:* BonkDAO's ~$20M treasury fell to ~$4M in bought governance tokens;
   Neutron's chain-governance seized $9.4M of a *different* protocol's contracts for ~$113K in staked
   tokens. For any governance, quorum, or auction-style mechanism, compute the realistic clearing
   cost against the value it gates before concluding it's safe because "no one would bother"
   (`WEB3-GOV-01`).
5. **Ask which layer actually has ultimate authority - and whether it's the one everyone assumes.**
   A protocol's own multisig is not necessarily the final word on its own contracts. *Worked
   example:* Neutron's chain-level governance could unilaterally rewrite the admin of Astroport/Drop
   contracts, overriding each protocol's own security posture entirely - the vulnerability was in a
   layer neither protocol controlled. For every deployed component, ask explicitly what, from
   outside it, can override its own access control.
6. **Score composability, not components in isolation - a bug chain increasingly beats a single
   "hero" bug.** As individual mitigations (CFI, sandboxing, PAC, hardened allocators, SafeMath)
   raise the cost of one flaw reaching impact, composing several individually-unremarkable
   weaknesses is the lower-cost path to the same outcome. *Worked example:* Orange Tsai's Pwn2Own
   2026 Edge sandbox escape chained four logic bugs with zero memory corruption; Drift's $285M loss
   chained a six-month social-engineering campaign with an unrelated fake-token wash-trading scheme
   - neither half alone reaches real impact. A finding scored "Medium, no direct impact standalone"
   is exactly the shape this pattern hides inside (`methodology.md` Part 4's chaining step exists for
   precisely this - but budget for it as a default question, not a rare exception, given how often
   2026's highest-severity findings needed it).
7. **New capability amplifies old bugs even when the capability itself is sound.** A legitimate new
   primitive can turn a contained, slow-moving compromise into an instant, unrecoverable one.
   *Worked example:* EIP-7702 batch delegation introduced no bug on its own, but let a years-old,
   already-compromised DxSale locker's owner key drain 1,400+ pools atomically instead of one at a
   time. When a target adopts a new standard or primitive, explicitly ask what *existing*,
   otherwise-slow-to-exploit weakness it just made instant or atomic.
8. **Treat a cluster of individually-modest findings as a chain candidate by default - AI compresses
   chaining velocity.** What used to take a human researcher days of manual pivoting, an agentic
   loop now iterates in hours (`WEB-CHAIN-01`; the Hacktron/OpenAI chain that closed the moment a
   more capable model became available). This cuts both ways for an audit: it's a reason a target is
   more exploitable than a pre-2025 checklist would assume, and it's a capability this skill's own
   deepen loop (Part 4) should lean into harder, not treat as an attacker-only advantage.
9. **Never accept a model's self-report as proof of anything, including your own reasoning about
   it.** Anthropic's own 2026 safety report measured a 31.5% raw hijack rate on a shipped browser
   agent before mitigations; EchoLeak was zero-click, fully chained, end to end. Whenever a target
   embeds or orchestrates an LLM/agent, "the model refused" or "the agent said it wouldn't" is not
   evidence - only an externally-observable side effect is
   (`packs/web/agents/ai-native-appsec-agent.md`'s proof-oracle discipline, which generalizes to any
   AI-adjacent finding regardless of pack).

---

## What this file is not

It is not a substitute for the vector cards (`packs/<pack>/vectors/*.md`) - those are the
concrete, fast-recall catalog of what already pays. This file is what you reach for *between* the
cards, when the card catalog runs out and the bug is still there, and the discipline that makes
sure "the card catalog ran out" was actually true rather than assumed.
