# kb/ — the shipped seed of the knowledge base

`kb/seed/cards/` ships a handful of illustrative cards in the same format `sieve kb use`/
`sieve kb writeback` produce, so the schema is unambiguous from day one. **Treat these as examples,
not vetted precedent** — they are marked `status: seed` and are never promoted to
`curated`/`confirmed` by any automated process.

The real, growing store lives outside this repo, at `~/.sieve/kb/` (`kb.vault` in `sieve.yaml`) —
per-user, not per-clone, so it accumulates across every engagement and isn't reset by updating the
skill. It is an **Obsidian vault**: `sieve vault init` scaffolds it (graph colours, one note per
vector card, class/domain hubs) and every card carries `[[wikilinks]]` to its vector card, class,
domain, and the engagements that used it. Open the folder in Obsidian for the graph; nothing
requires it.

```
kb/
  seed/cards/     shipped examples — read-only reference, `status: seed`
  README.md       this file
```

What `sieve kb writeback` writes is decided by the machine, not by a finding file's own `status:` line
(`references/validation.md`): a **confirmed** tier becomes a `confirmed` card, a **trace-verified** one a
`curated` card, a **rejected** candidate becomes a *false-positive lesson* (what looked real, and the guard or
missing harm that showed it wasn't), and every frontier row closed `dead` becomes a dead-end lesson. `sieve kb
prime` reads those lessons back before the next hunt in the same class.

`sieve kb index` rebuilds the local search index from `kb/seed/cards/` plus your own vault; nothing
here is the source of truth for search results once your own vault has real cards in it. Full
workflow — precedent, lessons, the vault — in `references/knowledge.md`.
