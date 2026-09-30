# Cross-chain and alt-VM coverage

`sieve/xray_web3.py`'s entry-point grep patterns lean Solidity/Vyper/Move/Cairo/Anchor-Rust-heavy -
that's real coverage for the chains most bounty programs and audit contests target, but it leaves
Algorand, Substrate, TON, and Cosmos-SDK (as distinct from CosmWasm, which the base pack already
covers) with no dedicated attack-pattern cards at all. This file is a **starting set, not an
exhaustive one** - each chain below has a well-documented, much longer canonical pattern list
(Trail of Bits' `building-secure-contracts` guidelines name 11 Algorand patterns, 9 Cosmos-SDK
patterns, 7 Substrate patterns, and 3 TON patterns) than the handful of cards here. Treat a clean
pass against this file as a floor, not a ceiling, and lean on `sieve kb search --online` for what
this file doesn't yet name.

## Algorand

### ALGO-REKEY-01 · Unchecked RekeyTo field enables silent authority hijack
- signal: a dApp or contract logic that approves a transaction group without explicitly checking every transaction's `RekeyTo` field is empty (or matches an expected value)
- attack: submit a transaction group where an otherwise-legitimate-looking transaction also carries a non-empty `RekeyTo`, transferring signing authority for that account to an attacker-controlled address; every future transaction from the account can now be authorized by the attacker regardless of the original key
- proof: a testnet transaction group demonstrating the rekey succeeding through logic that was supposed to gate the transaction on something else, followed by a second transaction signed by the new authority
- fp: a contract that explicitly checks `Txn.RekeyTo == Global.ZeroAddress` (or an allow-listed value) on every transaction in the group it approves is not vulnerable to this - confirm the check is present on *every* transaction in the group, not just the one the contract logic focuses on
- sev: Critical
- cwe: CWE-732
- kb: algorand rekey vulnerability RekeyTo unchecked authority hijack

### ALGO-CLOSE-01 · Unchecked CloseRemainderTo / AssetCloseTo redirects funds
- signal: contract logic that approves a payment or asset-transfer transaction without checking the `CloseRemainderTo` (Algo) or `AssetCloseTo` (ASA) fields are empty
- attack: submit a transaction that passes the contract's intended validation (correct amount, correct receiver) but also sets a close-to field, redirecting the *entire remaining balance* of the sending account to an attacker address as a side effect of an otherwise-valid transaction
- proof: a testnet transaction showing the account's full balance moved to an unintended address via a transaction that the contract's stated logic should have approved for a much smaller, specific amount
- fp: a contract explicitly checking both close-to fields are the zero address (or an expected value) on every relevant transaction is not vulnerable - confirm the check, don't assume it from the contract's general shape
- sev: Critical
- cwe: CWE-732
- kb: algorand CloseRemainderTo AssetCloseTo unchecked fund redirect

### ALGO-FEE-01 · Unchecked transaction fee in an atomic group
- signal: contract logic in an atomic transaction group that makes an assumption about fee cost or fee-payer identity without checking the `Fee` field explicitly
- attack: exploit fee-pooling behavior within an atomic group (Algorand pools fees across grouped transactions) to grief the contract's expected fee economics, or construct a fee-zero transaction that the contract's logic didn't anticipate
- proof: a testnet transaction group demonstrating fee-related logic behaving other than intended (a griefing cost, a bypassed fee-payer assumption)
- fp: contract logic with no fee-dependent behavior at all is not in scope for this card
- sev: Medium
- cwe: CWE-841
- kb: algorand unchecked fee atomic group pooling

## Substrate (Polkadot/Kusama parachains)

