---
id: KB-WEB-seed01
title: "Example - IDOR via an unguarded sibling verb"
source: seed
source_ref: "kb/README.md"
domain: web
class: idor
vector: WEB-IDOR-01
severity: high
stack: express/rest
tell: 'findById\(req\.params\.\w+\)'
status: seed
tags: [idor, authorization, sibling-rule]
first_seen: "2026-09-29"
---

# Example - IDOR via an unguarded sibling verb

Shipped example illustrating the card schema. See `packs/web/vectors/authz-and-idor.md`
(`WEB-IDOR-01`) for the live vector card, and `packs/web/agents/access-control-agent.md` for the
full sibling-rule method.

## Root cause
`GET /resource/:id` checks the caller owns the resource; the sibling `PATCH /resource/:id`, added
later by a different contributor, calls the same data-access helper directly and never re-applies
the ownership check.

## Attack path
An authenticated attacker with no relationship to the target resource sends `PATCH
/resource/<victim-id>` with an arbitrary body and the update succeeds against the victim's data.

## Fix
Move the ownership check into the shared data-access layer both routes call, so no future sibling
route can be added without it, rather than re-adding the same check per route.
