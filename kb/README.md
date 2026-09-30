# kb/: the shipped seed of the knowledge base

`kb/seed/cards/` ships a handful of illustrative cards in the same format `sieve kb use`/
`sieve kb writeback` produce, so the schema is unambiguous from day one. **Treat these as examples,
not vetted precedent** - they are marked `status: seed` and are never promoted to
`curated`/`confirmed` by any automated process.

Two tiers, both outside this repo. The **precedent tier** is the public record, filled by `sieve kb ingest` (DeFi exploits,
contest findings, disclosed HackerOne reports, CISA KEV, Exploit-DB, OSV with fix commits, ...; no API key) into the local
index `~/.sieve/index.db`. The **vault tier** is your own cards, in the `KB/` folder of the Sieve Obsidian vault
(`sieve vault path`): curated, confirmed and lesson cards with `[[wikilinks]]` to their vector card, class, domain and the
engagements that used them. `sieve vault init` scaffolds it.

```
kb/
  seed/cards/     shipped examples, `status: seed`, read-only reference
  README.md       this file
```

What `sieve kb writeback` writes is decided by the machine, not by a finding file's own `status:` line
(`references/validation.md`): a **confirmed** tier becomes a `confirmed` card, a **trace-verified** one a `curated` card, a
**rejected** candidate becomes a *false-positive lesson* (what looked real, and the guard or missing harm that showed it was
not), and every frontier row closed `dead` becomes a dead-end lesson. `sieve kb prime` reads those lessons back before the next
hunt in the same class. `sieve kb index` rebuilds the local card index from `kb/seed/cards/` plus your vault; ingested
precedents live in their own table and survive a reindex. Full workflow in `references/knowledge.md`.
