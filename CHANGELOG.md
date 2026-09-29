# Changelog

All notable changes to Sieve are documented here. Versioning follows
[Semantic Versioning](https://semver.org/).

## [1.4.0] — 2026-09-29

### Added
- **Deterministic validation** (`references/validation.md`, `sieve/validate.py`, `sieve/judging.py`, `sieve/cites.py`) —
  a finding is CONFIRMED by a machine, not by narration. `sieve prove run` executes the PoC N times, requires a stable
  exploit signature and a **negative control** that stays silent (ideally `--control-patch`: the *same command* re-run against a
  patched copy of the target — a PoC that ignores the target cannot stop when the code is fixed), refuses echo-only "PoCs",
  destructive verbs, literal credentials and out-of-fence traffic, pins the PoC and cited-source hashes, and writes an
  HMAC-sealed receipt to a hash-chained ledger. `sieve verify [--rerun]` re-reads every citation by code, detects drift
  (`stale`), regressions and tampering. `sieve judge` grew stages (`cleared` for Gates 0-5, `confirmed`/`trace-only` for
  Gate 6), refuses a verifier who discovered the finding, enforces two independent verifiers for complex findings (disagreement
  demotes), the confidence threshold, and refuses `confirmed` without a passing receipt.
- **The report prints the machine's tier** (confirmed · trace-verified · unvalidated · stale · tampered · rejected · lead)
  and ignores an agent's own `status:` line; each confirmed finding shows its oracle, repeats, control kind and measured values.
- **The hunt pipeline commands the docs always promised** — `sieve bundle` (prints every bundle's size), `dispatch`
  (verifies bundle integrity, `--sequential` for no-fanout), `rollcall` (finished? quotas? markers?), `merge` (deterministic
  checks; demotes proofless / hedged / mis-cited FINDINGs to LEADs, never promotes), `absorb` (frontier rows close only with
  receipts), `frontier seed`, plus the roaming pass (`bundle --roaming`). Step order is enforced.
- **The campaign engine** (`references/campaign.md`, `campaigns/`, `sieve campaign …`) — an ultrafuzz-shaped, topology-driven
  static-analysis campaign: nodes of kind meta / agentic / reference, `repeat` and `matrix` expansion, profiles
  (smoke/default/exhaustive), exactly one primary output per node, versioned artifact contracts validated before a node is done,
  a threat-model → goal-plan chain, eight independent invariant lenses fanned in, a dynamic strategy node, looped roster
  hunts, a triage panel with quorum and a deterministic reportability gate, machine-run proofs, a differential-reference
  independence audit, resumable state with stale-artifact detection, and a loopback dashboard. ~55 static anti-pattern rules
  (`campaigns/rules/`) feed the frontier.
- `sieve lint` now validates the campaign topology for every profile, every prompt, every rule regex and every contract's own
  example, and that each agent's `name:` matches its file.

### Changed
- `sieve prove record` is deprecated: it files an *asserted* note that counts for nothing. Use `sieve prove run` / `prove add`.
- `sieve kb writeback` keys off the computed tier (confirmed → `confirmed` card; trace-verified → `curated`) and turns rejected
  candidates into false-positive lessons.
- The Stop hook and `sieve status` are campaign-aware; the persistence progress hash includes the campaign directory.
- `packs/web/agents/ai-native-appsec.md` renamed to `ai-native-appsec-agent.md` to match its `name:` (the roster keys on it).

### Fixed
- The state machine pointed at commands that did not exist (`bundle`, `dispatch`, `rollcall`, `absorb`, `merge`, `sieve map`,
  `frontier seed`, `sieve run`) and a never-written `sieve.cli_findings`; `sieve pass` skipped the bundle step.
- The report counted every FINDING file as confirmed regardless of evidence.

## [1.3.0] — 2026-09-29

### Added
- **`references/hypothesis-craft.md`** — the thinking half of the method: a hypothesis standard
  (assumption / break / observable / cheapest test / why-unseen), invariants derived through eight
  independent lenses then merged (with anti-vacuity checks and independent-reference audits, taken
  from `monad-developers/ultrafuzz`'s property-design pipeline), an eight-point asymmetry checklist,
  the three ledgers of history (precedent, the target's own fix-commits and prior-audit exclusions,
  your own lessons), and the **roaming pass** — a final hunt for classes no lens was looking for.
- **Bright lines vs. open ground** (`shared-rules.md`, `SKILL.md`) — an explicit contract: comply
  exactly with the fence, cite-or-drop, proof-or-lead, the gates, and receipts; think freely
  everywhere else ("creativity is spent on hypotheses, never on evidence"). Plus concrete
  hallucination **tripwires** (unseen names, flags from memory, IDs, numbers, "it doesn't exist",
  hedge words, stale conclusions) and `methodology.md` Part 6b, five things to do when you feel done.
- **Real Obsidian wiring** — `sieve vault init` turns `~/.sieve/kb` into a vault (graph colours, one
  note per vector card, class/domain hubs) and every KB card now carries `[[wikilinks]]`; `sieve vault
  export` writes an engagement as a linked graph (components, `INV-n` invariants, findings, dead ends
  with their ladder rungs, hypotheses). `sieve/vault.py`, `sieve/cli_vault.py`.
- **A lessons ledger** — `sieve kb lesson` (false-positive / miss / revived / technique);
  `kb writeback` records killed hypotheses as dead-end lessons; `kb prime` surfaces your lessons for
  the engagement's packs before the hunt starts.
- **`sieve install <prereq|web|web3|web3-chains|binary>`** — prints (or, with `--run`, executes) the
  install command for every tool, read from the roster table; `sieve doctor` reads the same table
  and now finds tools in `~/.cargo/bin`, `~/go/bin`, `~/.foundry/bin` etc. before `PATH` refreshes.

### Changed
- **`references/local-tooling.md` rewritten to one best tool per job** (~45 tools -> ~35, section
  numbers preserved). Burp Suite over its MCP server is the web hub; six BApp extensions replace a
  dozen CLIs; sqlmap remains only as confirmation. An explicit "not listed on purpose" section stops
  the roster creeping back. Every agent's Tool binding updated to match.
- **Agent openers reframed** from "you are an attacker who exploits X" to "you audit X the way an
  adversary would" — authorization-forward and precise, with every technique, checklist, and
  minimum-coverage requirement unchanged.
- `SKILL.md` tightened and re-sequenced around the new turns (hypothesis-craft in Turn 1, lessons in
  Turn 4, roaming pass before convergence in Turn 5, post-mortem + vault export in Turn 10);
  `dispatch.md` bundles carry `hypothesis-craft.md`; `xray.md` Phase 2 derives invariants through
  lenses and aims symbolic/fuzz tooling at the functions the invariant pass flags;
  `property-fuzzing.md` gains anti-vacuity rules.

### Removed
- Vector cards outside bounty-relevant web / web3 / APK-binary scope: EV-charger signalling,
  hypervisor and GPU-container escapes, browser-engine JIT/CSS/WebGPU UAFs, mobile-kernel GPU and
  iMessage zero-click chains, registry-control-plane and package-worm assessment cards, an
  AI-agent-sandbox card duplicated elsewhere, the LLM-as-judge and MCP-rug-pull assessment cards, the
  unverified federated-subgraph card, and the "AI chaining" card (now methodology, Part 8). 68 -> 50.
  Git history keeps them.
- Tools with no distinct job left after Burp MCP and the lean roster (ZAP, mitmproxy, nikto, hydra,
  dalfox, jwt_tool, mythril, Wake, surya, ItyFuzz, Certora, standalone gadget finders, and others).

## [1.2.0] — 2026-09-29

### Added
- **`sieve xray web3` now auto-invokes `slither`, `aderyn`, and (when installed) `trailmark`
  itself** — static analysis and call-graph construction are the mechanical layer's own first
  move, not corroboration the operator supplies after the fact (`references/xray.md` Phase 0,
  `sieve/xray_web3.py`). Cross-tool corroboration is now a mechanical field on every tool lead:
  `corroborated: true` when 2+ independent detector engines flag overlapping `file:line` —
  meaningfully higher confidence than either tool alone, surfaced in the printed x-ray summary.
- **A new `ai-native-appsec-agent`** in the web pack — prompt injection (direct, indirect,
  multi-modal, hidden-Unicode), insecure LLM output handling, MCP/plugin supply chain, agent
  memory/RAG poisoning, toxic tool-call composition, and guardrail bypass, with a proof-oracle
  discipline built specifically to avoid an agent's self-report counting as evidence. Added after
  a research pass confirmed the category is now mainstream-scale (an OWASP taxonomy, 40+ MCP CVEs
  in one quarter, EchoLeak, Anthropic's own 31.5% pre-mitigation browser-agent hijack-rate
  disclosure) rather than speculative.
- **68 new vector cards** (up from 14) distilled from real, named, dated 2026 incidents across all
  three packs — `packs/<pack>/vectors/2026-incident-patterns.md` — plus
  `packs/web/vectors/ai-native-appsec.md` and `packs/web3/vectors/cross-chain-and-altvm.md`
  (Algorand/Substrate/TON/Cosmos-SDK patterns, a previously uncovered chain surface).
- **`references/methodology.md` Part 8** — nine mindset lessons distilled from how real 2026
  incidents were actually found (read what an audit excluded; the patch diff is the disclosure;
  ask what a boundary actually captures; compute cost-to-attack vs. value-at-risk; which layer has
  ultimate authority; score composability, not components in isolation; new capability amplifies
  old bugs; AI compresses chaining velocity; never trust a model's self-report as proof).
- **`references/judging.md`**: a plain-language restatement pre-filter in Gate 0 (half of false
  positives collapse the moment a claim has to be said plainly instead of in its original shape),
  complexity-based triage routing complex findings through a second independent pass on Gates 1
  and 6, and a negative-PoC requirement alongside Gate 6's positive proof.
- **`references/xray.md`**: a fourth "Review Required" access-control classification bucket for
  dynamic/computed checks a grep pass can't resolve on its own; Five-Whys root-cause analysis and
  regression-detection (a diff reverting a past fix-commit's protection) added to the git-history
  pass; invariant-guided targeted `mythril` runs (once `xray/invariants.md` exists, target
  mythril at exactly the functions its guard-lift step flagged, instead of guessing).
- **`references/local-tooling.md`**: `heimdall-rs` promoted from a buried sub-note to a full table
  row (including its storage-layout-dump use against verified proxy contracts); `CloakBrowser`
  added for bot-defended recon targets; `trailmark` added as an auto-run call-graph accelerant;
  `Triton` added alongside `angr`; recon gaps filled (`dnstwist`, `knock`, `fierce`, regional
  search engines, breach-data lookups, BGP/network-ownership intelligence, `abuseipdb`).

### Design notes for future maintainers
- The ultrafuzz-inspired proposal to wrap the static-analysis pass in a full topology-file-driven
  multi-node campaign (mirrored from `monad-developers/ultrafuzz`'s real architecture) was
  deliberately *not* built as a generic orchestration engine — that's the same overbuild mistake
  `[1.0.0]`'s design note already warns about, just with a fuzzing-campaign shape instead of a
  parser shape. What shipped instead is proportionate: auto-run the tools that are actually safe
  and fast to auto-run, corroborate their output mechanically, and document (never automate) the
  slow/judgment-heavy step of targeting `mythril` at invariant-flagged functions.

## [1.1.0] — 2026-09-29

### Changed
- `references/local-tooling.md` expanded into a full brainstorm — every discovery, static,
  dynamic, exploit-development, and reporting tool worth knowing per pack, not just a starter
  list.
- Every agent file across all three packs deepened substantially: concrete commands tied to the
  expanded tool roster, exhaustive per-target checklists, and an explicit minimum-coverage
  contract so a pass can't be called complete after a shallow first read.
- `references/methodology.md` expanded: more of the creativity/persistence toolbox, worked
  through with concrete examples.
- `README.md`'s layout section rewritten as a full, precise directory tree (every file named, every
  directory labeled by role) instead of a partial flat list; `SKILL.md` gained a matching compact
  repository map and its References section turned from a prose wall into a grouped table, each
  group tagged with the lifecycle phase it matters for.

### Removed
- The `tests/` suite and `third_party/` directory. The Python CLI's own correctness is now
  self-checked by `sieve lint` (content) and `sieve doctor` (environment) rather than a parallel
  pytest tree — a skill repository should read as a skill, not as a piece of software with its
  engineering scaffolding on full display. (The removed suite's coverage is preserved in this
  repository's git history for anyone extending `sieve/`.)
- Inline attribution scattered through the working reference files. Methodology and tooling
  lineage now live in one place: `CREDITS.md`.

## [1.0.0] — 2026-09-29

### Added
- Initial release. Three packs — web3, web, binary/mobile — each with a full agent roster
  (`agents/README.md`), a fast-recall vector-card catalog (`packs/<pack>/vectors/*.md`), and
  pack-specific gate additions (`packs/<pack>/judging.md`).
- The persistence engine: `.sieve/frontier.tsv` as the engagement's work queue, the stuck ladder
  (`sieve ladder`), and a Claude Code Stop hook (`sieve hooks install`) that blocks the agent from
  ending a turn while work remains — enforced by real budgets (max blocks, no-progress release,
  wall-clock cap), never an unbounded loop.
- The knowledge base: local markdown cards with YAML frontmatter, a SQLite full-text index, and a
  rate-limited broker in front of Solodit and OSV so twelve parallel agents never exceed either
  API's real rate limit. `sieve kb writeback` grows the local store from every engagement's
  confirmed findings.
- Mechanical x-ray enumerators for all three packs (`sieve xray web3|web|git`) — discovery, nSLOC,
  test inventory, and (web3) a grep-only entry-point scan generalized across Solidity, Vyper,
  Move, Anchor, and Cairo. Deliberately does not classify or parse semantics — that stays the
  agent's job, corroborated by real tools (Slither/Aderyn) rather than a hand-rolled parser.
- The report assembler (`sieve report`) — dedup, sort, and count over agent-written finding files;
  never computes a verdict or confidence itself.
- `references/local-tooling.md` — the real tool roster and Burp extension list per pack.
- Vendored `scripts/generate_svg.py` (MIT) for the architecture diagram — attribution in the
  file's own header and in `CREDITS.md`.

### Design notes for future maintainers
- An earlier iteration of this skill included a hand-rolled Solidity structural parser and a
  multi-framework web route scanner. Both were removed (v1.0.0, pre-release) after review: they
  re-implemented what Slither/Aderyn and Burp/subfinder/katana already do, worse. If you're
  tempted to rebuild either, read `CREDITS.md` and `references/local-tooling.md` first — the fix
  for "the x-ray isn't deep enough" is almost always "wire in the real tool's output," not "write
  more Python to replace it."
