# VM gates - a mechanical entry gate for every chain, not just Solidity

`solana-scan.md` gave Solana the thing Solidity already had: six grep-verifiable
checks that run **before** any actor opens a file, so hypotheses start from
measured gaps instead of a cold read. This file does the same for every other VM
Sieve can be pointed at.

That coverage is the point. The best Solidity auditor in the world is still a
Solidity auditor; a Move or CosmWasm target hands it nothing. Sieve runs the same
discipline across EVM, Solana, Move, CosmWasm and Cairo. `sieve scan` detects which one a tree
needs, and the `narrative-web3` node runs the matching section as its first move.

**Every check produces LEADs, never FINDINGs** (`shared-rules.md` §1). A grep hit
shows a *shape*; an actor still traces the call to confirm it fires. Print the
coverage numbers before the report ships.

All patterns are POSIX ERE (`-E`), portable across GNU/BSD grep and ripgrep. Run
against the source tree, excluding build output, tests and dependencies.

---

## §EVM - Solidity / Vyper

Pashov's `x-ray` and `solidity-auditor` do this well; **if they are installed,
run them and use their output as this gate.** These checks are the fallback and
the cross-check.

```bash
# E1. External/public functions with no access modifier
grep -rnE 'function [a-zA-Z0-9_]+\([^)]*\)[^{]*\b(external|public)\b' [src] --include='*.sol'
```
For each, confirm an `onlyOwner`/role modifier, an internal `require`, or a
deliberate permissionless design → **LEAD** `unguarded-external-entrypoint`.

```bash
# E2. Raw value movement and low-level calls
grep -rnE '\.(call|delegatecall|staticcall)\{?|\.transfer\(|\.send\(' [src] --include='*.sol'
# E3. Unchecked blocks and assembly
grep -rnE '\bunchecked\s*\{|\bassembly\s*\{' [src] --include='*.sol'
# E4. Upgrade/init surface
grep -rnE 'initializer|reinitializer|_disableInitializers|__gap|delegatecall' [src] --include='*.sol'
# E5. Oracle and price reads
grep -rnE 'latestRoundData|getReserves|slot0|consult|price[A-Z]' [src] --include='*.sol'
# E6. ERC20 return-value handling
grep -rnE '\.(transfer|transferFrom|approve)\(' [src] --include='*.sol' | grep -v 'safe'
```
E5 → check staleness (`updatedAt`, `answeredInRound`) and manipulation window.
E6 → non-standard tokens that return nothing or false → **LEAD**
`unchecked-erc20-return`.

**Coverage to print:** external entrypoints guarded / total · unchecked blocks ·
delegatecall sites · unsafe ERC20 calls.

## §SOLANA - Anchor / native

Use `references/solana-scan.md` - six checks, already written, already validated
on a real engagement. Do not duplicate it here.

**Axis 2 is unusually rich on Solana**: native SOL, WSOL, SPL and Token-2022 are
four representations of "value", and handlers routinely implement three of the
four. Every missing branch is a `representation-asymmetry` lead.

## §MOVE - Aptos / Sui

Move's type system kills whole bug classes (no reentrancy, resources cannot be
copied or silently dropped), so the gate targets what it does **not** kill:
capability handling, generic type confusion, and object ownership.

```bash
# M1. Public entry points
grep -rnE '\b(public\s+)?entry\s+fun\b|\bpublic\s+fun\b' [src] --include='*.move'
# M2. Capability / admin resources moved or stored
grep -rnE '\b(AdminCap|OwnerCap|TreasuryCap|MintCap|Capability)\b' [src] --include='*.move'
# M3. Generic type parameters on value-bearing functions
grep -rnE 'fun [a-zA-Z0-9_]+<[^>]+>\(' [src] --include='*.move'
# M4. Sui object transfers and sharing
grep -rnE 'transfer::(public_)?(transfer|share_object|freeze_object)' [src] --include='*.move'
# M5. Direct signer-address trust
grep -rnE 'signer::address_of' [src] --include='*.move'
```
- M1 with no capability argument and no `assert!` on the caller →
  **LEAD** `unguarded-entry`.
- M3 is the Move-specific trap: a generic `<T>` on a function that moves value,
  with no phantom/witness constraint, lets a caller instantiate an unintended
  coin type → **LEAD** `generic-type-confusion`.
