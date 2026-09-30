# Oracle & price manipulation

### W3-ORC-01 · Spot-price read used as an oracle
- signal: `getReserves()`, `slot0()`, or any single-block DEX price read feeding a valuation, collateral check, or liquidation
- attack: borrow flash-loan liquidity, swap to move the pool's spot price, trigger the valuation in the same transaction, reverse the swap
- chain: often the same root cause as a single-block oracle read inside a periphery wrapper (see agents/periphery-agent.md) - check both
- proof: fork test - before/after price shown moved, and the resulting profit/undercollateralized position computed
- fp: a genuine TWAP (30+ min window) or a Chainlink feed with a staleness check is not this vector - confirm which one is actually used before flagging
- sev: critical when it gates borrowing/liquidation/minting; high when it gates a smaller value flow
- cwe: n/a
- kb: oracle manipulation flash loan spot price DEX

### W3-ORC-02 · Stale oracle with no staleness check
- signal: `latestRoundData()` (or equivalent) called with the `updatedAt`/round-completeness return value ignored
- attack: the feed stops updating (chain congestion, provider outage, deprecated feed); the protocol keeps using the last, now-wrong price
- proof: trace showing no comparison of `updatedAt` (or the chain's equivalent) against `block.timestamp` with a maximum-age bound
- fp: some feeds intentionally have no explicit heartbeat in code because the underlying oracle network guarantees one contractually - verify which guarantee actually applies to this specific feed before flagging
- sev: high
- cwe: n/a
- kb: stale oracle price feed staleness check chainlink

## Reentrancy

### W3-REE-01 · Cross-function/cross-contract reentrancy around a `nonReentrant` guard
- signal: a guarded function calls into an external contract/token before finishing its own state updates, and a *different*, unguarded function shares the same state
- attack: reenter through the sibling function during the external call, before the first function's state update completes
- proof: fork test demonstrating the reentrant call succeeding and extracting value or corrupting state
- fp: `nonReentrant` on the function under test with no reachable sibling path is NOT this vector - confirm the actual cross-function reach before flagging (`packs/web3/judging.md`)
- sev: critical
- cwe: n/a
- kb: reentrancy cross-function cross-contract nonReentrant bypass

## Donation / share inflation

### W3-INF-01 · First-depositor share-price inflation
- signal: `shares = amount * totalShares / totalAssets` with no minimum-liquidity burn and `totalShares` starting at zero
- attack: deposit 1 wei as the first depositor (1 share), then donate a large amount directly to the pool (not via `deposit`) to inflate `totalAssets` per share; the next depositor's shares round to zero and their deposit is stolen
- tell: `totalShares == 0` reachable with no forced minimum-liquidity mint
- proof: fork test showing a victim's deposit resulting in zero minted shares while the attacker's prior position captures the value
- fp: a `MINIMUM_LIQUIDITY`-style permanent burn on first deposit, sized large enough relative to the token's decimals, blocks this - confirm it's actually present and adequately sized
- sev: high
- cwe: n/a
- kb: share inflation donation attack first depositor ERC4626

## Signature / replay

### W3-SIG-01 · Missing nonce or chain-id in a signed message
- signal: `ecrecover`/signature verification with no nonce tracked per-signer, or no `chainId`/domain separator bound into the signed hash
- attack: replay a valid signature on a different chain (missing chainId) or a second time on the same chain (missing nonce)
- proof: a second successful call using the identical signature bytes
- fp: EIP-712 domain separators that DO bind chainId and contract address are not this vector unless the nonce is still missing
- sev: critical when the signature authorizes a value transfer; high otherwise
- cwe: n/a
- kb: signature replay nonce chainid EIP-712 domain separator
