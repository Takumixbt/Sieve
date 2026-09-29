# Report formatting — the finding file contract, and what `sieve report` does with it

## The one rule

**A report must never claim to show more than the engagement actually found.** `sieve report`
(`sieve/report.py`) may print less — a finding file that failed to parse is named in a warning
block, never silently dropped — and it may never print as if it printed more. This rule is why
`sieve report`'s output always states exactly how many finding files it could not read, right next
to the summary table.

## The finding file — written by the agent, not generated

Every finding or lead is its own file: `.sieve/findings/<id>.md`, YAML frontmatter plus a markdown
body. `sieve report` only reads, dedupes, sorts, and counts these — it never computes a severity,
confidence, or verdict. If you find yourself wanting the tooling to decide a verdict, that decision
belongs in `judging.md`, done by an agent, not in this file's script.

```markdown
---
id: F-001
kind: FINDING                    # FINDING | LEAD | HYPOTHESIS — shared-rules.md
pack: web3                       # web3 | web | binary
class: oracle-manipulation       # the bug-class label — reuse an existing one for the same shape
vector: W3-ORC-01                # the packs/<pack>/vectors/*.md card id, if one applies
component: Vault.rebalance
group_key: Vault|rebalance|oracle-manipulation   # dedup key across agents and passes
severity: high                   # critical | high | medium | low | informational
status: confirmed                # confirmed | trace-verified | demoted | rejected
confidence: 90                   # judging.md's arithmetic — start at 100, deduct per rule
gate: "1,2,3,4,5,6 clear"        # which gates it passed, for the record
cwe: CWE-841                     # web / binary; web3 uses `vector` instead
stack: solidity/lending
tell: 'getReserves\('            # a grep-able signature for the learning loop (knowledge.md's write-back section)
source_ref: "solodit:abc123"     # a KB precedent that helped, if any (knowledge.md)
---

## Root cause
One or two sentences — the code-level defect.

## Attack path
caller -> function -> state change -> impact, with concrete values.

## Proof
The exact evidence: a fork-test name, a request/response pair, a crash trace. This is what
`sieve prove record` files a receipt for — the body here is the human-readable version.

## Remediation
The smallest change that eliminates the defect.
```

A **LEAD** carries `code_smells:` and a description of what remains unverified instead of a full
write-up; no confidence score, no Fix section.

## What `sieve report` does, mechanically

1. Reads every `findings/*.md`. A file missing required frontmatter is reported broken, not
   dropped from the count silently.
2. **Dedup by `group_key`** — one winner per key: strongest `kind` (FINDING > LEAD > HYPOTHESIS),
   then highest `confidence`.
3. **Sort** — by severity, then confidence, descending.
4. **The size trigger** — above 20 findings, the terminal-facing text shows the top 3 plus the full
   count and the path to the complete file; `report/report.md` itself always holds everything.
   Leads are never counted toward this trigger.
5. **Coverage section** — frontier stats (`sieve frontier stats`) and any recorded phase waivers
   (`.sieve/waivers.tsv`), so the report states what was skipped and why in the same document as
   what was found.

## Architecture diagram

`xray/architecture.json` feeds `scripts/generate_svg.py` (vendored, MIT-licensed — attribution in
its own file header and in `CREDITS.md`), rendered by `sieve xray map`.

```json
{"title": "...", "nodes": [{"id": "x", "label": "Name", "subtitle": "role", "type": "actor|protocol|external", "row": 0}],
 "edges": [{"from": "x", "to": "y", "label": "..."}], "groups": [{"label": "...", "nodes": ["id1", "id2"]}]}
```

Node/edge budget scales with in-scope component count (≤10 components → ≤12 nodes/14 edges; 36+ →
≤24/26) — prioritize completeness (every component that holds funds, gates access, or sits on a
critical path is visible) over compression; composite same-trust-level satellite contracts into one
node before dropping any to fit budget, and never composite across trust levels.

## Platform submission format

When the operator names a target platform, re-emit each CONFIRMED finding in that platform's
required shape (title/severity/impact/steps-to-reproduce for HackerOne/Bugcrowd/Intigriti; the
Immunefi Markdown template for web3 bounties) — the finding file above already carries every field
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
