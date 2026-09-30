---
id: KB-W3-seed01
title: "Example - spot-price oracle manipulation via flash loan"
source: seed
source_ref: "kb/README.md"
domain: web3
class: oracle-manipulation
vector: W3-ORC-01
severity: critical
stack: solidity/lending
tell: 'getReserves\(\)|slot0\(\)'
status: seed
tags: [oracle, flash-loan, amm]
first_seen: "2026-09-29"
---

# Example - spot-price oracle manipulation via flash loan

This is a shipped example illustrating the card schema, not a vetted precedent for any specific
engagement. See `packs/web3/vectors/oracle-and-price.md` (`W3-ORC-01`) for the live vector card.

## Root cause
A lending or vault contract reads a DEX pool's instantaneous reserves ratio as its sole price
source for collateral valuation, with no time-weighting or external feed cross-check.

## Attack path
1. Borrow a large amount of the pool's quote asset via a flash loan.
2. Swap it into the pool to move the spot price sharply.
3. In the same transaction, trigger the valuation-dependent action (borrow against inflated
   collateral, or force an undercollateralized position to look healthy).
4. Reverse the swap and repay the flash loan, keeping the extracted value.

## Fix
Use a time-weighted average price over a window a single transaction cannot move meaningfully, or
a decentralized oracle network feed with a staleness check (`W3-ORC-02`).
