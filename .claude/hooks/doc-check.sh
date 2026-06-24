#!/usr/bin/env bash
# doc-check.sh — Stop hook: post-turn documentation checklist based on git diff.
# Fires after every Claude turn. Drains stdin (required — hook hangs if stdin is not read).

cat > /dev/null  # drain stdin

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Staged + unstaged changes vs HEAD, plus untracked Python files
CHANGED=$(git -C "$REPO" diff --name-only HEAD 2>/dev/null)
UNTRACKED=$(git -C "$REPO" ls-files --others --exclude-standard 2>/dev/null | grep '\.py$')
ALL_CHANGED=$(printf '%s\n%s' "$CHANGED" "$UNTRACKED" | grep -v '^$' | sort -u)

[[ -z "$ALL_CHANGED" ]] && exit 0

models_changed=0
services_changed=0
repos_changed=0
api_changed=0
frontend_changed=0
discord_changed=0

while IFS= read -r f; do
  case "$f" in
    models.py)
      models_changed=1 ;;
    application/services/*.py)
      [[ "$(basename "$f")" != "__init__.py" ]] && services_changed=1 ;;
    application/repositories/*.py)
      [[ "$(basename "$f")" != "__init__.py" ]] && repos_changed=1 ;;
    api/routers/*.py|api/schemas/*.py|api/dependencies.py|api/rate_limit.py)
      api_changed=1 ;;
    pages/*.py|pages/*/*.py|pages/*/*/*.py|theme/*.py|theme/*/*.py|frontend.py)
      frontend_changed=1 ;;
    discordbot/*.py)
      [[ "$(basename "$f")" != "__init__.py" ]] && discord_changed=1 ;;
  esac
done <<< "$ALL_CHANGED"

CHECKLIST=()

[[ $models_changed -eq 1 ]] && {
  CHECKLIST+=("[ ] docs/reference/data-model.md — model list, field tables, enums, ERD")
  CHECKLIST+=("[ ] Run: poetry run aerich migrate && poetry run aerich upgrade")
}
[[ $services_changed -eq 1 ]] && {
  CHECKLIST+=("[ ] docs/reference/services.md — service catalog table and method signatures")
  CHECKLIST+=("[ ] application/services/__init__.py — verify new services are exported")
}
[[ $repos_changed -eq 1 ]] && {
  CHECKLIST+=("[ ] docs/reference/data-model.md — repository section")
  CHECKLIST+=("[ ] application/repositories/__init__.py — verify new repositories are exported")
}
[[ $api_changed -eq 1 ]] && {
  CHECKLIST+=("[ ] docs/reference/rest-api.md — endpoint catalogue, request/response schemas")
}
[[ $frontend_changed -eq 1 ]] && {
  CHECKLIST+=("[ ] docs/reference/frontend.md — page/tab/dialog/table inventory")
}
[[ $discord_changed -eq 1 ]] && {
  CHECKLIST+=("[ ] docs/reference/discord-integration.md — key files table, interaction handlers")
}

# Substantial changes → remind about current-state.md
TOTAL_PY=$(echo "$ALL_CHANGED" | grep '\.py$' | wc -l | tr -d ' ')
if [[ $TOTAL_PY -ge 3 ]]; then
  CHECKLIST+=("[ ] docs/current-state.md — update feature status or known issues if applicable")
fi

# New top-level directory not already in docs/README.md
NEW_DIRS=$(echo "$ALL_CHANGED" | awk -F/ 'NF==2 && $2 ~ /\.py$/ {print $1}' | sort -u)
for d in $NEW_DIRS; do
  grep -q "$d" "$REPO/docs/README.md" 2>/dev/null || \
    CHECKLIST+=("[ ] docs/README.md — new directory '$d/' detected; add a row to the coverage map")
done

if [[ ${#CHECKLIST[@]} -gt 0 ]]; then
  echo ""
  echo "POST-TURN DOC CHECKLIST (based on git diff HEAD):"
  for item in "${CHECKLIST[@]}"; do
    echo "  $item"
  done
  echo ""
fi

exit 0
