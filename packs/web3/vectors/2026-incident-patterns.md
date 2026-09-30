# 2026 incident patterns

Every card below traces to a real, named, dated 2026 incident - not a hypothetical. 2026's single
biggest shift, confirmed independently by CertiK/Chainalysis: **compromised keys and credentials
overtook smart-contract code bugs as the leading attack vector for the first time on record.** Half
of these cards are unreachable by Slither/Aderyn/Echidna entirely - they are governance, key-custody,
and cross-protocol trust questions a code-only checklist has no bucket for. See
`references/methodology.md`'s "mindset from 2026 incidents" section for the researcher-framing
lessons distilled from the full incident set.

## Cross-chain / bridge trust

### WEB3-BRIDGE-01 · Single-verifier / missing-origin cross-chain message trust
- signal: a bridge/messaging receiver contract (LayerZero OApp, Axelar executable, CCIP receiver, etc.) that (a) runs below the framework's recommended N-of-M verifier/DVN threshold, or (b) exposes an "express"/fast-path execute function callable by anyone without checking `msg.sender` against the canonical gateway/endpoint address
- attack: enumerate high-TVL OApp/receiver contracts against the messaging framework's public verifier-configuration registry; for a 1-of-1 or otherwise single-point-of-failure config, compromise or spoof that one verifier's data feed (RPC compromise, DDoS the honest path, or directly call the express-execute entrypoint with a fabricated commandId/sourceChain/sourceAddress); trigger mint/release on the destination chain with no genuine burn/lock on the source chain
- proof: a fork test (or live-fork simulation) calling the receiver's execute/expressExecute function directly with a forged payload and confirming funds move without a corresponding source-chain event; alternatively, an on-chain query showing the OApp's DVN/verifier count is below the framework-recommended threshold
- fp: "the framework's own docs list this as a default configuration" is not a false-positive excuse - flag it anyway; distinguish from a genuine false positive where the receiver DOES check `msg.sender` against a hardcoded, non-upgradeable gateway address and enforces N>=2 independent verifiers
- sev: Critical
- cwe: CWE-345
- kb: cross-chain bridge single verifier DVN default configuration exploit OR missing origin check express execute

## Governance

### WEB3-GOV-01 · Governance-scope overreach and cheap-quorum takeover
- signal: a DAO/chain governance system whose voting token has (a) historically low turnout relative to circulating supply, (b) no timelock (or a short one) between proposal passage and execution, and/or (c) authority - directly, or via a `MsgUpdateAdmin`-style chain-governance primitive - that reaches into contracts owned by a DIFFERENT protocol's own multisig
- attack: compute cost-to-acquire-decisive-stake (buy and stake enough governance tokens to clear the realistic/historical quorum, often in the closing minutes of a vote) versus value-at-risk (treasury, or admin rights over external contracts reachable via that governance); if cost << value, buy the stake, submit or back a proposal that grants the attacker funds or admin rights, and execute the instant the vote closes or the short/absent timelock expires
- proof: a governance-parameter report showing (recent realistic quorum in tokens) × (current token price) << (treasury value, or downstream contract TVL reachable via granted admin rights); for chain-level governance, an on-chain query enumerating every contract whose admin is a governance-controlled address rather than its own team multisig
- fp: a high nominal market cap is not protection if realistic turnout/quorum is low - do not close this out just because "the token has a $X00M market cap"; compute the actual historical clearing cost instead
- sev: High
- cwe: CWE-841
- kb: DAO governance takeover low quorum treasury drain OR chain governance MsgUpdateAdmin contract admin override

## Intent / solver settlement

### WEB3-INTENT-01 · Intent/solver settlement-path verification gaps
- signal: an intent-based settlement/solver-competition system with (a) a hardcoded or stale gas/compute ceiling used to "verify" candidate solver routes before accepting the winning quote, and/or (b) fallback routing into a low-liquidity venue when the primary/best route can't be verified or executed on-chain, for large or "fill-or-kill" orders
- attack: identify (via simulation or observed verification-system behavior) an order size/pair combination where the verification ceiling excludes every well-priced execution route, leaving only a catastrophically bad quote as the sole "passing" option; submit or wait for such an order, let settlement route into the thin fallback pool, and in the same or next block, flash-loan-arbitrage the resulting price dislocation, optionally aided by visibility into the pending settlement via a private-mempool/solver-relay leak
- proof: a Tenderly/Foundry-fork simulation of the solver-verification pipeline against current pool liquidity and the production gas/compute ceiling, showing that for a given order size, all economically-reasonable routes are filtered out and only a route through an illiquid pool passes verification
- fp: a large order that gets a merely "somewhat worse than optimal" price due to normal slippage is not this bug - the signal is specifically a verification/filtering mechanism that categorically excludes viable routes, not routine price impact
- sev: High
- cwe: CWE-841
- kb: intent solver settlement verification gas limit stale illiquid route MEV backrun

## Supply chain / patch adoption

### WEB3-SUPPLY-01 · Upstream fix merged, release not backported (patch-lag window)
- signal: a shared dependency (L1/L2 client, Cosmos SDK module, cryptographic library, rollup client) whose public git history shows a security-relevant fix merged to a main/default branch, while the tagged releases that downstream chains/protocols actually run still predate that commit
- attack: diff the dependency's public commit history for security-relevant changes (arithmetic bounds, validation logic, caching correctness) not yet present in the latest tagged release; identify every downstream chain/protocol still running a pre-fix tagged release; exploit the now-publicly-documented bug against any of them before they upgrade, racing the patch-adoption window
- proof: a reproduction against the exact vulnerable tagged-release version (not main/master) showing the bug is live, paired with a timestamp comparison showing the fix commit predates the exploit by days-to-months while the downstream release tag postdates or is absent
- fp: a fix present in the CURRENT tagged release that a chain simply hasn't upgraded to yet is an operational/deployment-lag finding (still worth flagging as coverage-debt) but is a different risk tier than a fix that was never backported to any release branch at all - distinguish the two in severity
- sev: High
- cwe: CWE-1104
- kb: security fix merged main branch not backported release tag exploited downstream chains
