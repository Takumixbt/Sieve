# Property fuzzing — Echidna / Medusa, once an invariant is stated

`invariant-agent.md`'s job is finding the invariant and a first counterexample by reasoning; a
stateful fuzzer's job is proving it holds (or finding a *different* counterexample) across many more
sequences than a human would try by hand. Run the fuzzer once you have a stated property, not as a
substitute for stating one — an unguided fuzzer with no property to check just burns compute.

## Writing the property

Start from `templates/InvariantHandler.t.sol` — a fill-in Foundry-style harness with the handler
pattern both Echidna and Medusa expect: a set of bounded, randomizable actions (`deposit`,
`withdraw`, `donate`, `skipTime`, ...) and one or more `invariant_*` functions asserting the
property from `xray/invariants.md` or the one `invariant-agent.md` derived.

```solidity
function invariant_conservation() public {
    assertEq(totalDeposited - totalWithdrawn, token.balanceOf(address(vault)));
}
```

## Running it

```bash
# Echidna — longer track record, mature corpus/coverage tooling
echidna . --contract InvariantHandler --config echidna.yaml

# Medusa — parallelizes natively, faster wall-clock on multi-core machines
medusa fuzz --config medusa.json
```

Seed the corpus from real transaction traces against this target where available (a mainnet-fork
replay, a prior audit's PoC transactions) — an empty corpus rediscovers basic validity for a long
time before it reaches anything interesting.

## Reading a failure

A broken invariant gives you a concrete call sequence — that sequence **is** the proof oracle
`judging.md` Gate 6 wants: paste it into a Foundry test (`forge test --match-test
test_invariant_break`) to turn the fuzzer's counterexample into a deterministic, replayable PoC
before writing the finding up.

## Reading a pass

A property that survives a long, well-seeded run is real evidence the invariant holds under the
inputs and action set the harness covers — but it is not proof for action sequences the harness
never modeled (a handler missing an admin action, a token behavior the harness doesn't simulate).
Note what the harness actually covers in the finding/coverage write-up; a clean fuzz run is
evidence, not a guarantee, and `judging.md`'s evidence-or-silence rule applies to negative results
too — say what was checked, not "nothing found."
