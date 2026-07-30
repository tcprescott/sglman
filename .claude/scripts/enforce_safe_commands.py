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
  dropdb / DROP TABLE|DATABASE               → destroys data (local sessions only)
  git add .env / committing .env             → never commit secrets
  cat/echo .env                               → don't print secrets to the transcript

A rule marked ``local_only`` is enforced only when Claude runs on a developer's
machine. Remote sessions (Claude Code on the web) get a fresh throwaway
container and a scratch Postgres, so a rule that exists to protect a real
long-lived database has nothing to protect there and only blocks legitimate
work.
"""

import json
import os
import re
import sys
from typing import NamedTuple, Pattern

from _hook_paths import anchor

anchor()  # hooks inherit the session's shell cwd; pin paths to the repo


class Rule(NamedTuple):
    pattern: Pattern[str]
    name: str
    fix: str
    local_only: bool = False


def is_local_session() -> bool:
    """True on a developer machine; False in Claude Code on the web."""
    return os.environ.get("CLAUDE_CODE_REMOTE", "") != "true"


RULES = [
    Rule(
        re.compile(r"\bpip3?\s+install\b|\bpython3?\s+-m\s+pip\s+install\b"),
        "pip install",
        "use `poetry add <pkg>` (or `poetry add --group dev <pkg>`) — this project is Poetry-managed.",
    ),
    Rule(
        re.compile(r"\bgit\s+push\b.*?(?:--force\b|--force-with-lease\b|\s-f\b)"),
        "git push --force",
        "force-pushing rewrites shared history — push without --force, or resolve the divergence first.",
    ),
    Rule(
        re.compile(r"\bgit\s+commit\b.*?(?:--no-verify\b|\s-n\b)"),
        "git commit --no-verify",
        "--no-verify skips git's verification hooks — commit normally.",
    ),
    Rule(
        re.compile(r"\bgit\s+reset\b.*?--hard\b"),
        "git reset --hard",
        "this discards uncommitted work irrecoverably — stash or commit first, or reset without --hard.",
    ),
    Rule(
        re.compile(r"\bgit\s+clean\b\s+-\S*f"),
        "git clean -f",
        "this deletes untracked files irrecoverably — run `git clean -n` first to preview.",
    ),
    Rule(
        re.compile(r"\bgit\s+checkout\b\s+(?:--\s+)?\.(?:\s|$)"),
        "git checkout -- .",
        "this discards all uncommitted changes in the working tree — stash first if unsure.",
    ),
    Rule(
        re.compile(r"\baerich\s+downgrade\b"),
        "aerich downgrade",
        "this reverts database migrations and can lose data — confirm the target version is intended.",
    ),
    Rule(
        re.compile(r"\brm\s+-\S*r\S*f|\brm\s+-\S*f\S*r"),
        "rm -rf",
        "recursive force-delete is irreversible — narrow the target or delete specific paths.",
    ),
    Rule(
        re.compile(r"\bdropdb\b|\bDROP\s+(?:TABLE|DATABASE)\b", re.IGNORECASE),
        "dropdb / DROP TABLE|DATABASE",
        "this destroys data irrecoverably — do not drop databases or tables from a tool call.",
        local_only=True,
    ),
    Rule(
        re.compile(r"\bgit\s+(?:add|commit)\b[^\n]*?\.env\b(?!\.example)"),
        "git add/commit .env",
        ".env holds real secrets and must never be committed — it is gitignored on purpose.",
    ),
    Rule(
        re.compile(r"\b(?:cat|less|more|head|tail|xxd|od|strings)\b[^\n]*?\.env\b(?!\.example)"),
        "printing .env",
        "don't dump .env to the transcript — it exposes secrets. Read individual values via os.environ in code instead.",
    ),
    Rule(
        re.compile(r"\bpoetry\s+add\b[^\n]*?\bpy-?cord\b", re.IGNORECASE),
        "poetry add py-cord",
        "py-cord and discord.py are forks that both install into the same `discord/` package "
        "and silently overwrite each other — this project uses discord.py only.",
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

    local = is_local_session()

    for rule in RULES:
        if rule.local_only and not local:
            continue
        if rule.pattern.search(command):
            print(
                f"BLOCKED COMMAND: {rule.name}\n"
                f"  Command: {command}\n"
                f"  {rule.fix}",
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
