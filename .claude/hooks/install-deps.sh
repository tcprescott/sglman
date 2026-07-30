#!/usr/bin/env bash
# install-deps.sh — SessionStart hook: install Python dependencies via Poetry so
# tests, linters, and the app are runnable from the first turn of a web session.
#
# Runs synchronously (blocks session start) so nothing races ahead of the
# install. Web-only: skipped on local machines where deps are already managed.
set -euo pipefail

# Only run in Claude Code on the web / remote environments.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

source "$( dirname "${BASH_SOURCE[0]}" )/_repo.sh"

# Idempotent: poetry sync is a no-op when the lockfile is already satisfied, and
# takes advantage of the cached container state on subsequent sessions. The
# project is package-mode = false, so there is no root package to install.
#
# sync, not install: a cached container venv can carry packages that were
# dropped from the lockfile since the image was built, and plain `poetry
# install` leaves those in place. py-cord is the one that bites — it and
# discord.py unpack into the same `discord/` package, so a leftover copy owns
# the shared modules and `discord.EntityType` stops existing.
poetry sync --no-interaction --no-ansi

# Removing py-cord takes the ~107 modules it shares with discord.py down with
# it, because both record those paths as their own. Poetry still considers
# discord.py installed, so the repair has to force a reinstall.
if ! poetry run python -c "import discord; assert discord.__title__ == 'discord'; discord.EntityType" >/dev/null 2>&1; then
  echo "discord.py is damaged (shared files removed with a conflicting fork) — reinstalling."
  poetry run python -m pip uninstall -y discord.py >/dev/null
  poetry sync --no-interaction --no-ansi
fi

echo "Dependencies installed (poetry sync)."
