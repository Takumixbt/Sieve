Eight lenses each derived invariants independently (their artifacts are inlined below). **Fan them in** into one ranked list.

## Merge rules

1. **Merge duplicates.** Two statements that are the same property in different words become one invariant whose
   `sources` lists every lens that found it. Agreement across independent lenses is the strongest signal on this page -
   keep the union of `violators` and the sharpest `test`.
2. **Drop the vacuous.** An invariant with no way to fail, or one that merely restates a `require` in the code, goes to
   `dropped` with the reason. Keep the reasons short and specific.
3. **Keep the odd ones.** An invariant only one lens found is not weaker for it - it may be the one nobody else could see.
   Do not drop a single-source invariant for being single-source.
4. **Rank by damage if broken** (`rank` 1 = worst): funds or data lost, privilege gained, chain or service halted.
   Break ties toward `on_chain: false` (unenforced by code) and toward invariants with many violators.
5. **Renumber** to `INV-1…INV-n`. These ids are what the frontier rows, the triage panel and the report's Coverage
   section refer to.

## Also

- If two lenses *contradict* (one says a value never decreases, another shows a path that decreases it), that
  contradiction is itself a lead: keep both statements and note it in the higher-ranked one's `test`.
- Do not invent invariants no lens produced; you are merging, not generating. (The strategy node generates.)
