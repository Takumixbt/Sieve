#!/usr/bin/env sh
# secrets-sweep.sh — portable tracked-secret grep (recon-agent's secret_scan
# fallback when trufflehog/gitleaks are absent). OPTIONAL; not a replacement for a
# real secret scanner, just a dependency-free floor. Every hit is a LEAD: confirm
# the value is live and in-scope before reporting (shared-rules.md), and treat a
# leaked signer/deployer key as a CROSSOVER lead, not "info disclosure, low".
set -eu
SRC="${1:-.}"; cd "$SRC"
echo "## secret sweep over $SRC (leads, verify each)"
grep -rnE \
  '(secret|token|api[_-]?key|password|passwd|private[_-]?key|mnemonic|aws_access|aws_secret|bearer)[ "'"'"':=]+[A-Za-z0-9/+_.-]{16,}' \
  . \
  --include='*.env' --include='*.yml' --include='*.yaml' --include='*.json' \
  --include='*.js' --include='*.ts' --include='*.py' --include='*.go' --include='*.rs' \
  --include='*.sh' --include='*.tf' --include='*.config' \
  2>/dev/null \
  | grep -vE 'example|sample|dummy|placeholder|your[_-]?|xxxx|<|test/|node_modules|\.lock' \
  | head -40 || echo "  (no obvious tracked secrets)"
echo "-- private-key blocks --"
grep -rnlE 'BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY' . 2>/dev/null | grep -vE 'node_modules|test' | head || true
