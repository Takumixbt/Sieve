# Changelog

All notable changes to Sieve are documented here. Versioning follows
[Semantic Versioning](https://semver.org/).

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
