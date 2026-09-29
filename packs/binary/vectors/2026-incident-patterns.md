# 2026 incident patterns

Every card below traces to a real, named, dated 2026 CVE, Pwn2Own result, or disclosed incident —
not a hypothetical. 2026's dominant pattern, confirmed across Pwn2Own Berlin's Edge/Exchange results
and the MikroTrick chain: **chains of small, individually-unremarkable logic bugs are displacing
single big memory-corruption bugs at the top tier**, as CFI/sandboxing/PAC/hardened allocators raise
the cost of a single memory-safety bug reaching code execution. A severity model that scores each
finding in isolation systematically under-rates exactly the bug chains winning real contests in 2026.
See `references/methodology.md`'s "mindset from 2026 incidents" section for the full framing lessons.

## Browser / JS engine

### BIN-JIT-ELEMKIND-01 · JS-engine JIT elements-kind / hidden-class confusion
- signal: target embeds a JS engine (V8/JSC/SpiderMonkey) or JIT with speculative array/object "shape"/"elements kind"/"hidden class" optimization; recent CVE history for the engine shows repeated type-confusion (CWE-843) fixes in the optimizing compiler (TurboFan/Maglev/DFG/FTL/IonMonkey)
- attack: construct a JS object/array, force it through an optimized function with a stable elements-kind assumption baked in by the JIT (repeated calls to warm up a type feedback slot), then mutate the object's backing store/elements-kind via a side path (array length change, a transition to a different element representation, a Proxy trap, an accessor defined mid-iteration) so the optimized code's cached type assumption no longer matches the object's real representation; trigger the optimized code path again to get a type-confused read/write, then pivot that into an addrof/fakeobj primitive
- proof: a JS PoC that reliably reproduces a type-confused arbitrary read/write in a debug build (crash under ASan, or a controlled read of adjacent heap memory printed back to the page); ideally with the specific elements-kind/shape transition documented and reproduced under a release build with only standard flags
- fp: an engine crash under a fuzzer is not automatically a security bug — many "type confusion" crashes in JIT fuzzing are actually already-mitigated by a runtime deopt/bailout check; confirm the type-confused access actually reaches attacker-influenced memory before triaging as a real finding
- sev: Critical
- cwe: CWE-843
- kb: v8 elements kind confusion inline cache OR turbofan type confusion exploit writeup

### BIN-GPU-RES-UAF-01 · GPU/WebGPU/graphics-library resource-lifecycle UAF
- signal: target exposes a GPU compute/graphics API (WebGPU/Dawn, Vulkan, Metal, a GPU-passthrough container layer) where resource objects (buffers, textures, command encoders) are created/submitted/destroyed across a process or IPC boundary
- attack: rapidly create, submit, and destroy GPU resource objects in tight loops from the less-trusted side of the boundary (a renderer or guest), racing the resource's destruction against its continued use by the more-trusted side (GPU process/host), then reallocate memory of the same size/class to land attacker-controlled data on the freed slot and corrupt a vtable/function-pointer or object-header field
- proof: reproducible crash showing use of a freed GPU resource object with attacker-controlled content in the freed slot (heap-buffer-overflow/UAF report under ASan/HWASan, or a controlled crash at an attacker-influenced instruction pointer/vtable call)
- fp: a benign UAF that only corrupts already-torn-down, non-attacker-reachable state (a logging object) is not exploitable — confirm the freed object's memory is actually reused by something the attacker controls the content of, not just that it's freed early
- sev: Critical
- cwe: CWE-416
- kb: webgpu dawn use-after-free gpu process sandbox escape

### BIN-CSS-NONJS-UAF-01 · Non-JS-engine memory-safety bug (CSS/layout/style engine)
- signal: target is a browser or embedded-webview component; audit attention has historically concentrated on the JS engine, leaving CSS/style/layout engine data structures (value maps, at-rule parsers, animation/transition state machines) comparatively unfuzzed relative to their complexity and C++ object-graph density
- attack: identify CSS features backed by non-trivial C++ container/map structures (at-rule value maps, custom-property registries, container-query/animation state), then look for iterator invalidation: mutate the underlying container (redefine a `@font-feature-values` block, trigger a style recalculation) while an iterator over it is still live in a code path reachable from script (a callback fired mid-iteration, a getter, a MutationObserver)
- proof: a crafted HTML/CSS page that deterministically triggers a use-after-free/iterator invalidation crash under ASan in the style/layout engine, independent of any JS engine bug
- fp: many CSS-engine "crashes" found by naive fuzzing are OOM/recursion-limit/assertion failures with no security impact — confirm the crash is a genuine memory-safety violation (ASan heap-UAF, not a hardened `CHECK`/`DCHECK` abort)
- sev: High
- cwe: CWE-416
- kb: css engine iterator invalidation use-after-free non-v8 browser bug

