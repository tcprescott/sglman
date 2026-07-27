#!/usr/bin/env bash
# session-start.sh — SessionStart hook: audit source files against reference docs.
# Stdout is injected as context at the top of each session.

source "$( dirname "${BASH_SOURCE[0]}" )/_repo.sh"

# Public module stems in a package. Descends one level into public subpackages
# (application/services/match/, discord/, …) but skips private ones (_bracket/),
# whose modules are implementation detail rather than documented surface.
stems_in_dir() {
  local dir="$1"
  [ -d "$dir" ] || return
  find "$dir" -maxdepth 2 -name "*.py" ! -name "__init__.py" ! -name "_*.py" \
    ! -path "*/_*/*" -exec basename {} .py \;
}

# Direct children only — used where a stem must map to its own sibling __init__.py.
stems_at_top() {
  local dir="$1"
  [ -d "$dir" ] || return
  find "$dir" -maxdepth 1 -name "*.py" ! -name "__init__.py" ! -name "_*.py" \
    -exec basename {} .py \;
}

# Public subpackages of a package (each carries its own barrel).
subpackages_of() {
  local dir="$1"
  [ -d "$dir" ] || return
  find "$dir" -mindepth 1 -maxdepth 1 -type d ! -name "_*" ! -name "__pycache__"
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

# __init__.py export checks — a module must be reachable from its own package's
# barrel. Whether the parent re-exports a subpackage is a per-package choice:
# the four domain clusters are re-exported so `from application.services import
# MatchService` still resolves, while bracket_engines/tournament_strategies are
# imported by path on purpose.
check_exports() {
  local dir="$1"
  local init_file="$dir/__init__.py"
  local label="${dir#$REPO/}"
  [ -f "$init_file" ] || return
  # A barrel that auto-imports its siblings (bracket_engines) names none of them
  # on purpose — "dropping a new engine file needs no edit here".
  grep -q "iter_modules" "$init_file" 2>/dev/null && return
  while IFS= read -r stem; do
    grep -q "$stem" "$init_file" 2>/dev/null || echo "EXPORT GAP [$label/__init__.py]: $stem — not imported/exported"
  done < <(stems_at_top "$dir")
}

for pkg in "$REPO/application/services" "$REPO/application/repositories"; do
  check_exports "$pkg"
  while IFS= read -r sub; do
    check_exports "$sub"
  done < <(subpackages_of "$pkg")
done

# Model count sanity note. Models live in the models/ package (historically a
# single models.py); support both layouts.
if [ -d "$REPO/models" ]; then
  MODEL_COUNT=$(grep -rh "^class.*Model" "$REPO/models"/*.py 2>/dev/null | wc -l | tr -d ' ')
  MODEL_LABEL="the models/ package"
elif [ -f "$REPO/models.py" ]; then
  MODEL_COUNT=$(grep -c "^class.*Model" "$REPO/models.py" 2>/dev/null || echo "?")
  MODEL_LABEL="models.py"
else
  MODEL_COUNT="?"
  MODEL_LABEL="models"
fi
echo ""
echo "SESSION CONTEXT: $MODEL_LABEL has $MODEL_COUNT Model subclasses. Verify docs/reference/data-model.md matches when editing models."
