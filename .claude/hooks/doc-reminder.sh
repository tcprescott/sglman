#!/usr/bin/env bash
# doc-reminder.sh — PostToolUse Write|Edit hook: emit a targeted doc reminder when
# a tracked Python source file is written or edited.
# JSON from stdin has: tool_name, tool_input.file_path, tool_response.

# Parse file_path from stdin JSON
if command -v jq &>/dev/null; then
  INPUT=$(cat)
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
else
  INPUT=$(cat)
  FILE_PATH=$(echo "$INPUT" \
    | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | head -1 \
    | sed 's/.*: *"//' | sed 's/"$//')
fi

[[ -z "$FILE_PATH" ]] && exit 0

# Skip docs and non-Python files to avoid reminder loops and noise
case "$FILE_PATH" in
  */docs/*|*.md)         exit 0 ;;
  */migrations/*)        exit 0 ;;
esac
case "$FILE_PATH" in
  *.py) ;;
  *)    exit 0 ;;
esac

REMINDED=0
remind() { echo "DOC REMINDER: $1"; REMINDED=1; }

# models.py
case "$FILE_PATH" in
  */models.py)
    remind "models.py changed → update docs/reference/data-model.md (model list, field tables, enums, ERD)"
    remind "models.py changed → run: poetry run aerich migrate && poetry run aerich upgrade"
    ;;
esac

# api/ routers and schemas
case "$FILE_PATH" in
  */api/routers/*.py|*/api/schemas/*.py|*/api/dependencies.py|*/api/rate_limit.py)
    remind "$FILE_PATH changed → update docs/reference/rest-api.md (endpoint catalogue, schemas)"
    ;;
esac

# application/services/
case "$FILE_PATH" in
  */application/services/*.py)
    [[ "$(basename "$FILE_PATH")" == "__init__.py" ]] && exit 0
    remind "$FILE_PATH changed → update docs/reference/services.md"
    remind "If this is a new service, export it from application/services/__init__.py"
    ;;
esac

# application/repositories/
case "$FILE_PATH" in
  */application/repositories/*.py)
    [[ "$(basename "$FILE_PATH")" == "__init__.py" ]] && exit 0
    remind "$FILE_PATH changed → update docs/reference/data-model.md (repository section)"
    remind "If this is a new repository, export it from application/repositories/__init__.py"
    ;;
esac

# pages/ and theme/ (including subdirectories like admin_tabs/, dialog/, tables/)
case "$FILE_PATH" in
  */pages/*.py|*/pages/*/*.py|*/pages/*/*/*.py|*/theme/*.py|*/theme/*/*.py|*/frontend.py)
    remind "$FILE_PATH changed → update docs/reference/frontend.md (page/tab/dialog/table inventory)"
    ;;
esac

# discordbot/
case "$FILE_PATH" in
  */discordbot/*.py)
    [[ "$(basename "$FILE_PATH")" == "__init__.py" ]] && exit 0
    remind "$FILE_PATH changed → update docs/reference/discord-integration.md (key files table, interaction handlers)"
    ;;
esac

# New top-level directory heuristic: __init__.py two path components below repo root
if [[ $REMINDED -eq 0 ]]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null)"
  if [[ -n "$REPO" ]]; then
    REL="${FILE_PATH#$REPO/}"
    DEPTH=$(echo "$REL" | tr -cd '/' | wc -c)
    if [[ $DEPTH -eq 1 && "$(basename "$FILE_PATH")" == "__init__.py" ]]; then
      TOP_DIR=$(echo "$REL" | cut -d'/' -f1)
      if ! grep -q "$TOP_DIR" "$REPO/docs/README.md" 2>/dev/null; then
        remind "New top-level directory '$TOP_DIR/' detected → add a row to docs/README.md coverage map"
      fi
    fi
  fi
fi

exit 0