## Mobile / kernel EoP

### MOBILE-GPU-DRV-EOP-01 · Vendor GPU/graphics kernel driver EoP (chained second stage)
- signal: target is a mobile device or embedded Linux system using a third-party GPU driver (Qualcomm Adreno, ARM Mali, Imagination PowerVR) shipped as a vendor binary blob or slow-to-patch out-of-tree kernel module
- attack: from an already-sandboxed/unprivileged local context (a compromised renderer or installed app), invoke the GPU driver's ioctl surface with crafted buffer-size/command-stream parameters designed to trigger an integer overflow/wraparound in size or offset calculations, producing an undersized kernel allocation later written past its bounds by subsequent GPU command processing
- proof: a local PoC (app or sandboxed process) that triggers kernel memory corruption via the GPU driver ioctl path, ideally with KASAN confirmation of an out-of-bounds or overflow condition tied to a specific ioctl and parameter
- fp: a GPU driver crash reachable only from a *privileged* context (already requires root/system_server access) is not a genuine EoP primitive — confirm the ioctl is reachable from the actual sandboxed/untrusted caller, not just the shell/root user used during local testing
- sev: High
- cwe: CWE-190
- kb: qualcomm adreno kernel driver integer overflow privilege escalation android

### MOBILE-PARSER-ZEROCLICK-01 · Auto-processed message/attachment parser zero-click chain
- signal: target is a messaging app or OS component that automatically parses attachments/rich content with no user interaction (iMessage, RCS, push-notification preview rendering, image thumbnailing services); check whether any such auto-processing path runs outside a dedicated hardened sandbox (something like BlastDoor) or whether that sandbox itself has a history of being bypassed
- attack: identify a rich-content/attachment format parsed automatically pre-user-interaction (image codec, font renderer, document previewer); fuzz or manually review that specific parser for memory corruption, then chain a corruption primitive there with (a) a sandbox-escape bug out of the dedicated content-processing sandbox and (b) on modern ARM targets, a PAC-bypass or PAC-forging primitive (commonly built from a separate info-leak or a JOP gadget chain that avoids needing to forge a signature by reusing already-signed pointers)
- proof: end-to-end chain demonstrated to achieve code execution from message/attachment delivery alone, with zero user interaction, ideally instrumented to show each stage (parser corruption, sandbox escape, PAC bypass if applicable) independently
- fp: a parser crash found via fuzzing that only reproduces with a debugger attached or requires a non-default OS/app configuration is not evidence of a real zero-click primitive — confirm reachability via the actual default auto-processing path, not a direct harness call with attacker-controlled setup the real pipeline would never allow
- sev: Critical
- cwe: CWE-787
- kb: imessage zero-click blastdoor sandbox bypass pointer authentication forgery

## Auth / credential comparison

### BIN-AUTHKEY-INCOMPLETE-CMP-01 · Incomplete public-key/credential comparison auth bypass
- signal: any authentication scheme that "compares a public key" (SSH host/user key auth, mTLS client cert pinning, JWT/JWK public-key matching, signed-URL verification) — check whether the comparison logic actually compares every structural component of the key/credential (for RSA: modulus AND exponent; for a cert: full DN/SAN/key material, not just a cached fingerprint field) or only a subset used as a lookup/matching key
- attack: obtain or derive a partial component of an authorized credential that is not secret (an RSA public modulus, by definition public, vs. the private exponent); construct a new, attacker-controlled credential (a keypair with exponent=1) that matches on every component the target's comparison logic actually checks but differs on a component it silently ignores; use that attacker-controlled credential (for which the attacker does hold the matching private key) to complete authentication as the victim identity
- proof: a working authentication as a victim identity performed using a credential the attacker legitimately generated (not stolen), demonstrating the target's matching logic accepted a different, attacker-forged key/cert differing from the authorized one in a component that was never actually compared
- fp: confirm the "matched but different" credential truly was not the authorized one bit-for-bit — if the target normalizes/canonicalizes the credential before comparison (recomputing exponent from a stored default), the comparison may be complete in practice even if the code reads as checking only part of the structure
- sev: Critical
- cwe: CWE-347
- kb: ssh public key auth incomplete rsa comparison modulus exponent bypass MikroTrick

