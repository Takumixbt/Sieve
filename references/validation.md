# Validation — a finding is CONFIRMED by a machine, not by narration

Every audit tool's real failure is not missing bugs; it is **shipping bugs that are not there**. An agent
that has talked itself into a finding will also talk itself into a proof: it writes "verified", it files a
receipt that says so, it labels the file `status: confirmed`, and the report prints it. Gate 1's
"re-read the line" and Gate 6's "attempt a negative PoC" are the right instincts — but as prose they are
only as strong as the agent's honesty on its worst day.

So this skill moves the decision out of the prose. **`confirmed` is a value the tool computes from
evidence the tool checked.** The agent still does all the thinking — the hypothesis, the PoC, the control,
the refutation — but it cannot mark its own work as proven. (`judging.md` is *what* the gates ask;
this file is *how the answer becomes machine-checked*.)

## What the machine checks

| Check | How | What it kills |
|---|---|---|
| **Citations exist** | every `file:line` in a finding is re-read by code (`sieve/cites.py`); a quoted snippet must appear within ±3 lines of the cited line | invented files, invented line numbers, code quoted from memory |
| **The proof is executed** | `sieve prove run` runs the PoC command itself, several times (default 3) | "the PoC works" said instead of shown |
| **The exploit is stable** | the signature regex must match on *every* run, and any value captured (`--capture profit=(\d+)`) must be identical across runs | flaky proofs; numbers typed by hand instead of measured |
| **A negative control exists and stays silent** | the same signature must **not** appear in the control run; if it does, the proof is `VACUOUS` and failed | a test that "passes" whether or not the bug exists — the most common fake proof |
| **The control is a mutation, ideally** | `--control-patch fix.diff` re-runs the *identical command* against a throw-away copy of the target with the fix applied | a PoC that ignores the target (a script that prints `PASS`): patching the code cannot make it stop |
| **Echo-only "PoCs" are refused** | a command that only prints text is rejected before it runs | a literal `echo "[PASS]"` |
| **The PoC and the code are pinned** | the receipt records the SHA-256 of the PoC files and of every cited source file | proving one thing, then editing it; proofs that silently outlive a change |
| **A verifier that isn't the discoverer signed off** | `sieve judge` refuses a verifier named in the finding's `found_by`; complex findings need two distinct verifiers per stage; disagreement demotes | a finding gating itself; one lenient reviewer |
| **Confidence clears the threshold** | `--confidence` must meet `audit.confidence_threshold` (75) | "probably real" |
| **The oracle is independent** | (campaign, `default`/`exhaustive`) an auditor checks the proof's expected value is not computed by the code under test | circular tests that pass by construction |
| **Nothing was edited afterwards** | receipts and verdicts carry an HMAC and join an append-only hash chain (`.sieve/proofs/ledger.jsonl`) | a hand-edited receipt, a deleted receipt, a hand-written one |

## Tiers — what the report prints

`sieve/validate.py:assess()` combines those checks into **one tier per finding**. The report prints this
tier and ignores whatever the finding file's own `status:` line claims (a mismatch is called out).

| Tier | Meaning |
|---|---|
| **confirmed** | judged confirmed by a non-discoverer at confidence ≥ threshold **and** citations verified **and** a sealed exec receipt with verdict `pass` (repeated, stable, control silent) — for critical/high/medium. Low/informational need citations + verdict only and print as trace-verified |
| **trace-verified** | cleared the gates and every citation re-reads correctly, but no controlled executable proof: a low-severity static finding, an uncontrolled run, captured evidence that was evaluated but not re-executed, or `--verdict trace-only` with a reason on record |
| **unvalidated** | raised as a finding, but the machine cannot stand behind it (no proof, failed proof, confidence too low, not judged). Printed in its own section with the reason — never as a finding |
| **stale** | it was proven, but the cited code or the PoC changed afterwards. `sieve verify <id> --rerun` re-executes it |
| **tampered** | a receipt or verdict failed its seal, or a receipt exists that `sieve` did not write. The report refuses to enter the report phase until a human looks |
| **rejected** | a verifier killed it. Counted, never listed as a finding; becomes a *false-positive lesson* in the KB |
| **lead** | LEAD/HYPOTHESIS, or demoted. High-signal trail, not a claim |

## The flow, in commands

