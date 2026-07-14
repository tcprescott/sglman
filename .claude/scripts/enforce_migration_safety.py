#!/usr/bin/env python3
"""
PreToolUse hook: protect *existing* migrations from hand-edits.

Files under `migrations/models/` are applied migrations — editing one in place
desyncs it from the `models/` package, the aerich version table, and any database
that already ran it. That is the footgun this guards against, so it blocks Edit and
any Write that would overwrite an existing migration file.

Creating a *new* migration file is allowed: it is how a migration is added,
whether by `aerich migrate` or (for constraint/data changes aerich cannot
autogenerate — the pattern this repo already uses) by hand. Reads a Claude Code
tool payload from stdin and exits with:
  0 — no violation (or not applicable)
  2 — the target is an existing migration being edited (stderr explains)
"""

import json
import os
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    norm = file_path.replace("\\", "/")
    if not ("/migrations/models/" in norm or norm.startswith("migrations/models/")):
        sys.exit(0)

    # Allow creating a brand-new migration file; only block edits/overwrites of
    # an existing one (the actual desync risk).
    if tool_name == "Write" and not os.path.exists(file_path):
        sys.exit(0)

    print(
        f"MIGRATION SAFETY VIOLATION in '{file_path}':\n"
        f"  This migration already exists; editing it in place desyncs it from the\n"
        f"  models/ package, the aerich version table, and databases that already ran it.\n"
        f"  Fix: change the model in models/ and add a NEW migration (aerich migrate, or a\n"
        f"  hand-written file for constraint/data changes aerich cannot generate).",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
