# Credits

Sieve builds directly on the published, permissively-licensed work of others. Where content is
adapted rather than newly written, it's named here and, where practical, in the file itself.

## Pashov Audit Group — `github.com/pashov/skills` (MIT)

The single biggest influence on this skill's shape. Vendored directly: `scripts/generate_svg.py`,
the architecture-diagram generator (`third_party/pashov-skills-LICENSE` carries the original MIT
license text). Structurally adapted, with attribution in each file's frontmatter comment where it
applies: the twelve `packs/web3/agents/*.md` lenses (generalized past Solidity to Move/Anchor/
Cairo/Vyper), the Feynman/Socratic/Inversion mental tools in `references/methodology.md`, the
four-gate core of `references/judging.md`, and the grep-then-read x-ray method in
`references/xray.md`. Their `solidity-auditor` and `x-ray` skills remain the sharper tool for
Solidity-only work; Sieve exists for the targets those tools don't cover (multi-VM web3, web,
binary/mobile) and the seams between them.

## Cyfrin / Solodit — `solodit.cyfrin.io`

The web3 precedent database `references/knowledge.md` and `sieve kb search --online` are built
around. API details in `references/local-tooling.md` and `sieve/kb_net.py`.

## Prior art that shaped the design, not vendored

- **Trail of Bits — `github.com/trailofbits/skills`** — the plugin-catalog structure for
  security-research skills more broadly.
- **Invariant Helix** and **BountyForge** (community skills) — the x-ray-as-executive-summary
  pattern, the crossover/seam-hunting concept (`references/crossover.md`), the persistence/
  "wild-mode" doctrine that shaped `references/shared-rules.md`'s anti-laziness section and the
  Stop-hook enforcement in `sieve/hook.py`, and the multi-gate judge concept that informed
  `references/judging.md`'s six-gate sequence.

## Open-source tools this skill orchestrates but does not vendor

Burp Suite, subfinder, httpx, katana, nuclei, ffuf, gau, dalfox, sqlmap, Slither, Aderyn, Foundry,
Echidna, Medusa, Mythril, Semgrep, Ghidra, radare2, AFL++, Frida, objection, jadx, apktool, MobSF —
full list and licenses at each project's own repository, linked from
`references/local-tooling.md`. None of their code is included here; Sieve only teaches an agent how
to drive them and how to read their output.
