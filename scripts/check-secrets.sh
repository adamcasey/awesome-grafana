#!/usr/bin/env bash
# Fails if a secret could reach (or has reached) git. Runs as the pre-commit hook and in CI.
#
#   scripts/check-secrets.sh            check files tracked in the repo (CI)
#   scripts/check-secrets.sh --staged   check what is about to be committed (pre-commit hook)
#
# Why not just `dotenvx precommit`? It catches plaintext values in .env files, but it passes
# when .env.keys is force-added (`git add -f`), because it treats the file as gitignored.
# The private key leaking is the one failure that makes the encryption pointless.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

if [[ "${1:-}" == "--staged" ]]; then
  files=$(git diff --cached --name-only --diff-filter=ACMR)
  show() { git show ":$1"; }
else
  files=$(git ls-files)
  show() { cat "$1"; }
fi

fail=0
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  base=$(basename "$f")

  # 1. Private key files must never be committed.
  if [[ "$base" == .env.keys || "$base" == *.env.keys ]]; then
    echo "✗ $f: dotenvx private key file must never be committed" >&2; fail=1; continue
  fi

  # 2. A private key pasted into any tracked text file (64 hex chars after the variable name).
  if show "$f" 2>/dev/null | grep -IqE 'DOTENV_PRIVATE_KEY[A-Z_]*[[:space:]]*[=:][[:space:]]*["'\'']?[0-9a-f]{64}'; then
    echo "✗ $f: contains a DOTENV_PRIVATE_KEY value" >&2; fail=1
  fi

  # 3. .env files: every assignment must be encrypted or empty (.env.example documents names only).
  if [[ "$base" == .env || "$base" == .env.* ]]; then
    bad=$(show "$f" | grep -vE '^[[:space:]]*(#|$)' \
          | grep -vE '^[[:space:]]*DOTENV_PUBLIC_KEY[A-Z_]*=' \
          | grep -vE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=("encrypted:[^"]+"|encrypted:[^[:space:]]+|""|)[[:space:]]*$' \
          | sed -E 's/=.*/=<value hidden>/' || true)
    if [[ -n "$bad" ]]; then
      echo "✗ $f: plaintext values (run: dotenvx encrypt -f $f):" >&2
      echo "$bad" | sed 's/^/    /' >&2
      fail=1
    fi
  fi
done <<< "$files"

if [[ $fail -ne 0 ]]; then
  echo "Secret check failed. Nothing was committed." >&2
  exit 1
fi
echo "✓ secret check passed"
