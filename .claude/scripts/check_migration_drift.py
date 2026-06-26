#!/usr/bin/env python3
"""
Stop hook: warn when models.py changed without a matching new migration.

`enforce_migration_safety.py` (PreToolUse) stops hand-edits to generated
migrations; this catches the opposite mistake — editing models.py and forgetting
to generate the migration. If models.py is modified in the working tree but no new
file was added under migrations/models/, the schema and the ORM have drifted.

Exit 0 = in sync / models unchanged; exit 2 = drift (stderr explains the fix).
"""

import subprocess
import sys


def run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""
    return out.stdout


def main() -> None:
    # Stop hooks must drain stdin or they can hang.
    try:
        sys.stdin.read()
    except Exception:
        pass

    tracked_changes = run(["git", "diff", "--name-only", "HEAD"]).splitlines()
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"]).splitlines()

    changed = {line.strip().replace("\\", "/") for line in (*tracked_changes, *untracked) if line.strip()}

    models_changed = "models.py" in changed
    if not models_changed:
        sys.exit(0)

    new_migration = any(
        c.startswith("migrations/models/") and c.endswith(".py") and c in set(untracked) for c in changed
    )
    # Also accept a modified (not just untracked) migration file as a fresh migration
    # being staged in the same session.
    touched_migration = any(
        c.startswith("migrations/models/") and c.endswith(".py") for c in changed
    )

    if not (new_migration or touched_migration):
        print(
            "MIGRATION DRIFT: models.py changed but no new file under migrations/models/.\n"
            "  The ORM models and the database schema have drifted.\n"
            "  Fix: run `poetry run aerich migrate && poetry run aerich upgrade`.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
