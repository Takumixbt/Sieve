# 2026 incident patterns

Every card below traces to a real, named, dated 2026 incident or disclosed research finding —
not a hypothetical. See `references/methodology.md`'s "mindset from 2026 incidents" section for
the researcher-framing lessons these were distilled from; the `kb:` line on each card is a starting
search, not a citation — verify current relevance against `sieve kb search --online` before relying
on a card's age alone.

## HTTP smuggling

### WEB-SMUGGLE-01 · Shared-parser desync (connection-reuse confusion)
- signal: front-end and back-end (or CDN and origin) run the *same* HTTP parser library/version, connection reuse / keep-alive is enabled across a proxy chain, and no strict-parsing / normalization layer sits between hops
- attack: send a request whose framing is ambiguous only under specific connection-state conditions (not classic CL.TE/TE.CL header disagreement) — probe with malformed chunk extensions, pipelined requests exploiting reuse timing, and RFC-edge-case framing; confirm smuggling by observing a subsequent, unrelated request on the same backend connection getting corrupted
- proof: two independent client requests on a shared connection where request B's response contains content addressed to request A (or vice versa), reproduced deterministically outside the app's own logs (Burp Turbo Intruder / a raw-socket harness), not merely "the app behaved oddly once"
- fp: transient network jitter or connection-pool exhaustion under load can look like response mis-association; require reproducibility across ≥3 independent trials before calling it smuggling
- sev: Critical
- cwe: CWE-444
- kb: HTTP request smuggling shared parser desync 2026 HTTP Terminator

## GraphQL federation

### WEB-GRAPHQL-01 · Federation directive-inheritance authorization gap
- signal: schema defines authorization directives (`@authenticated`, `@requiresScopes`, custom `@policy`) on a GraphQL *interface* type rather than repeating them on every concrete implementing type
- attack: query the protected field through a concrete type via an inline/named fragment (`... on ConcreteType { protectedField }`) instead of through the interface directly, bypassing the directive that was never inherited
- proof: an authenticated-low-privilege (or unauthenticated) request returns interface-protected field data when queried via the concrete type, while the same query via the bare interface is correctly rejected — side-by-side response diff is the proof
- fp: some federation gateways do propagate directives correctly by design (composition-time directive merging) — verify against the gateway's actual composed schema/introspection, not assumed behavior from a different runtime
- sev: High
- cwe: CWE-863
- kb: GraphQL federation interface directive authorization bypass Apollo

### WEB-GRAPHQL-02 · Blind federated sub-graph injection
- signal: a gateway federates multiple independently-owned/deployed subgraphs and trusts subgraph responses / entity-resolution metadata without per-subgraph output validation at the gateway boundary
- attack: craft a query that traverses entity references across subgraph boundaries into a subgraph the caller has no authorization for; when direct response inspection is blocked, infer leaked field values via timing/error-shape/entity-resolution side channels (blind exfiltration)
- proof: statistically significant, reproducible correlation between a boolean/timing oracle and a known-true fact about data the caller should not access — not a one-off timing blip
- fp: normal query-complexity-driven latency variance across different entity types can mimic a timing oracle; baseline latency distribution per query shape before claiming a channel exists
- sev: High
- cwe: CWE-200
- kb: federated GraphQL blind subgraph injection data leak

## Cache poisoning

### WEB-CACHE-03 · Cache-key injection via unseparated concatenation
- signal: `proxy_cache_key` (or equivalent CDN cache-key config) concatenates multiple request-derived values (scheme, host, URI, headers) without explicit delimiters between them
- attack: craft a request whose components, once concatenated without separators, collide with the cache key of a different, sensitive request (shift characters across a component boundary — `/h` + `Accept: ome*/*` colliding with `/home` + `Accept: */*`); confirm restricted/sensitive content is served from a cache entry populated by the attacker's crafted request
- proof: attacker-triggered cache entry is subsequently served to a victim (or to the attacker requesting the "legitimate" URL) containing attacker-influenced content — capture both requests/responses and the shared cache key
- fp: CDN-level cache normalization (many providers canonicalize before hashing) can make an origin-level PoC non-reproducible at the edge — test at the actual caching layer in production topology, not just against origin config directly
- sev: High
- cwe: CWE-444
- kb: cache key injection unseparated concatenation Nginx 2026

