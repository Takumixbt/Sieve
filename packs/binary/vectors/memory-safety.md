# Memory safety

### BIN-OOB-01 · Length field read from input, unchecked before use
- signal: a parser reads a size/length value from the input file/protocol and uses it directly in an allocation or copy with no upper-bound check against the actual buffer
- attack: craft input with a length field exceeding the real buffer size
- proof: crash under ASan with a precisely located heap/stack write past the allocated bound, plus the exact input file/bytes
- fp: a length field that IS bounds-checked against a `MAX_SIZE` constant before use is not this vector — confirm the check exists and actually covers this exact use, not a different field
- sev: critical when the write is attacker-controlled in content, not just location; high for a read-only OOB
- cwe: CWE-787 (write) / CWE-125 (read)
- kb: heap overflow stack overflow length field unchecked size parser

### BIN-UAF-01 · Object used after a callback frees it
- signal: a connection/object is freed on one code path (an error handler, a teardown routine) while a callback registered against it can still fire
- attack: trigger the free path, then trigger the callback (a delayed network event, a signal, a second thread) to use the freed object
- proof: crash under ASan showing a use-after-free on the exact freed address, with the trigger sequence (which two paths raced)
- fp: an object freed and then immediately set to NULL with every subsequent use guarded by a NULL check is not vulnerable — confirm the NULL check actually covers the specific use path you're claiming is reachable
- sev: critical
- cwe: CWE-416
- kb: use after free callback teardown dangling pointer

### BIN-FMT-01 · Attacker-controlled format string
- signal: `printf(user_input)`, a logging call, or any `*printf` family function where the format argument itself (not just an argument to it) comes from untrusted input
- attack: supply `%x`/`%n`-style format specifiers to read stack memory or write to an arbitrary address
- proof: a leaked stack value confirmed to come from the format-string read, or (for `%n`) a demonstrated write
- fp: `printf("%s", user_input)` — user input as an *argument* to a fixed format string — is not this vector at all; the format string itself must be attacker-controlled
- sev: critical when a write primitive (`%n`) is achievable; high for a read-only leak
- cwe: CWE-134
- kb: format string vulnerability printf attacker controlled

### BIN-TOCTOU-01 · Permission check separated in time from the operation it gates
- signal: a setuid/privileged tool calls a check function (`access()`, a stat-based permission check) and then, in a separate step, performs the privileged file operation on the same path
- attack: race the window between check and use — swap the target path (a symlink swap) after the check passes but before the operation runs
- proof: the privileged operation demonstrably acting on a different file than the one that passed the check, with a reproducible timing window
- fp: an operation using `O_NOFOLLOW`/`openat` with a file descriptor carried from the check through to the use (no re-resolution of the path) is not vulnerable to this — confirm the code re-resolves the path by name between check and use before flagging
- sev: high
- cwe: CWE-367
- kb: toctou time of check time of use symlink race setuid
