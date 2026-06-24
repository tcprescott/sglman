#!/usr/bin/env bash
# session-start.sh — SessionStart hook: audit source files against reference docs.
# Stdout is injected as context at the top of each session.

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

stems_in_dir() {
  local dir="$1"
  [ -d "$dir" ] || return
  find "$dir" -maxdepth 1 -name "*.py" ! -name "__init__.py" ! -name "_*.py" \
    -exec basename {} .py \;
}

check_coverage() {
  local label="$1" dir="$2" doc="$3"
  local missing=()
  while IFS= read -r stem; do
    grep -q "$stem" "$doc" 2>/dev/null || missing+=("$stem")
  done < <(stems_in_dir "$dir")
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "DOC GAP [$label]: ${missing[*]} — not found in $doc"
  fi
}

# Source-to-doc coverage checks
check_coverage "services"      "$REPO/application/services"      "$REPO/docs/reference/services.md"
check_coverage "repositories"  "$REPO/application/repositories"  "$REPO/docs/reference/data-model.md"
check_coverage "api/routers"   "$REPO/api/routers"               "$REPO/docs/reference/rest-api.md"
check_coverage "discordbot"    "$REPO/discordbot"                "$REPO/docs/reference/discord-integration.md"

# __init__.py export checks
for init_file in "$REPO/application/services/__init__.py" "$REPO/application/repositories/__init__.py"; do
  dir="$(dirname "$init_file")"
  label="${dir#$REPO/}"
  while IFS= read -r stem; do
    grep -q "$stem" "$init_file" 2>/dev/null || echo "EXPORT GAP [$label/__init__.py]: $stem — not imported/exported"
  done < <(stems_in_dir "$dir")
done

# Model count sanity note
MODEL_COUNT=$(grep -c "^class.*Model" "$REPO/models.py" 2>/dev/null || echo "?")
echo ""
echo "SESSION CONTEXT: models.py has $MODEL_COUNT Model subclasses. Verify docs/reference/data-model.md matches when editing models.py."
