#!/usr/bin/env bash
#
# One-shot environment setup for SGL On Site.
#
# Paste this into the "Setup script" field of a Claude Code cloud environment
# (it runs once before Claude Code launches), or run it locally:  bash scripts/setup_env.sh
#
# Prepares everything the app + the browser-validation loop need:
#   * PostgreSQL 16 + full tzdata (the app formats times in US/Eastern, a legacy
#     alias that minimal tzdata images omit -> ZoneInfoNotFoundError at runtime)
#   * the `sglman` dev database and a `postgres`/`devpass` login
#   * Python deps via Poetry
#   * a dev `.env` (MOCK_DISCORD, MOCK_SEEDGEN + a generated STORAGE_SECRET) if
#     one is absent
#
# Idempotent and safe to re-run. Does NOT boot the app — do that per task with
# `./start.sh dev`. See the `ui-validation` skill for the full validation loop.
#
set -euo pipefail
cd "$(dirname "$0")/.."

say() { printf '\n\033[1;34m[setup]\033[0m %s\n' "$*"; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then command -v sudo >/dev/null 2>&1 && SUDO="sudo"; fi

# Run a command as the postgres OS user. As root, `$SUDO -u postgres` expands
# to a bare `-u postgres` (SUDO is empty) and fails — use `su` instead.
as_postgres() {
  if [ "$(id -u)" -eq 0 ]; then
    su postgres -s /bin/sh -c "$*"
  else
    $SUDO -u postgres sh -c "$*"
  fi
}

# 1. System packages: postgres server/client + tzdata --------------------------
if command -v apt-get >/dev/null 2>&1; then
  say "Installing postgresql + tzdata (best effort)"
  $SUDO apt-get update -qq || true
  # `env` keeps the assignment valid when $SUDO expands to nothing (root):
  # after expansion the shell no longer treats VAR=val as an assignment prefix.
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    postgresql postgresql-client tzdata || true
fi

# 1b. Ensure the legacy US/Eastern zoneinfo alias exists (app uses it directly)
if [ ! -e /usr/share/zoneinfo/US/Eastern ] && [ -e /usr/share/zoneinfo/America/New_York ]; then
  say "Creating US/Eastern zoneinfo alias"
  $SUDO mkdir -p /usr/share/zoneinfo/US
  $SUDO cp /usr/share/zoneinfo/America/New_York /usr/share/zoneinfo/US/Eastern
fi

# 2. Start the default PostgreSQL cluster --------------------------------------
say "Starting PostgreSQL"
PG_VER="$(pg_lsclusters -h 2>/dev/null | awk 'NR==1{print $1}')"
if [ -n "${PG_VER:-}" ]; then
  $SUDO pg_ctlcluster "$PG_VER" main start 2>/dev/null || true
fi
$SUDO service postgresql start 2>/dev/null || true
# Wait for the socket to accept connections
for _ in $(seq 1 20); do
  if as_postgres "psql -tAc 'SELECT 1'" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

# 3. Dev role + database (idempotent) ------------------------------------------
say "Ensuring role/password and sglman database"
as_postgres "psql -v ON_ERROR_STOP=0" >/dev/null <<'SQL'
ALTER USER postgres PASSWORD 'devpass';
SELECT 'CREATE DATABASE sglman' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sglman')\gexec
SQL

# 4. Python dependencies -------------------------------------------------------
say "Installing Python dependencies (poetry install)"
poetry install --no-interaction || poetry install

# 5. Dev .env (only if absent; .env is gitignored) -----------------------------
if [ ! -f .env ]; then
  say "Writing dev .env (MOCK_DISCORD, MOCK_SEEDGEN, generated STORAGE_SECRET)"
  SECRET="$(poetry run python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  cat > .env <<ENV
DB_NAME=sglman
DB_USERNAME=postgres
DB_PASSWORD=devpass
DB_HOST=localhost
DB_PORT=5432
STORAGE_SECRET=${SECRET}
ENVIRONMENT=development
MOCK_DISCORD=true
MOCK_SEEDGEN=true
ENV
else
  say ".env already present — leaving it untouched"
fi

# 6. Report browser tooling (for the ui-validation loop) -----------------------
if [ -d /opt/pw-browsers ]; then
  say "Playwright browsers found at /opt/pw-browsers (use node's global playwright)"
else
  say "No pre-installed Playwright browsers detected; the ui-validation skill will note fallbacks"
fi

say "Setup complete. Boot with: ./start.sh dev   then seed: poetry run python scripts/seed_dev.py"
