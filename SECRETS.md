# Secrets (dotenvx)

API keys live in **`.env` at the repo root, committed encrypted**. Each value is encrypted with the
public key at the top of the file; only the matching **private key** can decrypt it.

| File | Committed? | Contains |
|---|---|---|
| `.env` | ✅ yes | `DOTENV_PUBLIC_KEY` + `NAME="encrypted:…"` values |
| `.env.keys` | ❌ never (gitignored, blocked by hook + CI) | `DOTENV_PRIVATE_KEY` |
| `.env.example` | ✅ yes | names only, empty values |

The private key exists in exactly two places: your machine (`.env.keys`) and the GitHub secret
`DOTENV_PRIVATE_KEY`. Losing it means re-entering every value. Keep a copy in your password manager.

## First-time setup (once)
```bash
npm install -g @dotenvx/dotenvx      # or: brew install dotenvx/brew/dotenvx
scripts/install-hooks.sh             # pre-commit hook: blocks plaintext values and private keys
dotenvx set EIA_API_KEY  <value>     # creates .env + .env.keys on first use
dotenvx set NASS_API_KEY <value>
dotenvx keypair DOTENV_PRIVATE_KEY   # copy this into GitHub → Settings → Secrets → Actions → DOTENV_PRIVATE_KEY
git add .env && git commit -m "Add encrypted .env"
```
Then delete the legacy `EIA_API_KEY` and `NASS_API_KEY` repository secrets, and remove the
`TODO(remove after migration)` fallback in `.github/workflows/mo-holiday-etl.yml`.

## Everyday use
| Task | Command |
|---|---|
| Add/change a secret | `dotenvx set NAME value` (encrypts in place; commit `.env`) |
| Read one value | `dotenvx get NAME` |
| Run anything with secrets | `dotenvx run -- <command>`, e.g. `cd mo-holiday-season && dotenvx run -f ../.env -- python -m holiday_etl run --only eia_grid` |
| Use in your shell | `export EIA_API_KEY=$(dotenvx get EIA_API_KEY)` |
| Rotate the keypair | `dotenvx rotate`, then update the `DOTENV_PRIVATE_KEY` GitHub secret |
| New laptop | Copy the private key from your password manager into `.env.keys` (`DOTENV_PRIVATE_KEY=…`) |

## Guardrails
- **Pre-commit hook** (`scripts/check-secrets.sh --staged`) blocks plaintext values in any `.env*`,
  any `.env.keys` file, and a private key pasted into any file. `dotenvx precommit` alone misses a
  force-added `.env.keys`, which is why this script exists.
- **`secret guard` workflow** runs the same check on every push/PR (hooks can be bypassed with `--no-verify`).
- **Missing key in CI** fails the ETL with a clear error. Without the guard, dotenvx would pass the ciphertext through as the "key".
- `--overload` in CI makes the encrypted `.env` win over any leftover legacy secret.
