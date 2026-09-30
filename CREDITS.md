# Credits

Where this skill's method or code was shaped by outside work, it's recorded here - once, in one
place - rather than scattered through the working reference files.

## Methodology lineage

The three-tool reading discipline in `references/methodology.md` (explain-in-plain-language first,
then interrogate every assumption, then invert the check) and the sequential-gate shape of
`references/judging.md` draw on established audit practice in the smart-contract security
community, most directly [Pashov Audit Group's public skills](https://github.com/pashov/skills)
(MIT). `scripts/generate_svg.py` is vendored from that same source, MIT-licensed; its required
license notice is preserved in the file's own header.

## Design lineage

The campaign's shape (a topology of prompts and checked hand-offs, independent invariant lenses merged, a dynamic strategy
node, a triage panel) follows the public design of [monad-developers/ultrafuzz](https://github.com/monad-developers/ultrafuzz)
(MIT). Sieve's engine, verdict rules and everything else in this repository are its own code.

## Knowledge base

[Cyfrin / Solodit](https://solodit.cyfrin.io) - the web3 precedent database `references/knowledge.md`
and `sieve kb search --online` are built around. [OSV.dev](https://osv.dev) - the dependency
vulnerability lookup behind `sieve kb osv`, no key required.

## Public datasets behind `sieve kb ingest`

Fetched on demand into the local index, never redistributed by this repository: [DeFiHackLabs](https://github.com/SunWeb3Sec/DeFiHackLabs)
(Apache-2.0), [kadenzipfel/smart-contract-vulnerabilities](https://github.com/kadenzipfel/smart-contract-vulnerabilities) (MIT),
[Code4rena findings repositories](https://github.com/code-423n4), [reddelexc/hackerone-reports](https://github.com/reddelexc/hackerone-reports)
(a community list of public disclosures), [PayloadsAllTheThings](https://github.com/swisskyrepo/PayloadsAllTheThings) (MIT),
[CISA Known Exploited Vulnerabilities](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) (US public domain),
[Exploit-DB](https://gitlab.com/exploit-database/exploitdb) (titles only) and [OSV](https://osv.dev) bulk data (CC-BY-4.0).
`sieve kb sources` prints each one's licence.

## Browser

[CloakBrowser](https://github.com/CloakHQ/CloakBrowser) drives the `browser-recon` node through its Playwright-compatible API.
It is installed by the operator (`pip install cloakbrowser`) under its own licence.

## Tools this skill drives but does not vendor

Every tool named in `references/local-tooling.md` (Burp Suite and its extensions, the
ProjectDiscovery toolchain, Slither, Aderyn, Foundry, Echidna, Medusa, Ghidra, radare2, Frida, and
the rest) is the operator's own install, under its own license, linked from that file. None of
their code is included here - this skill only teaches an agent how to drive them and how to read
what they produce.
