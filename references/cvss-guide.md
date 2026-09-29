# CVSS guide — scoring web and binary findings (CVSS 3.1)

Web3 findings use `severity` directly (critical/high/medium/low), calibrated by `judging.md`'s
gates and the deepen loop's blast-radius reasoning — CVSS's network/local vector model doesn't map
well onto "this drains the vault via a flash loan." Web and binary findings get a CVSS 3.1 vector;
apply it by reasoning through each metric against the finding's actual, gated (not hypothetical)
impact — there is no calculator script here on purpose: the input to CVSS is a judgment call about
*this* finding, and a script that took shortcuts on that judgment would just move the inflation
risk `judging.md` Gate 5 exists to catch into a different file.

## Base metrics, one line each

- **AV (Attack Vector)** — Network (over the internet) / Adjacent (same LAN/subnet) / Local
  (requires local access) / Physical (requires touching the device).
- **AC (Attack Complexity)** — Low (reliable, no special conditions) / High (needs a race window, a
  specific configuration, or information not normally available).
- **PR (Privileges Required)** — None / Low (a normal authenticated user) / High (an admin role).
- **UI (User Interaction)** — None / Required (a victim must click/open something).
- **S (Scope)** — Unchanged (impact stays within the vulnerable component's security authority) /
  Changed (impact crosses into a different security authority — e.g., a browser sandbox escape, a
  container breakout).
- **C/I/A (Confidentiality/Integrity/Availability)** — None / Low (limited exposure or
  modification) / High (total exposure, arbitrary modification, or full denial).

## Calibration against `judging.md`

- A finding that only clears Gate 3 with a **named admin amplifier** (race/retroactive-sweep/
  asymmetric-formula/access-gap) usually means PR should be **Low**, not None — the amplifier is
  what makes it exploitable by an unprivileged actor at all; score the amplified path, not the raw
  admin action.
- A finding DEMOTED at Gate 5 to "bounded, non-compounding impact" should show that as C/I/A
  **Low**, not High — the CVSS score and the gate's severity adjustment must agree, or one of them
  is wrong.
- **Never let the CVSS vector and the finding's stated severity disagree.** If the vector computes
  to a lower band than the severity you wrote, recheck the gate adjustments in `judging.md` before
  publishing either number — this is the same discipline as the "never inflate to hit a payout
  tier" rule, applied to the score instead of the label.

## Worked example

A stored XSS in an authenticated admin panel, requiring the victim to view a specific page an
attacker can get linked to, no special conditions:

```
AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N  → CVSS 3.1 Base Score: 6.4 (Medium)
```

`S:C` because the payload executes in the admin's browser session — a different security context
than the unauthenticated attacker who planted it — not because it "sounds severe."

## Where to compute the final number

Use any standard CVSS 3.1 calculator (FIRST.org's reference calculator, or the one built into the
target platform's submission form) once you've reasoned through the vector by hand. The reasoning
above is what prevents garbage-in on that calculator; the arithmetic itself is standardized and not
worth re-implementing.
