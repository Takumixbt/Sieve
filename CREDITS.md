# Credits

Where this skill's method or code was shaped by outside work, it's recorded here — once, in one
place — rather than scattered through the working reference files.

## Methodology lineage

The three-tool reading discipline in `references/methodology.md` (explain-in-plain-language first,
then interrogate every assumption, then invert the check) and the sequential-gate shape of
`references/judging.md` draw on established audit practice in the smart-contract security
community, most directly [Pashov Audit Group's public skills](https://github.com/pashov/skills)
(MIT). `scripts/generate_svg.py` is vendored from that same source, MIT-licensed; its required
license notice is preserved in the file's own header.

## Knowledge base

[Cyfrin / Solodit](https://solodit.cyfrin.io) — the web3 precedent database `references/knowledge.md`
and `sieve kb search --online` are built around. [OSV.dev](https://osv.dev) — the dependency
vulnerability lookup behind `sieve kb osv`, no key required.

## Tools this skill drives but does not vendor

Every tool named in `references/local-tooling.md` (Burp Suite and its extensions, the
ProjectDiscovery toolchain, Slither, Aderyn, Foundry, Echidna, Medusa, Ghidra, radare2, Frida, and
the rest) is the operator's own install, under its own license, linked from that file. None of
their code is included here — this skill only teaches an agent how to drive them and how to read
what they produce.
