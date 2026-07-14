#!/usr/bin/env python3
"""
Stop hook: a new model needs a row in scripts/seed_dev.py.

CLAUDE.md > Adding a new feature, step 6: extend ``scripts/seed_dev.py`` so a
new model has at least one representative row — the seed script is the fixture
set the /ui-validation browser loop and every dev environment run against, so
"a feature the seed never creates is a feature no one can see in the running
app". This is the seed-side mirror of check_migration_drift.py: at Stop, if the
working tree adds a **new Tortoise Model class** under ``models/`` but
``scripts/seed_dev.py`` was not touched, block the turn with a reminder.

Only *new* ``class Foo(Model)`` definitions trigger it (field edits to an
existing model rarely need new seed rows — that would be noise). Detection is
``git diff -U0`` added lines plus untracked model files; requires the base list
to contain the bare word ``Model`` so enums/dataclasses/pydantic ``BaseModel``
never match.

Exit 0 = no new models / seed updated; exit 2 = seed gap (stderr explains).
"""

import re
import subprocess
import sys

CLASS_RE = re.compile(r"^\s*class\s+(\w+)\s*\(([^)]*)\)")
ADDED_CLASS_RE = re.compile(r"^\+\s*class\s+(\w+)\s*\(([^)]*)\)")
BARE_MODEL_RE = re.compile(r"(?<![\w.])Model\b")


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

    changed = {
        line.strip().replace("\\", "/")
        for line in run(["git", "diff", "--name-only", "HEAD"]).splitlines()
        if line.strip()
    }
    untracked = {
        line.strip().replace("\\", "/")
        for line in run(["git", "ls-files", "--others", "--exclude-standard"]).splitlines()
        if line.strip()
    }

    new_models: list[str] = []

    diff = run(["git", "diff", "-U0", "HEAD", "--", "models", "models.py"])
    for line in diff.splitlines():
        m = ADDED_CLASS_RE.match(line)
        if m and BARE_MODEL_RE.search(m.group(2)):
            new_models.append(m.group(1))

    for path in sorted(untracked):
        if not (path.startswith("models/") or path == "models.py") or not path.endswith(".py"):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    m = CLASS_RE.match(line)
                    if m and BARE_MODEL_RE.search(m.group(2)):
                        new_models.append(m.group(1))
        except OSError:
            continue

    if not new_models:
        sys.exit(0)

    seed_touched = "scripts/seed_dev.py" in changed or "scripts/seed_dev.py" in untracked
    if seed_touched:
        sys.exit(0)

    names = ", ".join(sorted(set(new_models)))
    print(
        f"SEED COVERAGE GAP: new model(s) added ({names}) but scripts/seed_dev.py is unchanged.\n"
        f"  CLAUDE.md 'Adding a new feature' step 6: the dev seed is the fixture set the\n"
        f"  /ui-validation browser loop and every dev environment run against — a model the\n"
        f"  seed never creates is invisible in the running app.\n"
        f"  Fix: add at least one representative row (and each meaningful state) to\n"
        f"  scripts/seed_dev.py, idempotent (get_or_create) and tenant-scoped like the\n"
        f"  existing rows.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
