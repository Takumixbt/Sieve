The hunt loops and the roaming pass are finished, and `sieve absorb` closed every row an agent covered *with a receipt*.
**Every remaining frontier row must now be closed the same way** - this node is complete only when `sieve frontier list
--status open` is empty (the engine checks).

## How a row leaves the queue (nothing else counts)

```
sieve frontier attempt <row> --rung <rung> --note "what exactly you tried"   # log real work; repeat
sieve frontier done <row> --finding <F-id>              # it produced a finding/lead (see .sieve/findings/ledger.md)
sieve frontier done <row> --clean "the guard that makes it hold, file:line"   # needs >=2 attempts INCLUDING `inversion`
sieve frontier dead <row> --try layer:"..." --try sibling:"..." --try precedent:"..."   # needs >=3 attempts on >=3 rungs
sieve frontier block <row> --reason scope|credentials|irreversible|tooling --note "exactly what is missing"
```

The rungs are `sieve ladder`: input, layer, precondition, inversion, precedent, sibling, transplant, construct, fresh-eyes -
each a different *kind* of move, so three attempts on three rungs are three ideas, not three retries.

## Work the queue

- `sieve frontier next -n 20` gives the highest-priority open rows. Take them in that order; do not cherry-pick the easy ones.
- For each row: read the code or replay the request, form a hypothesis (assumption → break → observable → cheapest test),
  try it. If it produces a bug, write it up as a FINDING/LEAD block in `.sieve/raw/drain.md` with a real `proof:` and
  `file:line` citations, and close the row with `--finding` once `sieve merge` has given it an id.
- A "clean" claim is a claim you tried to falsify: the `inversion` attempt asks *what would have to be true for this to be
  exploitable, and can I make it true?* A path that "looks fine" and one that was inverted and held are different claims.
- A row that resists is not a reason to stop. Climb another rung. The only honest early stop is `sieve frontier block` with a
  whitelisted reason and a note that names exactly what is missing.

## Then

Write a short `.sieve/campaign/artifacts/drain.md`: how many rows you closed each way, which resisted longest and why, and
anything you would want the triage panel to look at twice. Finish with `sieve campaign submit drain`.
