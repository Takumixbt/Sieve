# Report formatting - the finding file contract, and what `sieve report` does with it

## The one rule

**A report must never claim to show more than the engagement actually found.** `sieve report`
(`sieve/report.py`) may print less - a finding file that failed to parse is named in a warning
block, never silently dropped - and it may never print as if it printed more. This rule is why
`sieve report`'s output always states exactly how many finding files it could not read, right next
to the summary table.

## The finding file - written by `sieve merge`, judged by `sieve judge`

Every finding or lead is its own file: `.sieve/findings/F-NNN.md`, YAML frontmatter plus a markdown body.
Agents write raw FINDING / LEAD / HYPOTHESIS *blocks* (`shared-rules.md`); `sieve merge` turns them into these files
(deduped by `group_key`, ids stable across re-merges); `sieve judge` and `sieve prove` add the verdict and the receipts.
`sieve report` only reads, sorts, counts and prints - and for **what is allowed to be called confirmed it does not read
the file's `status:` line at all**: it recomputes the tier from the sealed receipts (`validation.md`). If you find
yourself wanting the tooling to decide a *severity* or a *root cause*, that is `judging.md`, done by a verifier.

```markdown
---
id: F-001
kind: FINDING                    # FINDING | LEAD  (HYPOTHESIS blocks live in findings/hypotheses.json, not here)
pack: web3                       # web3 | web | binary
class: oracle-manipulation       # the bug-class label - reuse an existing one for the same shape
vector: W3-ORC-01                # the packs/<pack>/vectors/*.md card id, if one applies
component: Vault.rebalance
group_key: Vault|rebalance|oracle-manipulation   # dedup key across agents and passes
title: oracle-manipulation - Vault.rebalance
severity: high                   # the verifier's, once judged (the discoverer's before)
status: candidate                # candidate | lead | cleared | confirmed | trace-verified | demoted | rejected
                                 #   informational only - the REPORT recomputes the tier from receipts
confidence: 90                   # judging.md's arithmetic - set by `sieve judge`, threshold 75
found_by: [web3/access-control-agent, web3/math-precision-agent]   # discoverers (a verifier may not be one)
passes: [1, 2]
complexity: straightforward      # straightforward | complex (complex needs two verifiers per stage)
validation: confirmed            # last computed tier (informational; `sieve verify` refreshes it)
demoted_by: [cite-fail]          # why the merge kept a FINDING block as a LEAD, if it did
claim_hash: 4f9a1c0d22b7e610     # hash of the claim text - a later edit marks receipts stale
cwe: CWE-841                     # web / binary; web3 uses `vector` instead
tell: 'getReserves\('            # a grep-able signature for the learning loop (knowledge.md's write-back section)
source_ref: "solodit:abc123"     # a KB precedent that helped, if any (knowledge.md)
---

## Root cause
One or two sentences - the code-level defect.

## Attack path
caller -> function -> state change -> impact, with concrete values.

## Proof
The agent's evidence: a fork-test name, a request/response pair, a crash trace, with `file:line` citations. The
machine-run proof is separate: `sieve prove run` writes sealed receipts to `.sieve/proofs/F-001--exec-*.json`.

## Remediation
The smallest change that eliminates the defect.

## Machine checks (`sieve merge`)      # present only when the merge demoted or annotated the block
```

A **LEAD** carries `code_smells:` and a description of what remains unverified instead of a full
write-up; no confidence score, no Fix section. A LEAD becomes a candidate only when a later pass raises the same
`group_key` again as a proper FINDING.

## What `sieve report` does, mechanically

1. Reads every `findings/F-*.md`. A file missing required frontmatter is reported broken, not
   dropped from the count silently.
2. **Computes each finding's tier** (`validate.assess`): `confirmed`, `trace-verified`, `unvalidated`, `stale`, `tampered`,
   `rejected` or `lead` - from the verdict in `judged.json` (sealed), the citation receipt, the exec receipts and the ledger.
   A finding whose file says `status: confirmed` but whose tier is lower is printed at the lower tier with a warning.
3. **Dedup by `group_key`** - one winner per key: strongest `kind` (FINDING > LEAD), then highest `confidence`.
4. **Sort** - by the verifier's severity, then confidence, descending.
5. **Sections**: *Findings* (confirmed only, each with a Validation line: oracle, repeats, control kind, measured values,
   verifiers), *Trace-verified findings*, *Unvalidated candidates - not confirmed* (with the reason), *Leads*, *Coverage*.
6. **The size trigger** - above 20 confirmed findings, the terminal-facing text shows the top 3 plus the full
   count and the path to the complete file; `report/report.md` itself always holds everything.
7. **Coverage section** - frontier stats, validation stats (receipts, ledger INTACT/TAMPERED), and every recorded waiver
   (`.sieve/waivers.tsv`: phases entered early, agents lost or below contract, proofs accepted as trace-only, campaign nodes
   skipped) - so the report states what was skipped and why in the same document as what was found.
8. **A tamper banner** at the top if the proof ledger fails its chain/MAC/hash check.

## Architecture diagram

`xray/architecture.json` feeds `scripts/generate_svg.py` (vendored, MIT-licensed - attribution in
its own file header and in `CREDITS.md`), rendered by `sieve xray map`.

```json
{"title": "...", "nodes": [{"id": "x", "label": "Name", "subtitle": "role", "type": "actor|protocol|external", "row": 0}],
 "edges": [{"from": "x", "to": "y", "label": "..."}], "groups": [{"label": "...", "nodes": ["id1", "id2"]}]}
```

Node/edge budget scales with in-scope component count (≤10 components → ≤12 nodes/14 edges; 36+ →
≤24/26) - prioritize completeness (every component that holds funds, gates access, or sits on a
critical path is visible) over compression; composite same-trust-level satellite contracts into one
node before dropping any to fit budget, and never composite across trust levels.

## Platform submission format

When the operator names a target platform, re-emit each CONFIRMED finding in that platform's
required shape (title/severity/impact/steps-to-reproduce for HackerOne/Bugcrowd/Intigriti; the
Immunefi Markdown template for web3 bounties) - the finding file above already carries every field
those templates need; this is a re-formatting pass, not new analysis. Never submit a finding the
prior-art sweep (`knowledge.md`) already found reported.

## The Notion / in-house format

For an internal audit deliverable rather than a bounty submission: the same finding files, grouped
by severity, with the x-ray narrative (`xray.md`) and the architecture diagram as the opening
sections, and the Coverage section always last.

> ⚠️ Every generated report carries this line: *"This assessment was produced with AI assistance.
> AI analysis cannot verify the complete absence of vulnerabilities, and no guarantee of security
> is given. A human security review, an independent audit, and ongoing monitoring remain
> recommended."*
