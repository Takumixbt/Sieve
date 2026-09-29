# Binary / mobile — pack-specific gate additions

Read after `references/judging.md`.

## Do Not Report — binary/mobile-specific

- A crash with no sanitizer and no manual trace of the actual corruption — "it segfaults" alone is
  a LEAD, not a finding; `memory-safety-agent`'s proof oracle requires the provenance trace.
- Root/jailbreak detection or anti-tampering bypassed via Frida is worth documenting, but treat it
  at the severity the program's own policy states for that class — many programs explicitly scope
  this as low/informational since it requires a rooted device the victim chose to create.
- A theoretical primitive with no demonstrated crash or control — `exploit-primitive-agent` requires
  an actual debugger/exploit-script transcript, not a plausible-sounding chain.
- Anti-debugging or obfuscation presence alone, with no bypass demonstrated and no vulnerability it
  was hiding.

## Calibration note

`checksec`'s mitigation report changes what "impact" means: a stack overflow behind a working
canary, PIE, and NX is a DoS finding until an info-leak or a bypass is demonstrated — do not claim
full RCE severity without `exploit-primitive-agent`'s proof that the mitigations were actually
cleared.
