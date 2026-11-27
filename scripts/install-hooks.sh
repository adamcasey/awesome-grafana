#!/usr/bin/env bash
# One-time per clone: install the pre-commit hook that blocks plaintext secrets and private keys.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
hook="$(git rev-parse --git-path hooks)/pre-commit"
cat > "$hook" <<'EOF'
#!/usr/bin/env bash
exec "$(git rev-parse --show-toplevel)/scripts/check-secrets.sh" --staged
EOF
chmod +x "$hook" "$root/scripts/check-secrets.sh"
echo "installed $hook"