- M4 `share_object` on something holding value makes it globally mutable →
  confirm the intended ownership model.
- M5 trusting `signer::address_of` without checking it against stored state is
  the Move flavour of a missing owner check.

## §COSMWASM - Rust / Cosmos

```bash
# C1. Every ExecuteMsg variant and its handler
grep -rnE 'ExecuteMsg::[A-Za-z0-9_]+' [src] --include='*.rs'
# C2. Admin / owner checks
grep -rnE 'info\.sender|assert_owner|ensure_eq!|cw_ownable' [src] --include='*.rs'
# C3. Reply / submessage handling
grep -rnE 'SubMsg::|reply_on|fn reply\(' [src] --include='*.rs'
# C4. Migration entry point
grep -rnE 'fn migrate\(' [src] --include='*.rs'
# C5. Funds handling
grep -rnE 'info\.funds|BankMsg::Send|must_pay|one_coin' [src] --include='*.rs'
```
- Every C1 variant must appear in C2's guarded set or be deliberately open →
  **LEAD** `unguarded-execute-variant`.
- C3: a `reply` handler that trusts `msg.result` without matching the original
  `id` is the CosmWasm reentrancy analogue → **LEAD** `reply-id-unbound`.
- C4: `migrate` with no version check or no admin gate → **LEAD**
  `unguarded-migration`.
- C5: accepting funds without `must_pay`/`one_coin` lets a caller send the wrong
  denom or none at all.

## §CAIRO - Starknet

```bash
# K1. External entry points
grep -rnE '#\[external\(v0\)\]|#\[abi\(embed_v0\)\]' [src] --include='*.cairo'
# K2. Access control
grep -rnE 'get_caller_address|assert!|Ownable|AccessControl' [src] --include='*.cairo'
# K3. felt252 arithmetic on value
grep -rnE ':\s*felt252' [src] --include='*.cairo'
# K4. Upgrade surface
grep -rnE 'replace_class_syscall|upgrade' [src] --include='*.cairo'
# K5. L1<>L2 messaging
grep -rnE '#\[l1_handler\]|send_message_to_l1' [src] --include='*.cairo'
```
- K3 is the Cairo-specific trap: `felt252` is **not** a bounded integer and wraps
  modulo the field prime, so an amount or supply typed as `felt252` has no
  overflow protection → **LEAD** `felt-overflow-on-value`.
- K5 `l1_handler` functions are callable only by the L1 bridge; confirm the
  sender check, since a missing one is a direct mint/drain → **LEAD**
  `l1-handler-sender-unchecked`.

---

## §BACKEND - application source review (Python / Node / Go / Ruby / Java / PHP)

The case the Solidity tooling and the web pack's live-host recon do not cover: someone hands you a **backend repository** for a source
review. This is not on-chain and not a live target - it is code, and it gets the
same grid discipline as everything else. The axes are the web grid
(`packs/web/agents/access-control-agent.md`) recovered from source instead of from a running host:
authorization, authentication, input sinks, and secrets.

Detect the framework, then run its route + guard + sink scan. Route enumeration is
axis 1 of the web grid: every route is a cell, and every route whose handler lacks
an auth check is a lead.

