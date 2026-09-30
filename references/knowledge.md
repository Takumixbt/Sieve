# Knowledge: grounding hypotheses in what has actually paid

The highest-ROI pre-hunt activity is reading what other hunters already found and got paid for. Sieve keeps a
two-tier knowledge base. The **vault tier** holds cards an engagement or you wrote (curated, confirmed, lessons): few,
high signal, an Obsidian graph. The **precedent tier** holds the public record (tens of thousands of disclosed reports,
real exploits, advisories with their fix commits), searchable but never written into the vault as files, so the graph
stays readable. Every source needs no account and no API key.

## The "what changed" method (the highest-ROI pattern, every pack)

```
1. Find a disclosed report / precedent for the SAME stack as this target
   (web: same framework: Django REST, Express, Rails.
    web3: same protocol shape: lending, AMM, bridge, staking.
    binary: same class of target: a parser, a network daemon, a setuid tool.)
2. Find the fix commit / patched version and read the diff.
3. Identify the anti-pattern in the vulnerable code.
4. Grep THIS target's source for that same anti-pattern.
5. Test every match.
```

It works because different teams reproduce the same mistakes in the same frameworks and the same protocol shapes. You
are transplanting a *pattern*, not copying a PoC. Precedent rows from OSV and OSS-Fuzz carry their **fix commits**
(`fix:` in `sieve kb search`), which is step 2 done for you.

## `sieve kb`: the commands

```
sieve kb sources                                # each public source, its licence, row count and last ingest
sieve kb ingest [--source a,b|all] [--limit N] [--osv-ecosystem X,Y] [--refresh]   # fill the precedent tier
sieve kb search "<query>" [--domain web3|web|binary] [--online]   # both tiers (+ Solodit if you have a key)
sieve kb osv --package <name> --ecosystem npm --version <v>       # known CVEs for a dependency
sieve kb use <ref> --finding F-001 --class <bug-class>            # a precedent that helped -> curated card
sieve kb add --title ... --domain ... --class ... --url ...       # a report you found by hand
sieve kb lesson --kind ... --title ... --body ...                 # something an engagement taught you
sieve kb writeback                                                # confirmed findings, false positives, dead ends -> cards
sieve kb prime                                                    # writes xray/precedents.md for this engagement
```

Run `sieve kb ingest` once per machine (about a minute) and again when you want fresher data; a source ingested within
seven days is skipped unless you pass `--refresh`, and a failed refresh never wipes what was there.

## Sources

**Ingested, keyless (`sieve kb sources`)**

| Source | Domain | What it holds |
|---|---|---|
| `defihacklabs` | web3 | 700+ real DeFi exploits with date, loss, root-cause class, PoC and write-up links (Apache-2.0) |
| `web3-vulns` | web3 | Smart-contract vulnerability class references with root cause, exploit and mitigation (MIT) |
| `c4` | web3 | Code4rena High and Medium findings, newest contests first (`--limit N` contests, default 40) |
| `hackerone` | web, binary | About 15k disclosed HackerOne reports: program, weakness, bounty |
| `payloads` | web | PayloadsAllTheThings, one entry per attack class (MIT) |
| `cisa-kev` | web, binary | Vulnerabilities exploited in the wild |
| `exploitdb` | web, binary | Exploit-DB titles, platforms and CVE codes |
| `osv` | binary, web | Advisories with fix commits. Default ecosystem is OSS-Fuzz (native C/C++ bugs); add `--osv-ecosystem crates.io,Go,npm,PyPI,Maven,...` |

**Optional online**: Solodit (`sieve kb search --online`) if you happen to have a `CYFRIN_API_KEY`. It is skipped
silently when unset; nothing depends on it.

**Also worth reading by hand when the summary is not enough**: the actual exploit PoC in DeFiHackLabs, `rekt.news`,
PortSwigger Research for genuinely new web attack classes, and the target's own fix commits.

`sieve kb search` and `sieve kb prime` read both tiers, ranking your own confirmed and curated cards above public
precedents. All online lookups go through a rate-limited broker shared by every parallel agent (20 requests per 60 seconds
for Solodit), so twelve agents searching at once cannot blow a limit.

## Prior-art / duplicate sweep: run before hunting, every engagement

```
1. IN-REPO    /audits, /security, SECURITY.md, any prior audit PDF in the target's own repo
2. CONTEST    a prior Code4rena/Sherlock/Cantina contest report for this exact protocol
3. PLATFORM   the program's own disclosed reports, filtered by class
4. PUBLIC     search writeups and aggregators for the target's name
```

