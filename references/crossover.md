# Crossover — the seam where the packs meet

This is where the highest-value bugs live, and the one place a single-pack tool structurally
cannot look. After web3, web, and binary hunts have each run, the crossover pass reads every
pack's findings and leads together and asks one question: **what does one surface give an attacker
power over on another?**

Runs only when **two or more packs produced output** — one pack alone has no seam to hunt.

## The seams to check, every time

- **A web admin panel that holds a web3 privileged role** — a `setOracle`/`pause`/`upgrade`
  capability gated only by a web session, not an on-chain multisig. A web finding that reaches this
  panel (an IDOR, a broken auth check, a CSRF) inherits the on-chain role's full severity.
- **An API endpoint that triggers a privileged on-chain action** — an off-chain signer, a relayer,
  a bridge operator's service account. A web-side bug here is a bridge-drain, not a data leak.
- **A leaked web2 secret that is also a signing/validator key** — `.env` exposure, a misconfigured
  storage bucket, a debug endpoint — checked against every key the web3 side treats as trusted.
- **The SIWE / EIP-712 / JWT boundary** between a web session and an on-chain identity — does the
  signed message actually bind to what the web session claims it does?
- **A price/data API a contract trusts as an oracle** — web-side manipulation of a feed the
  contract reads becomes on-chain price manipulation.
- **A native binary a web endpoint or a contract trusts** — a CGI/native backend, an off-chain
  prover or validator client. Memory-corruption RCE here undermines whatever on-chain or web
  guarantee depends on that binary's correctness.
- **A mobile app's local trust decisions** — client-side validation the server (or the contract)
  assumes happened; an API key or signing capability embedded in the APK/IPA that a native-binary
  agent extracted.

## Method

Load every pack's raw findings/leads plus the x-ray verdicts (`xray.md`) from each pack that ran.
For each seam above that's structurally present in this target, trace it explicitly — don't wait
for two findings to coincidentally reference each other; actively ask "does this component's output
feed that component's trust decision?" for every pair of surfaces.

A crossover finding's `proof:` must show **both halves**: the web/binary-side mechanism and the
web3-side (or vice versa) consequence, each with its own citation. Gate it exactly like any other
finding (`judging.md`) — a crossover claim is not exempt from Gate 1's refutation pass just because
it's more interesting.

## Chaining low findings across packs

`methodology.md` Part 4 covers chaining within one pack; the same idea applies across packs and is
usually where it pays most. A web3 finding that looked capped ("only an admin can trigger this")
might chain with a web finding that shows exactly how an attacker reaches the admin's session.
Check `judging.md`'s lead-promotion rule 4 (crossover chain) before writing off either half as
insufficient alone.
