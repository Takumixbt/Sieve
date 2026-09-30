# Solana / Anchor static scan - the one real code pass for this chain

Every other chain in Sieve's web3 pack gets its "is this claim actually true"
answer from grep, not from an actor's word (the x-ray's entry-point gate does this
for Solidity, `xray.md`). Solana never had that.
This file is it - six grep-verifiable checks, run before any actor opens a
`.rs` file, so their hypotheses start from *measured* gaps instead of a fresh
read-and-guess. Grep output is not LLM-generated - it either matches or it
doesn't. That's the one property worth paying for without standing up a
pipeline.

**Every check produces LEADs, never FINDINGs** (`shared-rules.md` §1 - a grep
hit shows a *shape*, not a proven exploit; an actor still traces the call to
confirm it fires). Feed the lead list into the `access-control-agent` and
`invariant-agent` bundles as seed leads, exactly how x-ray's entry-point list
seeds solidity-auditor.

All commands are POSIX ERE (`-E`), no `-P`/PCRE, so they run identically on
GNU grep (Linux/WSL), BSD grep (macOS), and ripgrep - same portability rule as
x-ray's Solidity scan. Run against the program's `src/` (or wherever
`Cargo.toml` + `#[program]` live), excluding `target/`, `tests/`, `migrations/`.

---

## Check 1 - Unchecked account without a `/// CHECK:` comment

Anchor's own convention: any `AccountInfo<'info>` or `UncheckedAccount<'info>`
field that skips Anchor's type-level validation is required to carry a
`/// CHECK:` comment explaining *why* it's safe - missing / off-topic wording
is a real signal, not boilerplate.

```bash
# 1. Every unchecked-account field declaration
grep -rnE '(AccountInfo|UncheckedAccount)<.info>' [src-dir]/ --include='*.rs' \
  | grep -v '/tests/'
```

For every hit, look at the 1-3 lines immediately above it. No `/// CHECK` line
present → **LEAD**: `unchecked-account-no-safety-comment`. A comment that's
present but generic ("this is fine") rather than naming the actual validation
elsewhere is also worth a LEAD - the comment existing doesn't mean the
validation does.

**Coverage number to print** (mirrors the frontier's completeness rule in `methodology.md`):
`count(AccountInfo/UncheckedAccount fields)` vs `count(/// CHECK comments)` in
the same scope. A gap between the two is not proof of a bug, but it is the
single highest-signal number in this file - print it before the report ships.

## Check 2 - Privileged account missing `has_one` / `constraint`

For every `#[derive(Accounts)]` struct containing a `Signer<'info>`, every
*other* account in the struct whose name suggests privileged state (`config`,
`admin`, `owner`, `authority`, `vault`, `pool`, `treasury` - adapt to the
target's actual naming) should tie back to that signer via `has_one =` or an
explicit `constraint =`.

```bash
# 2a. Every Accounts struct and its full body (for manual cross-check)
grep -rnE '^#\[derive\(Accounts\)\]' [src-dir]/ --include='*.rs' -A 40
```

Read each struct block returned. For each privileged-looking account field,
confirm a `has_one` or `constraint` line references the signer field in the
*same* struct. No such line → **LEAD**: `privileged-account-unbound-to-signer`.
This is exactly the gap class that would have caught the pattern Veilo's own
`ConfigAdmin`/`UpdatePoolConfig` structs get right (`has_one = admin` on
`config`, tied to a `Signer<'info> admin`) - the check is: does *every*
struct that touches privileged state follow that same pattern, or do some
skip it.

## Check 3 - Under-scoped PDA seeds

```bash
# 3. Every seeds = [...] declaration with its bump line
grep -rnE 'seeds[[:space:]]*=[[:space:]]*\[' [src-dir]/ --include='*.rs' -A 3
```

For each hit:
- `bump` with no `= x.bump` (i.e. re-derived/searched each call rather than
  reading a stored canonical bump) on a `mut` account → **LEAD**:
  `pda-bump-not-canonical` (cheap DoS / unnecessary compute at minimum; worth
  an actor's trace).
- Seeds built only from constant byte strings with no per-user, per-mint, or
  per-market component, on an account that clearly should be scoped to one
  entity (holds a balance, a position, a note) → **LEAD**:
  `pda-seed-under-scoped` - two different users' state may collide on the same
  address, or the account is globally shared when it shouldn't be.

## Check 4 - CPI account confusion

```bash
# 4. Every invoke / invoke_signed call site
grep -rnE '\b(invoke|invoke_signed)\(' [src-dir]/ --include='*.rs' -B 15
```

For each call, check whether every account passed in the CPI's account list
was itself validated by the enclosing `#[derive(Accounts)]` struct (typed,
constrained, or explicitly checked) versus pulled raw from instruction data or
`remaining_accounts` with no prior validation in this function. The latter →
**LEAD**: `cpi-account-unvalidated`.

## Check 5 - `remaining_accounts` (Anchor's validation macro doesn't reach it)

```bash
# 5. Every remaining_accounts access
grep -rnE 'remaining_accounts' [src-dir]/ --include='*.rs' -B 5 -A 10
```

`remaining_accounts` is *always* coverage-debt by default - Anchor's
`#[derive(Accounts)]` macro validates nothing about accounts that arrive this
way; every property (owner, type, PDA correctness, uniqueness across the
list) is on the instruction handler to check manually. For each site, confirm
the handler manually validates owner + expected discriminator + no duplicate
entries before use. Any missing check → **LEAD**:
`remaining-accounts-unvalidated-<owner|discriminator|duplicate>`. Print the
raw count of sites (Veilo's own source has ~90 - treat any target with a
nonzero count here as needing an actor's full attention on this file, not a
skim).

## Check 6 - Value-moving instruction with no signer in scope

```bash
# 6a. Instructions whose Accounts struct has zero Signer<'info> fields
grep -rlZ 'Signer<.info>' [src-dir]/ --include='*.rs' 2>/dev/null | tr '\0' '\n' > /tmp/has-signer.txt
grep -rlE '^#\[derive\(Accounts\)\]' [src-dir]/ --include='*.rs' > /tmp/has-accounts-struct.txt
```

(Run structurally per-struct, not per-file, when the target has multiple
`Accounts` structs per file - Path A/B distinction from `x-ray`'s Step 2
applies here too.) For each `#[derive(Accounts)]` struct with **zero**
`Signer<'info>` fields, check whether the paired instruction handler moves
value (transfer, mint, burn, close-and-reclaim-lamports, withdraw). If yes →
**LEAD**: `value-move-no-signer` - highest-priority lead this file produces,
hand it straight to the `access-control-agent` (web3 pack).

---

## Wiring into the campaign

The `narrative-web3` node runs after `sieve scan` has produced the mechanical x-ray. When the target is Rust/Anchor,
run all six checks above during that node, write the lead list into `.sieve/xray/x-ray.md` under a
`## Solana static scan` heading, and print the Check 1 and Check 5 coverage numbers inline. Each lead becomes a
frontier row (`sieve frontier add tool-lead ... --pack web3`), so the drain node must close it with a receipt.
Hunters then start from measured gaps, not a cold read.

## What this is not

This does not replace an actor tracing a lead to a real exploit - a grep hit
is a shape, and Check 2/3/6 in particular need a human-grade read of the
surrounding logic to separate "genuinely missing" from "checked a different,
equally valid way" (e.g. an admin gate enforced one call earlier via a shared
`require_admin()` helper rather than inline `has_one`). Treat every hit as a
LEAD and gate it exactly like any other (`judging.md`) - this file only makes
the *first* pass cheaper and unfakeable, it doesn't skip verification.
