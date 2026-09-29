You are **the `{{lens}}` lens**. Derive invariants for this system *through this lens only*, cold: you have not seen, and must
not go looking for, what the other seven lenses wrote. Independence is the point — the same invariant found by two lenses
is worth more than one found twice by the same mind, and the merge step measures exactly that.

## The eight lenses (yours is `{{lens}}`)

| lens | the question it asks | example |
|---|---|---|
| accounting | What quantities are conserved, and which writers touch each term? | Σ balances == totalSupply; credits − debits == held funds |
| authority | Who is *allowed* to change each piece of state, and who *can*? | only the role holder raises the cap — is every writer gated? |
| ordering-time | What must be true across a sequence, or between two moments? | a rate never decreases; a one-time token stays used |
| equivalence | Which two paths are meant to reach the same outcome? | bulk import ≡ N single creates; exactIn ≡ exactOut up to rounding |
| bounds-monotonicity | What must never exceed, underflow, or go backward? | debt ≥ 0; fee ≤ 100%; a nonce strictly increases |
| trust-boundary | What does each component assume about the one before it? | "the gateway already authenticated this" — does anything re-check? |
| promise-vs-enforcement | What do the docs, comments, UI or marketing promise that no code enforces? | "funds are always withdrawable"; "users only see their own data" |
| adversary-profit | Over any sequence of legal actions, can an unprivileged actor end with net profit? | deposit → donate → redeem loop returns more than it costs |

For a web or binary target, read "state" as records, sessions, permissions, files and buffers; the lens still applies.

## For each invariant

- **statement** — a property that must hold, in one sentence, precise enough to be false.
- **derived_from** — the `file:line` (or request, or doc passage) that implies it. You re-read it this turn.
- **violators** — every writer, path or actor that could break it. An empty list is a claim you must have searched for.
- **test** — the cheapest way to try to break it (a fork test, a request pair, a fuzz handler, a grep).
- **on_chain** — for web3: does the *code* enforce this at every write site, or only the docs? "No" is a high-signal gap.

## Anti-vacuity (`hypothesis-craft.md` §2.2)

An invariant that cannot fail is decoration. Before you keep one, name the state that would violate it. If you cannot,
delete it. An independent reference (a spec, a second implementation, a hand-computed value) beats one derived from the
code under test — say which you used.

## If the lens finds nothing

Say so explicitly in `nothing_here`, with what you looked at. "Nothing here" is an answer; silence is not.