### SUBSTRATE-ORIGIN-01 · Missing or incorrect origin check on a privileged extrinsic
- signal: a pallet extrinsic that performs a privileged action (mint, slash, parameter change, admin-only operation) without an explicit `ensure_signed`/`ensure_root`/custom-origin check matching the action's actual privilege level
- attack: call the extrinsic from an unprivileged (or wrongly-privileged) origin and observe whether the privileged action executes anyway
- proof: a runtime test (or a call against a local dev chain) showing the extrinsic succeeding from an origin that should have been rejected
- fp: an extrinsic correctly gated by a custom origin type that the review didn't initially recognize as equivalent to `ensure_root`/`ensure_signed` is not vulnerable - read the actual origin-check logic, don't assume from its unfamiliar name
- sev: Critical
- cwe: CWE-862
- kb: substrate pallet BadOrigin missing check privileged extrinsic

### SUBSTRATE-WEIGHT-01 · Underestimated extrinsic weight enables cheap DoS
- signal: an extrinsic's declared `#[pallet::weight(...)]` annotation appears to underestimate the actual computational/storage cost of the code path it gates, especially a path with a loop or unbounded-size input
- attack: call the extrinsic with input sized to maximize actual execution cost while the declared weight (and therefore the fee charged) stays low, repeating cheaply to consume block space disproportionate to the fee paid
- proof: a benchmark run (Substrate's own `frame-benchmarking` tooling) showing measured weight substantially exceeds the declared weight for a realistic worst-case input
- fp: a weight that's merely conservative (overestimates cost) is not this bug - the finding is specifically an *underestimate*, verified by benchmark, not by inspection alone
- sev: High
- cwe: CWE-405
- kb: substrate pallet weight underestimate benchmark DoS

### SUBSTRATE-PANIC-01 · Runtime panic from unchecked arithmetic or unwrap
- signal: pallet on-chain logic using raw arithmetic operators, `.unwrap()`, or `.expect()` on a `Result`/`Option` instead of checked arithmetic (`checked_add`, etc.) or explicit error handling
- attack: construct input that drives the unchecked operation to overflow/underflow or the `Option`/`Result` to `None`/`Err`, triggering a runtime panic - on a Substrate chain this can halt block production for the whole network, not just revert one transaction
- proof: a local dev-chain reproduction showing the panic and its effect on block production, with the exact triggering extrinsic and parameters
- fp: arithmetic inside a `#[cfg(test)]`-only path or genuinely unreachable from any external extrinsic input is not this vector - confirm the reachable input path
- sev: Critical
- cwe: CWE-248
- kb: substrate pallet panic overflow unwrap runtime halt

## TON

### TON-BOOL-01 · Integer-as-boolean confusion in FunC
- signal: FunC code using `if (some_int)`-style conditionals where `some_int` is expected to hold boolean semantics - FunC has no native boolean type, and TON's convention represents "true" as `-1`, not `1`
- attack: identify a code path where a value that's `1` (or any non-zero, non-`-1` value) is treated inconsistently by different parts of the contract - one path checking truthiness generically (any non-zero) while another expects the strict `-1` convention - and craft input landing in that inconsistency
- proof: a local TON sandbox/testnet reproduction showing the contract's behavior diverges from its intended logic specifically because of a `1` vs `-1` truthiness mismatch between two code paths
- fp: consistent use of a single truthiness convention throughout the contract (even if it's the "any non-zero" convention rather than strict `-1`) is not this bug - the finding is specifically an *inconsistency* between code paths, not the choice of convention itself
- sev: Medium
- cwe: CWE-697
- kb: ton func integer boolean confusion true false convention

### TON-JETTON-01 · Fake Jetton contract acceptance
- signal: a contract that reacts to an incoming Jetton transfer-notification message without independently verifying the sender is the genuine Jetton-wallet contract for the expected Jetton-master (via TON's deterministic state-init/address-derivation, not merely trusting the claimed sender field)
- attack: deploy a fake "Jetton wallet" contract that sends a transfer-notification message mimicking a real token transfer for an amount/token the victim contract trusts, without any real token value ever changing hands
- proof: a local TON sandbox reproduction showing the victim contract crediting a balance, granting an action, or releasing value in response to the fake notification with no genuine Jetton transfer having occurred
- fp: a contract that derives the expected Jetton-wallet address itself (from the Jetton-master and the sender) and compares it against the actual message sender before trusting the notification is not vulnerable - confirm the derivation-and-compare step is actually present, not merely a sender address recorded somewhere
- sev: Critical
- cwe: CWE-345
- kb: ton jetton fake wallet contract transfer notification verification

### TON-GASFWD-01 · Message forwarding without a gas-sufficiency check
- signal: a contract that forwards a message (and often value) to another contract or continues its own execution after an external call, without checking that sufficient gas remains for its own subsequent logic to complete
- attack: construct a call chain that exhausts gas partway through the forwarding contract's post-forward logic, leaving it in a partially-updated, inconsistent state (a state update that should have been atomic with the forward instead completes only on one side)
- proof: a local TON sandbox reproduction showing the contract left in an inconsistent state after a gas-exhausted forward, with the specific state fields that diverged from the atomic-intent
- fp: a contract that explicitly reserves gas for its own post-forward logic (TON's `SEND_MODE` flags and explicit gas budgeting) before forwarding is not vulnerable - confirm the reservation is actually sized correctly for the worst-case post-forward path
- sev: High
- cwe: CWE-696
- kb: ton gas forwarding insufficient check message chain atomicity

## Cosmos SDK (chain-level modules, not CosmWasm contracts)

### COSMOS-UNDELEGATE-01 · Undelegation/unbonding time-validation gap
- signal: a custom module that extends or wraps Cosmos SDK's staking module logic, with its own handling of unbonding periods, redelegation, or early-withdrawal conditions
- attack: construct a sequence of delegate/undelegate/redelegate calls that exploits an incorrectly-validated unbonding-completion timestamp to withdraw or reuse stake before the real unbonding period has elapsed
- proof: a testnet reproduction showing stake withdrawn or double-counted before the module's own documented unbonding period has actually completed
- fp: a module that correctly delegates all unbonding-time validation to the base Cosmos SDK staking module's own logic (rather than reimplementing it) is not in scope for this card unless it also overrides that specific validation
- sev: High
- cwe: CWE-367
- kb: cosmos sdk staking undelegation time validation early withdrawal

### COSMOS-ROUND-01 · Rounding-direction inconsistency in share/token conversion
- signal: a module converting between a share representation and an underlying token amount (staking shares, distribution rewards, a custom vault-like module) where the rounding direction isn't explicitly and consistently biased in the protocol's favor
- attack: repeatedly perform small deposit/withdraw or delegate/undelegate operations that each round in the user's favor by a tiny amount, accumulating a drainable discrepancy over many operations (or a single large operation sized to maximize one rounding step)
- proof: a script or test demonstrating the cumulative discrepancy after N operations, with the module's actual balance diverging from the sum of what each operation's rounding should have produced if biased correctly
- fp: a module using `sdk.Dec`/fixed-point arithmetic with an explicit, consistently-applied rounding-down-for-the-user policy (matching the reference Cosmos SDK modules' own convention) is not vulnerable - confirm the actual rounding direction in code, not just that fixed-point math is used
- sev: Medium
- cwe: CWE-682
- kb: cosmos sdk rounding direction share conversion drain

### COSMOS-AMOUNT-01 · Missing amount validation on a module message handler
- signal: a custom module's `Msg` handler that credits or debits an account based on a `Coin`/`sdk.Int` amount field without validating it is positive and won't overflow the account balance's underlying type
- attack: submit a message with a zero, negative (where the type permits it), or overflow-inducing amount and observe whether the handler's balance update produces an unintended result (a negative balance interpreted as a large positive one, an overflow wrapping to a small value, a no-op that still emits a success event)
- proof: a testnet transaction showing the account balance or module state end up in a value inconsistent with the amount that should have been transferred, directly attributable to the missing validation
- fp: a handler that calls the Cosmos SDK's own `Validate()` on the `Msg` (which typically enforces positive amounts) before processing is not vulnerable to this specific pattern - confirm the validation actually runs and covers this exact field, not a different one
- sev: High
- cwe: CWE-20
- kb: cosmos sdk module message handler amount validation overflow
