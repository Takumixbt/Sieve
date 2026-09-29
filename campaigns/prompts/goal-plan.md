Turn the threat model into a **goal plan**: ranked, checkable goals for the hunt, and an explicit list of what will not be
hunted. This is the bridge from "what could go wrong" to "what will we actually try, in what order".

## For every attack goal in the threat model (and any you add)

- Write a **goal** — a statement that can be answered *yes, here is the trace* or *no, here is the guard that stops it*.
  "Prove or refute that any caller can move funds out of the vault" is a goal; "look at access control" is not.
- Give it a **priority 1-5** (5 = read first): (damage if true) x (likelihood it is unguarded) x (how little the roster
  would notice). A goal that only a cross-component chain reaches is not low priority for that reason — it is exactly
  where nobody looks.
- List the **components** it touches (`file:function`, endpoint, boundary) so the frontier and the roster can find it.
- Write **first checks**: the cheapest read or query that would confirm or kill it. The first check is what an agent does
  in its first ten minutes.
- Record `from_goal` (the threat-model goal id, `G-n`).

## And write what you will NOT spend time on

`excluded`: classes the scope card rules out, gas micro-optimisation, best-practice deviations with no demonstrated exploit,
admin-privilege-by-design with no unprivileged amplifier. Each with the reason. An exclusion with no reason is a hole in the
plan, not a decision.

## Quality bar

- At least five goals; at least one that crosses two components; at least one that starts from a *promise* the docs make
  rather than from a line of code.
- No goal restates another in different words.