```
sieve merge                      # parse raw agent output: a FINDING with no proof / hedge wording / a bad
                                 # citation is kept as a LEAD with the reason written on it (never promoted)
sieve judge F-001 --verdict cleared  --verifier verifier-1 --reason "Gates 0-5: ..."          # Gates 0-5
sieve prove run F-001 --oracle fork-test \
      --cmd 'forge test --match-test testSweep -vv --fork-url $RPC_URL' --env RPC_URL --infra-host eth.example \
      --expect '\[PASS\] testSweep.*profit=(\d+)' --capture 'profit=profit=(\d+)' \
      --control-patch .sieve/proofs/F-001/fix.diff                                             # Gate 6, executed
sieve judge F-001 --verdict confirmed --verifier verifier-1 --confidence 90 --reason "..."     # refused without a pass receipt
sieve verify --all [--rerun]     # re-read every citation, check every seal and hash, re-execute proofs
sieve report                     # prints the computed tier
```

Two refusals to expect, and why they are correct:

- `sieve judge … --verdict confirmed` on a critical/high/medium finding **with no passing exec receipt** is refused and
  prints the three honest ways forward: run the PoC, capture evidence (`prove add`, → trace-verified), or
  `--verdict trace-only --reason` (a waiver, printed in the report's Coverage section).
- `sieve prove run` with **no control** is refused. `--control-waiver "why"` records the proof as uncontrolled; it can
  reach trace-verified, never confirmed.

## Writing a proof that survives the check

The check rewards proofs that would be persuasive to a skeptical human. Per pack:

- **web3** — a Foundry test against a fork (`forge test --match-test … --fork-url $RPC_URL`) whose assertion is the
  *consequence* (funds moved, a balance gone wrong), plus the fix as a diff for `--control-patch`. Compute expected values from
  the deposit amounts or the spec, not by calling the contract's own accounting (the independence audit reads this).
- **web** — a two-identity replay: the same request as the owner and as another user, expecting the other user's data;
  the control is the request with the second identity's *own* object, or without the credential. Declare every host with
  `--target`; the fence checks each one and refuses if `rules.active_testing` is false. If it is false, capture the traffic
  yourself and use `sieve prove add` (caps at trace-verified).
- **binary** — a crash reproduction under a sanitizer with the fixed build (or the bounds-check patch) as the control; a Frida
  script whose output distinguishes the vulnerable path.
- **Numbers** in a finding's description must be the run's `--capture`d values. A number nobody measured is a tripwire
  (`shared-rules.md`).

## The seatbelt (what `prove run` refuses)

Destructive verbs (`rm -rf /`, `mkfs`, `DROP TABLE`, HTTP `DELETE`, fork bombs, power control); a command containing what looks
like a literal credential (put it in an env var and pass `--env NAME`); traffic to any URL or `--target` the scope fence does not
list, or any traffic at all when `rules.active_testing` is false; a network oracle with no declared target. The environment passed
to the PoC is scrubbed to a small allow-list plus the names you pass with `--env`; receipts store output excerpts with secrets
redacted and store only variable *names*. This is a seatbelt against mistakes, not a sandbox against a hostile PoC — run PoCs in
the fork/lab the scope card names.

## What this does NOT do — read this before trusting a green tier

- **It cannot tell a well-built fake from a real bug.** A script that prints `[PASS]` *and* a control script that prints `[FAIL]`
  will satisfy a weak setup. That is why the strongest control is `--control-patch` (a fake cannot stop when the code is patched),
  why echo-only commands are refused, and why the report prints each confirmed finding's oracle, control kind and command. **A human
  reads the PoC before a submission.** The tier is "a machine reproduced it and could not make it vanish without the fix" — a very
  high bar, not omniscience.
- **The seal is tamper-*evident*, not tamper-proof.** The HMAC key lives in `.sieve/.seal-key` on the same disk. It stops accidents
  and narrated shortcuts; forging a receipt takes a deliberate read of that file and would show in the transcript.
- **A pass on a fork is not proof of exploitability in production**, and severity is still a judgement — the verifier sets it
  (`--severity`), and the report prints the verifier's, not the discoverer's.
- **Static rule hits, Slither output and precedent cards are leads.** They never reach a tier above `unvalidated` on their own.

## Anti-patterns (each one has been observed; each now fails a check)

- A receipt whose evidence is "trust me" → recorded as `asserted`; counts for nothing.
- A `[PASS]` that also prints on the patched code → `VACUOUS`.
- Proving on Monday, editing the PoC on Tuesday → `stale`.
- Numbers in the write-up that the run never printed → the description is checked against `--capture` by the reviewer, and
  the tripwire in `shared-rules.md` names it.
- `status: confirmed` typed into the file → the report prints "unvalidated" and flags the mismatch.