```bash
# B1. ROUTES - enumerate every endpoint (the grid's row set)
grep -rnE '@(app|router|blueprint)\.(get|post|put|patch|delete)\(|@(require_http_methods)' [src] --include='*.py'   # Flask/FastAPI/Django
grep -rnE '\b(app|router)\.(get|post|put|patch|delete|use|all)\(' [src] --include='*.js' --include='*.ts'          # Express/Koa/Nest
grep -rnE '(r|mux|router|e|g)\.(GET|POST|PUT|PATCH|DELETE|Handle|HandleFunc)\(' [src] --include='*.go'             # Go net/http, gin, echo, chi
grep -rnE '^\s*(get|post|put|patch|delete|resources|namespace)\s' [src] --include='routes.rb'                      # Rails
grep -rnE '@(Get|Post|Put|Patch|Delete|Request)Mapping|@Path' [src] --include='*.java'                             # Spring / JAX-RS

# B2. AUTH GUARDS - which routes are actually protected (the grid's guard column)
grep -rnE '@login_required|@permission_required|IsAuthenticated|current_user|@jwt_required|before_action' [src]
grep -rnE 'requireAuth|isAuthenticated|passport\.|ensureLoggedIn|@UseGuards|@Roles' [src] --include='*.js' --include='*.ts'
grep -rnE 'authMiddleware|RequireAuth|c\.Get\("user"\)|AuthRequired' [src] --include='*.go'

# B3. RAW QUERY SINKS - SQLi
grep -rnE 'execute\(|executemany\(|raw\(|cursor\.|\.query\(|db\.Query\(|Statement|createQueryBuilder' [src] | grep -viE 'params|\?|\$[0-9]|prepare|bind'

# B4. DANGEROUS SINKS - RCE / SSRF / deserial / traversal
grep -rnE '\b(eval|exec|os\.system|subprocess\.|child_process|spawn|popen|Function\(|vm\.runIn)' [src]
grep -rnE '\b(pickle\.loads|yaml\.load|marshal\.loads|cPickle|unserialize|readObject|Marshal\.load|JSON\.parse\()' [src]
grep -rnE '\b(requests\.get|urllib|axios|fetch|http\.Get|open\(|readFile|sendFile|render_template_string)\(' [src]

# B5. SECRETS in tracked source (report immediately)
grep -rnE '(secret|token|api[_-]?key|password|private[_-]?key|aws_access)[\"'\'' :=]+[A-Za-z0-9/+_-]{16,}' [src] --include='*.py' --include='*.js' --include='*.ts' --include='*.go' --include='*.rb' --include='*.env' --include='*.yml'

# B6. MASS ASSIGNMENT / over-posting
grep -rnE 'update\(\*\*|\.update\(req\.body|permit!|Object\.assign\([a-z]+, req|setattr\(' [src]
```

Read each result as a grid cell:
- **B1 minus B2** is the finding set: a route that appears in B1 and whose handler
  contains no B2 guard is `route-missing-authz` - the source-side IDOR/broken-auth
  lead. Cross-check the **sibling rule**: if the `GET` handler pulls `current_user`
  and the `DELETE` on the same resource does not, that is the bug.
- **B3** hits where the query is built by string concatenation / f-string / template
  literal rather than a parameterised placeholder → `sqli-source`.
- **B4** confirm the sink is reachable from a route with attacker-controlled input;
  `yaml.load` without `SafeLoader`, `pickle.loads` on a cookie, and
  `render_template_string(user_input)` (SSTI) are the highest-yield.
- **B5** any match is reported at once as a tracked-secret exposure, per
  `shared-rules.md`.
- **B6** a model update fed the whole request body lets a caller set fields the UI
  never exposed (`is_admin`, `balance`, `role`) → `mass-assignment`.

**Coverage to print:** routes enumerated · routes with an auth guard · guard-gap
routes (the lead list) · raw-query sinks · dangerous sinks reachable from a route ·
tracked secrets. This maps one-to-one onto the web pack's authorization grid, so a source
review and a live test of the same app produce comparable coverage numbers.

Framework nuances that a generic pass misses:
- **Django** - an `@api_view` with no `permission_classes` inherits the *project*
  default; check `REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES']`, because
  `AllowAny` there silently opens every unmarked view.
- **Express** - middleware order is positional; a route registered *above* the
  `requireAuth` line is public regardless of intent.
- **Rails** - `before_action` with `only:`/`except:` lists drift out of sync with
  the action list as controllers grow; diff the two.
- **Spring** - method security (`@PreAuthorize`) is inert unless
  `@EnableMethodSecurity` is on; a project relying on it without the enable is
  wide open.
- **Go** - no framework convention forces auth; middleware is wired per-router, so
  a handler registered on the wrong mux/group has no guard and nothing flags it.

---

## What this gate is not

It does not replace an actor tracing a lead to a real exploit. A grep hit is a
shape, and several of these checks (M3, C3, K3) need a human-grade read of the
surrounding logic to separate "genuinely missing" from "checked a different,
equally valid way". Treat every hit as a LEAD and gate it exactly like any other
(`judging.md`). This file only makes the *first* pass cheap and unfakeable.
