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

## Make sure the property can fail (anti-vacuity)

A green run means nothing until you've shown the property is *able* to go red. Before trusting one:

1. **Plant the bug.** In a scratch copy, weaken the guard the invariant protects (or reintroduce a
   known-fixed bug) and confirm the fuzzer now finds a counterexample. No failure → the harness is
   vacuous, and every green result from it so far was noise.
2. **Prove the handlers reach the risky code.** Check line coverage on the exact functions the
   invariant protects. A handler whose preconditions are never satisfied, or that never calls the
   function you care about, is a harness that tests itself.
3. **Bound for feasibility, not safety.** Clamping handler inputs to "sensible" values can make a
   real failure unreachable. Let amounts hit zero, one, and the maximum; let actors be the
   attacker; let time skip. Restrict only what the real system also can't do.
4. **Keep the reachable failures.** If the fuzzer finds a break you think is "unrealistic," check
   whether the real contract can reach that state before you constrain the handler around it — the
   constraint may be hiding the finding.

Derive the properties themselves through independent lenses and merge them first
(`hypothesis-craft.md` §2) — a fuzzer checks the invariants you gave it, so the ones you didn't
think of are the ones it can't find.

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
