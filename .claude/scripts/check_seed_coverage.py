#!/usr/bin/env python3
"""
Stop hook: a new model needs a row in the dev seed.

CLAUDE.md > Adding a new feature, step 6: extend ``scripts/seed_dev.py`` so a
new model has at least one representative row — the seed script is the fixture
set the /ui-validation browser loop and every dev environment run against, so
"a feature the seed never creates is a feature no one can see in the running
app". This is the seed-side mirror of check_migration_drift.py: at Stop, if the
working tree adds a **new Tortoise Model class** under ``models/`` whose name
does not appear anywhere in the ``scripts/seed_*.py`` working-tree content,
block the turn with a reminder.

"Touched the seed file" is not enough (an unrelated seed edit would satisfy
it): the check is a word-bounded search for the model's class name across all
seed scripts, which the seed's ``Model.get_or_create(...)`` calls satisfy
naturally. A model that genuinely cannot be seeded is exempted with a comment
in any seed script: ``# seed-exempt: Foo — <reason>`` (the name match hits it).
The runtime backstop is tests/test_seed_coverage.py, which runs the real seed
and asserts a row per tenant-FK model.

Only *new* ``class Foo(Model)`` definitions trigger it (field edits to an
existing model rarely need new seed rows — that would be noise). Detection is
``git diff -U0`` added lines plus untracked model files; requires the base list
to contain the bare word ``Model`` so enums/dataclasses/pydantic ``BaseModel``
never match.

Exit 0 = no new models / all named in a seed script; exit 2 = seed gap.
"""

import glob
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


def seed_content() -> str:
    """Concatenated working-tree content of every scripts/seed_*.py."""
    chunks = []
    for path in sorted(glob.glob("scripts/seed_*.py")):
        try:
            with open(path, encoding="utf-8") as fh:
                chunks.append(fh.read())
        except OSError:
            continue
    return "\n".join(chunks)


def main() -> None:
    # Stop hooks must drain stdin or they can hang.
    try:
        sys.stdin.read()
    except Exception:
        pass

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

    seeds = seed_content()
    if not seeds:
        sys.exit(0)  # seed scripts unreadable — fail open

    missing = sorted(
        name for name in set(new_models)
        if not re.search(rf"(?<!\w){re.escape(name)}(?!\w)", seeds)
    )
    if not missing:
        sys.exit(0)

    names = ", ".join(missing)
    print(
        f"SEED COVERAGE GAP: new model(s) added ({names}) but no scripts/seed_*.py names them.\n"
        f"  CLAUDE.md 'Adding a new feature' step 6: the dev seed is the fixture set the\n"
        f"  /ui-validation browser loop and every dev environment run against — a model the\n"
        f"  seed never creates is invisible in the running app.\n"
        f"  Fix: add at least one representative row (and each meaningful state) to\n"
        f"  scripts/seed_dev.py, idempotent (get_or_create) and tenant-scoped like the\n"
        f"  existing rows. tests/test_seed_coverage.py will verify the row actually lands.\n"
        f"  A model that genuinely cannot be seeded: add `# seed-exempt: {missing[0]} — <reason>`\n"
        f"  to scripts/seed_dev.py (and list it in that test's EXEMPT).",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
