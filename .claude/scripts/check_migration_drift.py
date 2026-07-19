#!/usr/bin/env python3
"""
Stop hook: warn when a schema-bearing model change has no matching migration.

`enforce_migration_safety.py` (PreToolUse) stops hand-edits to generated
migrations; this catches the opposite mistake — editing a model (under the
models/ package, or a legacy models.py) and forgetting to generate the
migration with `aerich migrate`.

"Some migration file changed" is not evidence (an unrelated migration would
satisfy it), and "any model file changed" is not drift (enum members, docstrings
and comments generate no DDL). So the check is **schema-token matching**:

- Tokens = names of newly added ``class Foo(Model)`` definitions plus any field
  name on an added *or removed* ``name = fields.…`` line, from the working-tree
  diff of ``models``/``models.py`` (and untracked model files).
- Evidence = added diff lines under ``migrations/models/`` plus the full
  content of untracked files there.
- Every token must appear (case-insensitive substring) in the evidence; aerich
  migrations name the tables and columns they touch, so a genuine migration
  satisfies this naturally.

No tokens → exit 0 (an enum/docstring-only model edit needs no migration).
A field moved between files with no schema change is the one residual false
positive: exempt it by adding a ``# schema-unchanged`` comment on an added line
in that model file, which drops that file's tokens.

Exit 0 = in sync / no schema-bearing change; exit 2 = drift (stderr explains).
"""

import re
import subprocess
import sys

CLASS_RE = re.compile(r"^\s*class\s+(\w+)\s*\(([^)]*)\)")
ADDED_CLASS_RE = re.compile(r"^\+\s*class\s+(\w+)\s*\(([^)]*)\)")
BARE_MODEL_RE = re.compile(r"(?<![\w.])Model\b")
FIELD_RE = re.compile(r"^[+-]\s*(\w+)\s*=\s*fields\.")
FILE_HEADER_RE = re.compile(r"^\+\+\+ b/(.+)$")
SCHEMA_UNCHANGED_RE = re.compile(r"^\+.*#\s*schema-unchanged")


def run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""
    return out.stdout


def tokens_from_diff(diff: str) -> set[str]:
    """Schema tokens per file, honoring the per-file # schema-unchanged escape."""
    per_file: dict[str, set[str]] = {}
    exempt: set[str] = set()
    current = ""
    for line in diff.splitlines():
        header = FILE_HEADER_RE.match(line)
        if header:
            current = header.group(1)
            per_file.setdefault(current, set())
            continue
        if SCHEMA_UNCHANGED_RE.match(line):
            exempt.add(current)
            continue
        m = ADDED_CLASS_RE.match(line)
        if m and BARE_MODEL_RE.search(m.group(2)):
            per_file.setdefault(current, set()).add(m.group(1).lower())
            continue
        f = FIELD_RE.match(line)
        if f:
            per_file.setdefault(current, set()).add(f.group(1).lower())
    tokens: set[str] = set()
    for path, names in per_file.items():
        if path not in exempt:
            tokens |= names
    return tokens


def tokens_from_untracked(paths: list[str]) -> set[str]:
    tokens: set[str] = set()
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            continue
        if re.search(r"#\s*schema-unchanged", content):
            continue
        for line in content.splitlines():
            m = CLASS_RE.match(line)
            if m and BARE_MODEL_RE.search(m.group(2)):
                tokens.add(m.group(1).lower())
                continue
            f = re.match(r"^\s*(\w+)\s*=\s*fields\.", line)
            if f:
                tokens.add(f.group(1).lower())
    return tokens


def migration_evidence(untracked: set[str]) -> str:
    added = [
        line[1:]
        for line in run(["git", "diff", "-U0", "HEAD", "--", "migrations/models"]).splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    chunks = ["\n".join(added)]
    for path in sorted(untracked):
        if path.startswith("migrations/models/") and path.endswith(".py"):
            try:
                with open(path, encoding="utf-8") as fh:
                    chunks.append(fh.read())
            except OSError:
                continue
    return "\n".join(chunks).lower()


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

    tokens = tokens_from_diff(run(["git", "diff", "-U0", "HEAD", "--", "models", "models.py"]))
    tokens |= tokens_from_untracked(
        [p for p in sorted(untracked) if (p.startswith("models/") or p == "models.py") and p.endswith(".py")]
    )

    if not tokens:
        sys.exit(0)

    evidence = migration_evidence(untracked)
    # A FK field ``tenant`` appears in DDL as ``tenant_id``; substring match
    # covers it, but only when there is evidence at all.
    missing = sorted(t for t in tokens if t not in evidence)

    if missing:
        names = ", ".join(missing)
        print(
            f"MIGRATION DRIFT: schema-bearing model change with no matching migration.\n"
            f"  Changed model/field name(s) not found in any new/modified migration: {names}\n"
            f"  The ORM models and the database schema have drifted.\n"
            f"  Fix: run `poetry run aerich migrate && poetry run aerich upgrade`.\n"
            f"  (Moved a field between files with no schema change? Add a\n"
            f"  `# schema-unchanged` comment in that model file.)",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
