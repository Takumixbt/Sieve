# Web - pack-specific gate additions

Read after `references/judging.md`.

## Do Not Report - web-specific

- Self-XSS with no escalation path (no CSRF/clickjacking chain that gets the payload into a
  victim's session).
- Logout CSRF, and CSRF on any non-state-changing or already-unauthenticated action.
- Rate-limiting that genuinely prevents exploitation inside the program's stated threat model.
- Missing security headers with no demonstrated impact - cite the concrete attack the missing
  header enables, or it's a hardening note, not a finding.
- Anything requiring a physical or on-path (MITM) attacker position explicitly out of the program's
  scope.
- A CVE flagged by `sieve kb osv` in a dependency this application never actually calls into
  (`supply-chain-agent`'s reachability check) - an unreachable known-vulnerable function is a note,
  not a finding.
- A model "saying" something unsafe or refusing/complying with no tool call fired and no
  externally-observable side effect - a chat-transcript-only observation is a content-safety note,
  not an application-security finding (`ai-native-appsec-agent`'s proof-oracle discipline).

## Calibration note

A WAF or filter blocking your exact payload string is not proof the underlying sink is safe -
retest with encoding/case variation before concluding either way (`injection-agent`).
