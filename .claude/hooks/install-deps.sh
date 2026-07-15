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

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$REPO"

# Idempotent: poetry install is a no-op when the lockfile is already satisfied,
# and takes advantage of the cached container state on subsequent sessions.
# The project is package-mode = false, so there is no root package to install.
poetry install --no-interaction --no-ansi

echo "Dependencies installed (poetry install)."
