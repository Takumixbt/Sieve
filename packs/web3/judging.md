# Web3 — pack-specific gate additions

Read after `references/judging.md`. These apply on top of the universal gates and Do-Not-Report
list, never instead of them.

## Safe patterns — do not flag on sight, verify the reasoning first

- `unchecked{}` in Solidity ≥0.8 where the surrounding bounds genuinely make overflow impossible.
- An explicit narrowing cast in Solidity ≥0.8 (it reverts on overflow — confirm the compiler
  version before trusting this).
- A `MINIMUM_LIQUIDITY`-style burn on first deposit — this exists specifically to block the
  donation/inflation attack; verify it's actually present and sized correctly before claiming the
  attack works.
- `SafeERC20`'s `safeTransfer`/`safeTransferFrom` usage.
- `nonReentrant` on the function under test — only a genuine cross-contract reentrancy path (one
  that reaches a *different* function not covered by the same guard) clears Gate 1 here.
- A two-step admin-transfer pattern (propose then accept) — this already mitigates the single-step
  version of that finding.
- Protocol-favoring rounding that is consistent and doesn't compound or zero-round a real position.

## Do Not Report — web3-specific

- Centralization risk with no concrete unprivileged amplifier (Gate 3) — an owner *can* rug by
  design is not a finding; a mechanism that lets an unprivileged actor exploit that power is.
- Gas micro-optimizations, compiler/linter suggestions, missing NatSpec.
- "Reentrancy" on a function already protected by a working `nonReentrant` guard, with no
  cross-contract path around it.
- Implausible preconditions requiring the owner to act against their own stated incentives with no
  external pressure to do so — but fee-on-transfer, rebasing, and blacklisting token behaviors ARE
  plausible for any contract accepting arbitrary ERC-20/SPL tokens; do not wave these away as
  implausible.
