#!/usr/bin/env python3
"""
PreToolUse hook (Bash matcher): block a few unsafe shell commands.

Exit 0 = allowed; exit 2 = blocked (stderr explains the safer alternative).

Blocks:
  pip install …                              → use `poetry add` (Poetry-managed)
  git push --force / -f / --force-with-lease → no force-push of shared history
  git commit --no-verify / -n                → don't skip git's verification hooks
  git reset --hard                           → discards uncommitted work
  git clean -f                               → deletes untracked files
  git checkout -- .                          → discards working-tree changes
  aerich downgrade                           → reverts DB migrations (data loss)
  rm -rf                                      → irreversible recursive delete
  dropdb / DROP TABLE|DATABASE               → destroys data
"""

import json
import re
import sys


RULES = [
    (
        re.compile(r"\bpip3?\s+install\b|\bpython3?\s+-m\s+pip\s+install\b"),
        "pip install",
        "use `poetry add <pkg>` (or `poetry add --group dev <pkg>`) — this project is Poetry-managed.",
    ),
    (
        re.compile(r"\bgit\s+push\b.*?(?:--force\b|--force-with-lease\b|\s-f\b)"),
        "git push --force",
        "force-pushing rewrites shared history — push without --force, or resolve the divergence first.",
    ),
    (
        re.compile(r"\bgit\s+commit\b.*?(?:--no-verify\b|\s-n\b)"),
        "git commit --no-verify",
        "--no-verify skips git's verification hooks — commit normally.",
    ),
    (
        re.compile(r"\bgit\s+reset\b.*?--hard\b"),
        "git reset --hard",
        "this discards uncommitted work irrecoverably — stash or commit first, or reset without --hard.",
    ),
    (
        re.compile(r"\bgit\s+clean\b\s+-\S*f"),
        "git clean -f",
        "this deletes untracked files irrecoverably — run `git clean -n` first to preview.",
    ),
    (
        re.compile(r"\bgit\s+checkout\b\s+(?:--\s+)?\.(?:\s|$)"),
        "git checkout -- .",
        "this discards all uncommitted changes in the working tree — stash first if unsure.",
    ),
    (
        re.compile(r"\baerich\s+downgrade\b"),
        "aerich downgrade",
        "this reverts database migrations and can lose data — confirm the target version is intended.",
    ),
    (
        re.compile(r"\brm\s+-\S*r\S*f|\brm\s+-\S*f\S*r"),
        "rm -rf",
        "recursive force-delete is irreversible — narrow the target or delete specific paths.",
    ),
    (
        re.compile(r"\bdropdb\b|\bDROP\s+(?:TABLE|DATABASE)\b", re.IGNORECASE),
        "dropdb / DROP TABLE|DATABASE",
        "this destroys data irrecoverably — do not drop databases or tables from a tool call.",
    ),
]


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    for rx, name, fix in RULES:
        if rx.search(command):
            print(
                f"BLOCKED COMMAND: {name}\n"
                f"  Command: {command}\n"
                f"  {fix}",
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