### WEB-CACHE-04 · Scheme-confusion cache poisoning to stored XSS
- signal: cache key begins with `$scheme$host...` (or equivalent) and the backend reflects the `Host` header into a script-src, canonical URL, or other executable/DOM-sink context
- attack: send an HTTP (not HTTPS) request with a crafted `Host` header whose trailing bytes complete the string `https`, producing a cache key collision with a real HTTPS request; if the backend reflects the attacker's `Host` into a script tag's `src`, the poisoned cache entry now serves JS from an attacker-controlled domain to every subsequent visitor of the legitimate HTTPS URL
- proof: a request to the legitimate HTTPS URL, made from a clean client with no prior state, returns a response referencing the attacker's domain — screenshot/HAR capture plus the two colliding raw requests
- fp: many deployments force scheme normalization (HSTS + redirect-before-cache) that closes this off; confirm the origin/CDN actually caches on the raw incoming scheme before treating this as exploitable
- sev: Critical
- cwe: CWE-79
- kb: web cache poisoning scheme confusion stored XSS

## CI/CD supply chain

### WEB-CICD-01 · pull_request_target cache-poisoning to OIDC token theft
- signal: a workflow triggers on `pull_request_target` (or `workflow_run`) and either (a) checks out fork PR code before restricting permissions, or (b) restores an Actions cache keyed in a way a fork PR run can also populate
- attack: submit a PR from a fork that populates the shared Actions cache (a poisoned package-manager store) during its own `pull_request_target`-triggered run; wait for a legitimate maintainer workflow (on push/merge, elevated `GITHUB_TOKEN`/OIDC scope) to restore that same cache key and execute the planted binary, exfiltrating OIDC tokens from the runner's process memory
- proof: a controlled reproduction (in a disposable throwaway repo, never the real target) showing cache-key collision between a fork-PR-triggered job and a base-repo-triggered job, with a benign canary payload proving code execution in the elevated context — never actually exfiltrate real tokens against a live target
- fp: many orgs pin cache keys to a hash of the lockfile plus the base ref, which closes the collision — verify the actual cache key expression in the workflow YAML, don't assume the vulnerable pattern applies verbatim
- sev: Critical
- cwe: CWE-284
- kb: pull_request_target GitHub Actions cache poisoning OIDC theft TanStack

### WEB-CICD-02 · Stale credential enabling mass git-tag mutation
- signal: an organization publishes GitHub Actions / reusable workflows referenced by version *tag* (not pinned SHA) by downstream consumers, and credential rotation after a prior incident is not verifiably complete
- attack: use a still-valid credential to force-push new commits onto existing released version tags of a widely-consumed action, injecting malicious code that every consumer pinned to that tag will pull on their next run
- proof: a tag's underlying commit SHA differs from the SHA originally associated with that tag at release time (compare against GitHub's own audit log, an SBOM snapshot, or a third-party mirror taken before the mutation)
- fp: legitimate maintainers occasionally do re-tag (fixing a same-day typo) — corroborate with out-of-band signals (unexplained new outbound domains in the diff, credential-harvesting patterns) before calling it compromise
- sev: Critical
- cwe: CWE-494
- kb: GitHub Action tag mutation supply chain force push stale credential

## SAML / SSO

### WEB-SAML-01 · XML parser differential producing a signature/assertion desync
- signal: the SAML SP uses one XML library/config path to validate the signature and a different one (or the same library with different canonicalization settings) to extract the asserted identity
- attack: construct a SAML response where attribute pollution, namespace confusion, or void canonicalization causes the signature-validating parser to see a legitimate signed document while the assertion-processing parser extracts attacker-controlled identity claims from a different logical reading of the same bytes
- proof: log in as an arbitrary user (an admin whose NameID you forged) using a SAML response whose signature validates against the IdP's real certificate — a live authenticated session as a victim account you do not control is the strongest proof
- fp: many SPs additionally check assertion `InResponseTo`/timestamp/audience restrictions correctly even when canonicalization is fragile — a parser differential alone is not proof of exploitability until it survives every other SP-side check
- sev: Critical
- cwe: CWE-347
- kb: SAML XML canonicalization parser differential auth bypass fragile lock