This does two things: it kills duplicates before you write them up (the single most common rejection reason on every
platform), and it shows you where nobody has looked: the component a prior audit skipped, the class a contest
under-covered, the version bumped after the last review. Record the swept sources and the known-issue list in
`.sieve/plan.md` so the gate rejects a re-find on sight.

## Write-back: how an engagement makes the next one sharper

`sieve kb use <ref> --finding <id>` promotes a precedent you actually *used* (not every hit, only the one that moved a
hypothesis forward) to a **curated** card. `sieve kb writeback`, run by the campaign at the end, turns every finding the
machine computed as **confirmed** at or above `kb.writeback.min_confidence` (75 by default) into a **confirmed** card:
root cause, attack path, fix, tagged with the `tell:` grep signature that would catch the same shape again. A
trace-verified finding becomes a curated card, a rejected candidate a *false-positive lesson*, every frontier row closed
`dead` a dead-end lesson with its ladder rungs. Cards are real markdown with YAML frontmatter you can read, edit or delete
by hand; the index is a cache rebuilt from them, never the source of truth.

**Learn only from proof.** A card's `status` never downgrades on merge, and a card is never created from a suspect or a
hypothesis: only from something that cleared `judging.md`, or a precedent you consciously chose to trust. Secrets are
stripped automatically before anything is written (`kb_store.sanitize`); never rely on this as the only check, and do not
paste a live credential into a card body in the first place.

## Lessons: learning from your own history

Precedent is other people's history. Your own is more useful and almost never recorded. Four kinds of lesson, each a
card (`sieve kb lesson --kind ... --title ... --body ...`):

| Kind | Write one when | Put in the body |
|---|---|---|
| `false-positive` | A finding died at the gate | The assumption that made it look real, and the guard that saved the target |
| `miss` | Something you didn't find surfaced later | The lens or asymmetry that would have caught it |
| `revived` | A dead end turned out alive | The ladder rung that revived it |
| `technique` | A move unexpectedly paid | The move, and the target shape it worked on |

`sieve kb prime` puts your recent lessons for this engagement's packs at the bottom of `xray/precedents.md`; read them
before the hunt starts. The five-minute end-of-engagement post-mortem that feeds this is in `hypothesis-craft.md` §4.

## The Obsidian vault

One vault holds everything Sieve writes, separate from any other vault you keep. It resolves as `$SIEVE_VAULT`, then
`vault.root` in `sieve.yaml`, then `Sieve Vault` in Documents (OneDrive's Documents when that is where Documents lives).

```
Sieve Vault/
  Sieve.md                        the root note; every engagement is listed on it
  KB/                             cards (web3/ web/ binary/), vector notes, class and domain hubs, ladder-rung hubs
  Engagements/<target>-<id>/
    <engagement id>.md            the engagement hub: coverage, components, invariants, findings, dead ends, classes
    <target>-<id>-Report.md       the assembled report
    invariants/  findings/  components/  deadends/  hypotheses/
```

```
sieve vault init          # create the vault: root note, graph colours, KB scaffold, vector notes, every card linked
sieve vault export        # this engagement into Engagements/<target>-<id>/ (re-running is idempotent)
sieve vault export --local   # a confidential engagement: .sieve/vault/ inside the target, nothing synced
sieve vault path
```

Every note name carries the engagement's namespace (`<target>-<id>-F-001`), so any number of engagements share one
vault without `F-001` colliding; links display the short name. The graph is the audit's mind-map:

- each numbered invariant is a note with a **coverage** state (`broken` when a finding cites it, `clean`, `dead-end`, or
  **`unprobed`**). An unprobed invariant is a promise nobody examined; filter the graph by tag `#unprobed` to see the
  audit's gaps, and the engagement hub lists them first
- findings link up to the invariants they break, their class hub, their component and their vector card
- dead ends keep their ladder attempts and link to the rung hubs, so what was tried is never re-walked
- class hubs live in `KB/_hubs/` and tie findings across engagements to the same bug class, so the next audit on a
  similar stack opens with the graph already pointing at what to check

The vault is derived from files the audit already wrote; the export decides nothing. Confidential engagement? Use
`--local` or point `SIEVE_VAULT` at a non-synced folder for that run.

## Using a precedent in the hunt

A card match, online or local, is always a **lead**: it raises priority and confidence in a direction worth digging, and
it earns a `source_ref:` citation in the finding it helps confirm. It never substitutes for this engagement's own proof;
`judging.md` Gate 6 still requires this target's own evidence before anything ships.
