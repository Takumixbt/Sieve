# kb/ — the shipped seed of the knowledge base

`kb/seed/cards/` ships a handful of illustrative cards in the same format `sieve kb use`/
`sieve kb writeback` produce, so the schema is unambiguous from day one instead of starting from an
empty folder with no example to follow. **Treat these as examples, not as vetted precedent** — they
are marked `status: seed` and are never promoted to `curated`/`confirmed` by any automated process.

The real, growing store lives outside this repo, at `~/.sieve/kb/` (`kb.vault` in `sieve.yaml`) —
per-user, not per-clone, so it accumulates across every engagement you run and isn't reset by
updating the skill.

```
kb/
  seed/cards/     shipped examples — read-only reference, `status: seed`
  README.md       this file
```

`sieve kb index` rebuilds the local search index from `kb/seed/cards/` plus your own vault; nothing
here is the source of truth for search results once your own vault has real cards in it.
