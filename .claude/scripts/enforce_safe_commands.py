#!/usr/bin/env python3
"""
PreToolUse hook (Bash matcher): block a few unsafe shell commands.

Exit 0 = allowed; exit 2 = blocked (stderr explains the safer alternative).

Blocks:
  pip install …                              → use `poetry add` (Poetry-managed)
  git push --force / -f / --force-with-lease → no force-push of shared history
  git commit --no-verify / -n                → don't skip git's verification hooks
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
