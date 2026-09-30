Write the **threat model** for this engagement. It is the first reasoning artifact of the campaign and everything downstream
(goals, invariants, strategies, the hunt) is anchored to it, so it must be specific to *this* system - a threat model that
would fit any application is a failed one.

## Ask, and answer from the x-ray and the code

- **Assets.** What is worth taking or breaking here, and why does it matter (funds, accounts, keys, data, uptime, reputation)?
  Name the concrete object: the vault, the session store, the signing key, the update channel.
- **Actors.** Who can touch the system and with what privilege: anonymous, ordinary user, another tenant, privileged role,
  admin, an external contract, a validator or keeper, an oracle, an insider. What does each *want*?
- **Trust boundaries.** Where does control or data cross from a less-trusted place to a more-trusted one, and what enforces
  the crossing? A boundary with no named control is where the first attack goals come from.
- **Attack goals.** At least three, each stated as a concrete end state an attacker wants ("move the whole vault balance to
  an address I choose", "read another tenant's invoices", "execute code in the update service"), with the actor, the asset
  and the preconditions. Do not write a goal the scope card excludes.
- **Assumptions.** What must be true for the design to be safe (an honest owner key, a live oracle, an authenticated
  gateway)? Each is a place to attack - write them down so the hunt can try to make them false.

## How to think

- Start from the attacker's profit, not from the code's shape (`hypothesis-craft.md` §3, "backward from value").
- Use the precedents (`xray/precedents.md`) and your own lessons: what broke systems of this type before?
- Prefer goals a *different* lens would not naturally reach. The roster covers the classics; this is where the odd,
  system-specific ideas begin.
- Anything you could not verify is an assumption, not a fact - say so.
