# Knowledge — grounding hypotheses in what has actually paid

The highest-ROI pre-hunt activity is reading what other hunters already found and got paid for.
Sieve doesn't vendor a knowledge base that drifts stale in weeks; it carries the method and, for
web3, a real, freely-licensed dataset (`kb/seed/`) plus live access to Solodit — and a local store
that every engagement's own confirmed findings grow (`sieve kb writeback`).

## The "what changed" method (the highest-ROI pattern, every pack)

```
1. Find a disclosed report / precedent for the SAME stack as this target
   (web: same framework — Django REST, Express, Rails.
    web3: same protocol shape — lending, AMM, bridge, staking.
    binary: same class of target — a parser, a network daemon, a setuid tool.)
2. Find the fix commit / patched version → read the diff.
3. Identify the anti-pattern in the vulnerable code.
4. Grep THIS target's source for that same anti-pattern.
5. Test every match.
```

It works because different teams reproduce the same mistakes in the same frameworks and the same
protocol shapes. You are transplanting a *pattern*, not copying a PoC.

## `sieve kb` — the commands

```
sieve kb search "<query>" [--domain web3|web|binary] [--online]   # local cards + Solodit (web3)
sieve kb osv --package <name> --ecosystem npm --version <v>       # known CVEs for a dependency
sieve kb use <ref> --finding F-001 --class <bug-class>            # a precedent that helped -> curated card
sieve kb add --title ... --domain ... --class ... --url ...       # a report you found by hand (search/writeups)
sieve kb writeback                                                # confirmed findings -> confirmed cards
sieve kb prime                                                    # writes xray/precedents.md for this engagement
```

`sieve kb search --online` calls Solodit through a rate-limited broker (20 req/60s, shared across
every parallel agent — nobody should ever call the API directly; go through this command).
Twelve agents searching independently would blow the limit in seconds; the broker queues and
caches so the limit holds regardless of how many agents ask.

## Sources, in priority order

**Web3**
1. **Solodit** (`sieve kb search --online`) — tens of thousands of findings from Code4rena,
   Sherlock, Cantina, and the audit firms. Filter by impact/tags/protocol category.
2. **Slither/Aderyn leads** from this engagement's own x-ray (`xray.md`) — already-run, real
   detector output for this exact target.
3. **DeFiHackLabs** and **rekt.news** — runnable Foundry PoCs and post-mortems for real, historical
   exploits; the best "read the actual exploit" source when Solodit's summary isn't enough.
4. **The program's own disclosed reports and prior audits** — the prior-art sweep below.

**Web**
1. **HackerOne Hacktivity** / **Bugcrowd Crowdstream** — filter disclosed + awarded, by program and
   class.
2. **PortSwigger Research** — the canonical source for genuinely new web attack classes.
3. **The target's own repo** — fix commits are the "what changed" goldmine; GitHub code search for
   internal package names surfaces dependency-confusion opportunities.

**Binary**
1. **NVD/OSV** (`sieve kb osv`) — mapped from the target's detected library versions.
2. **GitHub Security Advisories** and the project's own advisories.
3. The CVE writeup itself, read for exactly one thing: where the attacker-controlled length or the
   freed pointer entered — that's the shape to grep for on this target.

## Prior-art / duplicate sweep — run before hunting, every engagement

```
1. IN-REPO    /audits, /security, SECURITY.md, any prior audit PDF in the target's own repo
2. CONTEST    a prior Code4rena/Sherlock/Cantina contest report for this exact protocol
3. PLATFORM   the program's own disclosed reports, filtered by class
4. PUBLIC     search writeups and aggregators for the target's name
```

This does two things: it kills duplicates before you write them up (the single most common
rejection reason on every platform), and it shows you where nobody has looked — the component a
prior audit skipped, the class a contest under-covered, the version bumped after the last review.
Record the swept sources and the known-issue list in `.sieve/plan.md` (`dispatch.md`) so the gate
rejects a re-find on sight.

## Write-back — how an engagement makes the next one sharper

`sieve kb use <ref> --finding <id>` promotes a precedent you actually *used* (not every hit — only
the one that moved a hypothesis forward) to a **curated** card in `~/.sieve/kb/`. `sieve kb
writeback`, run at the end of an engagement, turns every gate-CONFIRMED finding at or above
`kb.writeback.min_confidence` (75 by default) into a **confirmed** card — root cause, attack path,
fix, tagged with the `tell:` grep signature that would catch the same shape again. Both write real
markdown files with YAML frontmatter you can read, edit, or delete by hand; the local index
(`sieve kb index`) is a cache rebuilt from them, never the source of truth.

**Learn only from proof.** A card's `status` never downgrades on merge, and a card is never created
from a SUSPECT or a hypothesis — only from something that cleared `judging.md`, or a precedent you
consciously chose to trust. Secrets are stripped automatically before anything is written
(`kb_store.sanitize`) — never rely on this as the only check; don't paste a live credential into a
card body in the first place.

## Lessons — learning from your own history

Precedent is other people's history. Your own is more useful and almost never recorded. Four kinds
of lesson, each a card (`sieve kb lesson --kind ... --title ... --body ...`):

| Kind | Write one when | Put in the body |
|---|---|---|
| `false-positive` | A finding died at the gate | The assumption that made it look real, and the guard that saved the target |
| `miss` | Something you didn't find surfaced later | The lens or asymmetry that would have caught it |
| `revived` | A dead end turned out alive | The ladder rung that revived it |
| `technique` | A move unexpectedly paid | The move, and the target shape it worked on |

`sieve kb writeback` also records every frontier row closed `dead` as a `dead-end` lesson, ladder
attempts included — a killed hypothesis is data. `sieve kb prime` puts your recent lessons for this
engagement's packs at the bottom of `xray/precedents.md`; read them before the hunt starts. The
five-minute end-of-engagement post-mortem that feeds this is in `hypothesis-craft.md` §4.

## The Obsidian vault

The knowledge base is an Obsidian vault if you want it to be, and a folder of markdown if you don't.

```
sieve vault init          # scaffold ~/.sieve/kb (graph colours, vector-card notes, class/domain hubs), link every card
sieve vault export        # this engagement as a linked note graph in .sieve/vault/ (start at SV-<id>.md)
```

Every card ends in a `## Links` block — its vector card, class hub, domain hub, and the engagements
that used it — so Obsidian's graph clusters what has actually paid. `vault export` reshapes what the
audit already wrote: components, `INV-n` invariants, findings, dead ends (with their ladder rungs),
and `HYPOTHESIS` blocks become notes that link to each other, colour-coded by type. Agents don't need
to know about Obsidian: write findings and notes normally; `[[wikilinks]]` you add by hand survive.
Open the folder with *Open folder as vault* — nothing else is required.

## Using a precedent in the hunt

A card match, online or local, is always a **lead**: it raises priority and confidence in a
direction worth digging, and it earns a `source_ref:` citation in the finding it helps confirm. It
never substitutes for this engagement's own proof — `judging.md` Gate 6 still requires this
target's own evidence before anything ships.