### WEB-SAML-02 · Decoupled signature verification across response/assertion/source config
- signal: SSO/IdP integration config allows verifying the assertion signature while leaving the top-level response signature (or vice versa) unchecked, or allows configuring a SAML source with no encryption certificate at all
- attack: submit a SAML response with a validly-signed assertion but an unsigned/differently-signed wrapping response element (or an assertion the SP never checks is actually encrypted when it's supposed to be), smuggling attacker-controlled claims past whichever check the SP actually enforces
- proof: successful authentication as a victim identity using a response that intentionally fails one of the two signature checks but is still accepted — capture the raw SAML XML and the resulting authenticated session
- fp: SP-initiated flows with strict `InResponseTo` binding can close this even when signature checks are individually decoupled — test both SP-initiated and IdP-initiated flows, since many bypasses only work on the latter
- sev: Critical
- cwe: CWE-347
- kb: SAML decoupled signature verification response assertion bypass

## WebSocket

### WEB-WS-01 · Cross-Site WebSocket Hijacking (CSWSH) via missing Origin check
- signal: a WebSocket server (especially local dev tooling, admin panels, or internal dashboards) performs no `Origin` header validation during the WS upgrade handshake, and the WS channel carries session-authenticated, sensitive data
- attack: host a page that opens a WebSocket connection to the target's default port from a victim's browser while the victim is authenticated (or, for local-only services, simply while the victim has the service running); read the live data stream cross-origin, since WebSocket — unlike `fetch`/XHR — is not subject to the same-origin policy by default
- proof: a PoC HTML page hosted on an unrelated origin that successfully opens the WS connection and displays victim data live in the browser console/DOM — the browser's own network tab showing the cross-origin WS connection succeed is sufficient
- fp: some WS servers rely on a separate token in the first message (not the Origin header) for authorization — confirm the data actually returned is sensitive and that no secondary auth check silently blocks it
- sev: High
- cwe: CWE-346
- kb: cross-site websocket hijacking CSWSH origin validation

### WEB-WS-02 · Protocol-upgrade-specific SSRF via malformed absolute-form URI
- signal: reverse proxy / app framework has a separate code path for routing WebSocket upgrade requests versus normal HTTP requests, and the upgrade path performs less/different URL normalization or completion-flag checking than the HTTP path
- attack: send a raw request with a malformed absolute-form URI (triple-slash `http:///...`) combined with WebSocket upgrade headers (`Connection: Upgrade`, `Sec-WebSocket-Key`); if URL-normalization logic strips the hostname before the proxy layer applies its default target, the request lands on `localhost` and reaches co-located internal services
- proof: response content from a known-internal-only endpoint (cloud IMDS, localhost admin panel banner) returned to the external attacker-controlled connection — redact any real credentials captured and report via responsible disclosure rather than exfiltrating them
- fp: managed/PaaS-hosted deployments of the same framework often front the app with a separate, hardened ingress proxy that never exposes this code path externally — confirm self-hosted topology before treating this as exploitable
- sev: Critical
- cwe: CWE-918
- kb: WebSocket upgrade SSRF absolute URI normalization localhost Next.js

## AI-accelerated attack development

### WEB-CHAIN-01 · AI-accelerated exploit-chain compression
- signal: target has independently-low-severity findings (an image-processing flaw, a minor auth-flow quirk) that individually would not be prioritized, but which touch adjacent trust boundaries
- attack: use an agentic LLM with tool access (code execution, HTTP request crafting, iterative exploit refinement) to rapidly hypothesize and test chains linking two-or-more individually-modest bugs into a full account-takeover — what previously took a human researcher days of manual pivoting, an agentic loop can iterate in hours
- proof: an end-to-end, reproducible chain from the initial low-severity bug to a fully authenticated session as a victim account, with every intermediate step's request/response captured — chain diagrams alone, without raw traffic, are not sufficient proof
- fp: agentic tooling can produce plausible-looking multi-step chains in its reasoning trace that don't actually work end-to-end when replayed manually — always manually replay the full chain outside the agent's own harness before reporting it as proven
- sev: Critical
- cwe: CWE-284
- kb: chained vulnerabilities account takeover AI-assisted exploit development 2026