## Composed logic chains

### BIN-CHAIN-LOGIC-SBXESC-01 · Multi-bug pure-logic sandbox/permission-boundary escape
- signal: target has a well-hardened memory-safety posture (site isolation, CFI, hardened allocator, no recent memory-corruption CVEs) but exposes multiple independently-low-severity logic/permission findings (an IPC message the sandboxed process shouldn't be able to send but can; a permission check present on one code path but missing on an equivalent alternate path; a state transition reachable out of order) — treat a cluster of such findings as a composition candidate rather than closing each as "Low, no direct impact standalone"
- attack: map every sandboxed-process-to-broker/host IPC message and every permission/state check gating a privileged operation; for each, test not just "is the check present" but "is the check present on every code path that reaches this operation, including less-obvious ones (error-handling paths, out-of-order re-entrant calls, alternate API entry points)"; then attempt to compose 2-4 such gaps into a sequence that starts from confirmed sandboxed code and ends outside the sandbox boundary, exactly as a memory-corruption chain would compose an info-leak + a corruption bug
- proof: an end-to-end PoC starting from the actual sandboxed execution context (not a privileged test harness) that demonstrates code execution or state modification outside the intended sandbox boundary, using only the composed logic bugs — no memory corruption required
- fp: an individual missing-permission-check finding that is real but requires an already-privileged starting point to reach is not evidence of a sandbox escape — every step of the chain must be reachable starting from the actual untrusted/sandboxed entry point
- sev: Critical
- cwe: CWE-284
- kb: browser sandbox escape logic bug chain no memory corruption ipc permission Pwn2Own

### BIN-SHELLOUT-ARITH-01 · Command injection via shell arithmetic-expansion / RewriteMap-style external script
- signal: target's web/app server invokes an external shell script or interpreter for a subsidiary function (Apache mod_rewrite RewriteMap programs, a "helper script" called via popen/exec, a webhook handler shelling out) — look at the external script's own input handling, not just the calling application's validation, since input that already passed app-layer validation is often wrongly treated as pre-sanitized by the time it reaches the helper script
- attack: identify an HTTP parameter or other attacker-controlled value that flows into the external script's invocation; within that script, look specifically for Bash arithmetic-expansion contexts (`$(( ... ))`, `let`, array-index expressions) as a second, easily missed injection surface distinct from the obvious backtick/`$()`/`eval` patterns; craft a value that, when the shell evaluates it as an arithmetic expression, contains a command-substitution subexpression the shell will execute as a side effect of arithmetic evaluation
- proof: a crafted HTTP request that results in attacker-chosen OS command execution on the target host, with the request/response and resulting command output captured as evidence
- fp: many arithmetic-expansion code paths only accept values already constrained to be numeric by an earlier regex/type check in the calling application — confirm the actual end-to-end data flow, not just that the pattern exists in the script, before treating it as exploitable
- sev: Critical
- cwe: CWE-78
- kb: apache rewritemap bash arithmetic expansion command injection pre-auth rce Ivanti EPMM

## Physical / protocol-layer input

### IOT-EVCHARGE-SIGNAL-01 · EV charging-protocol / power-line signal manipulation injection
- signal: target is an EV charger, battery-management system, or any device that negotiates session parameters over a domain-specific physical/electrical protocol (SAE J1772/CCS pilot-signal PWM, ISO 15118 power-line communication, OCPP over the charger's backend link) or accepts NFC "tap to authenticate" input — a network-only vulnerability scan will never touch these
- attack: build or adapt hardware capable of manipulating the pilot/control-pilot signal timing, duty cycle, or PLC data stream outside protocol-legal bounds (or, for NFC auth, craft a malformed/oversized NFC tag payload), and observe how the charger's embedded firmware parses and reacts to out-of-spec or malformed signal/tag data — target the firmware's session-negotiation and command-injection-prone logging/telemetry-string handling specifically
- proof: a demonstrated firmware-level effect (command execution, persistent state change, denial of charging service, unauthorized free charging) achieved purely through electrical signal/PLC manipulation or a crafted NFC tag, with no network-layer access used
- fp: a signal-manipulation "anomaly" that only causes the charger to fault safely into a documented error state (no code-execution or auth-bypass consequence) is a robustness finding, not a security vulnerability — confirm actual unauthorized command execution, billing bypass, or persistent compromise
- sev: High
- cwe: CWE-20
- kb: ev charger ccs pilot signal manipulation command injection nfc firmware Pwn2Own Automotive

## AI agent / orchestration trust boundaries

### AGENT-SANDBOX-STARTUP-RACE-01 · Sandbox-enforcement-timing gap via agent/process startup file
- signal: target is (or embeds) an AI coding agent, CLI tool, or any sandboxed process launcher where a new subprocess is spawned and wrapped in a sandbox profile (seatbelt, AppArmor, Landlock, a container entrypoint) — check specifically whether the shell/interpreter being launched has its own startup-time file-read behavior (rc files, env files, dynamic-linker preload config) that could execute or load attacker-influenced content
- attack: identify any file read automatically during new-process startup for the shell/interpreter the agent uses (`~/.zshenv`, `~/.bashrc` for non-interactive-but-sourced shells, `LD_PRELOAD`-style config, a language runtime's auto-loaded init file) that is writable by the sandboxed process itself or reachable via an earlier stage of the same attack chain; if the sandbox profile is only attached to the process after the OS has already begun executing that startup file, plant a payload there and trigger the next process launch to execute it unsandboxed
- proof: a reproduction showing attacker-controlled code executing without the sandbox's restrictions being enforced, specifically by exploiting the ordering between "process launched" and "sandbox profile active," with the triggering tool call/context shown to have been made from within the intended sandbox
- fp: confirm the payload genuinely runs unsandboxed (performs an action the sandbox profile would otherwise block, such as writing outside the allowed directory or making network connections the profile denies) rather than merely running early — some startup files are sourced but still under active sandbox enforcement on some platforms, which would not be a genuine bypass
- sev: Critical
- cwe: CWE-829
- kb: seatbelt sandbox zshenv startup race agent prompt injection sandbox escape Claude Code worktree

### AGENT-TRUST-BOUNDARY-TOOLCALL-01 · AI agent/orchestration trust-boundary RCE (tool-call / model-output revalidation)
- signal: target embeds or orchestrates calls to an LLM, agent runtime, MCP-style tool server, or model-serving backend (LiteLLM, Ollama, LM Studio, a custom agent harness, a coding-agent CLI) — look at how the product handles output coming back from a tool call, a plugin, a downstream model API response, or a loaded model/config file, and whether that output is treated as trusted once it crosses back into the orchestrating product
- attack: identify a tool/plugin/model-file/API-response path whose content the orchestrating product does not revalidate before acting on it (a model file that can specify config/execution parameters, a tool-call response deserialized without type/schema enforcement, an internal admin/proxy endpoint reachable via SSRF from a tool-call target URL the product will fetch); use that path to reach deserialization of attacker-controlled data, SSRF into an internal-only endpoint, or path traversal into a sensitive file, and chain that into code execution or credential/API-key exfiltration
- proof: demonstrated unauthorized code execution, credential/API-key exfiltration, or access to internal-only resources, triggered purely through the AI product's normal tool-call/model-loading/plugin interface — no direct network access to the underlying host required
- fp: an SSRF finding that can only reach other public internet hosts (not internal/localhost-bound services or cloud metadata endpoints) has much lower real impact — confirm what is actually reachable through the SSRF/trust-boundary gap before rating severity
- sev: Critical
- cwe: CWE-502
- kb: llm orchestration ssrf deserialization litellm ollama agent trust boundary rce Pwn2Own

## Build/registry supply chain

### SUPPLY-REGISTRY-CTRLPLANE-01 · Package/module registry control-plane hijack (DNS/API-credential compromise)
- signal: target's build, deployment, or environment-provisioning pipeline pulls packages/modules/images from a registry whose routing/DNS/CDN credentials (not just its package-signing keys) are a single point of trust — check who holds API keys for the registry's DNS provider/CDN and how those credentials are scoped, rotated, and monitored
- attack: (assessment framing) determine whether registry-infrastructure API credentials (DNS, CDN, load-balancer config) are as tightly scoped/monitored as the package-signing keys themselves; a compromise of the former lets an attacker silently redirect a subset of legitimate registry traffic to attacker-controlled infrastructure serving malicious package/module versions, without ever needing to compromise a maintainer account or break package signing
- proof: for an audit, proof consists of demonstrating that registry DNS/CDN-level credentials are broadly held, unmonitored, or insufficiently scoped relative to their blast radius — a credential-exposure/access-review finding, plus a demonstration (in a safe test registry) that a routing change of this kind would go undetected by existing monitoring
- fp: the mere existence of DNS/CDN admin access is not itself a finding if it's tightly scoped, MFA-protected, alert-monitored for unexpected record changes, and consistent with least-privilege — the finding is the absence of those controls, not the existence of the capability
- sev: Critical
- cwe: CWE-494
- kb: package registry dns cdn api key compromise malicious module supply chain Coder

### SUPPLY-WORM-PROPAGATE-01 · Self-propagating package-ecosystem credential-theft worm
- signal: an engagement's dependency tree includes packages from an ecosystem (npm, PyPI, etc.) with a recent history of automated mass-publish incidents; check CI/CD and developer-machine environments for unscoped, long-lived publish credentials, cloud keys, SSH keys, and Kubernetes secrets that would be harvestable by any compromised dependency's postinstall/import-time code
- attack: (assessment framing) evaluate whether a single compromised dependency's install-time or import-time code execution could reach and exfiltrate publish credentials for other packages the same identity maintains or has CI access to — that reachability is exactly what lets a worm self-propagate across an ecosystem once it lands on one machine/pipeline
- proof: demonstrate (in an isolated test environment) that a package's install/import-time hooks can read and would be able to exfiltrate the credentials/secrets present in a realistic CI or developer environment for this target, without those secrets being scoped, short-lived, or protected by hardware-backed/ephemeral-credential mechanisms
- fp: a dependency with install-time network access is not automatically a worm risk if the environment's real secrets are short-lived/scoped (OIDC-issued ephemeral tokens rather than long-lived static keys) — the finding is about credential exposure and scope, not the mere existence of a postinstall script
- sev: High
- cwe: CWE-506
- kb: npm pypi supply chain worm postinstall credential theft self propagating Shai-Hulud

## Virtualization / containers

### BIN-VIRT-CROSSTENANT-01 · Hypervisor guest-to-host escape with cross-tenant impact
- signal: target is a hypervisor (ESXi, KVM, Hyper-V, Xen) or any multi-tenant virtualization platform; scope should explicitly ask whether "guest-to-host code execution" is the ceiling of impact being tested, or whether cross-tenant impact (host-to-neighboring-guest) is also in scope, since these represent meaningfully different severities
- attack: starting from a guest VM, target the hypervisor's device-emulation layer (virtual NIC, virtual disk controller, virtual GPU/USB passthrough, balloon/paravirt drivers) for a corruption or logic bug that yields host-context code execution; once host-level execution is achieved, additionally attempt to reach and modify state belonging to a separate guest VM on the same host to demonstrate cross-tenant impact, not just host compromise
- proof: for guest-to-host, a PoC starting purely from inside the guest VM (no host-side assistance) achieving code execution in the host/hypervisor context; for cross-tenant, an additional PoC showing modification of a second, independently-provisioned guest VM's state from that host-level foothold
- fp: a device-emulation crash reachable only via a non-default/debug hypervisor configuration (a device only enabled by an administrator, not exposed to guests by default) overstates real-world risk — confirm the vulnerable device/feature is present in the platform's default, as-shipped guest configuration
- sev: Critical
- cwe: CWE-668
- kb: hypervisor guest to host escape cross tenant vm isolation bypass Pwn2Own ESXi

### BIN-GPU-CONTAINER-ESCAPE-01 · GPU-passthrough container-toolkit escape
- signal: target uses a container runtime with GPU passthrough (NVIDIA Container Toolkit or equivalent) to expose hardware acceleration to containerized workloads, common in ML training/inference deployments — check what device nodes, driver ioctls, and toolkit-managed mount/hook logic the container actually gets access to beyond the GPU compute path itself
- attack: from inside a container with GPU passthrough enabled, enumerate every device node, library, and hook script the toolkit mounts or invokes at container-start time (not just `/dev/nvidia*`); look for toolkit logic that runs with host privileges to set up the passthrough (mount namespace manipulation, dynamic library injection, ldconfig cache rebuilding) for a race condition, symlink-following, or insufficiently-scoped mount that lets a malicious container escape into the host mount/device namespace
- proof: a PoC container image that, when run with standard GPU-passthrough flags (no special privileges beyond what a normal GPU workload would request), achieves code execution or filesystem access on the host outside the container
- fp: an escape that requires the container to already be started with `--privileged` or an unusual non-default capability set is not evidence of a toolkit vulnerability — confirm the PoC works under the toolkit's documented/typical GPU-workload configuration
- sev: Critical
- cwe: CWE-668
- kb: nvidia container toolkit gpu passthrough escape host privilege Pwn2Own
