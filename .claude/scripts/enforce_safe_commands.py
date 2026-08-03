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
  pkill -f … / pgrep -f … | kill             → kills its own shell; use ./start.sh stop

The ``-f`` rule has one false-positive shape worth knowing: writing *prose* about
the hazard through a Bash heredoc can trip it, because markdown inline code
(`` `pkill -f x` ``) puts a backtick before the command and a backtick opens a
command substitution in shell. Shell ``#`` comments are stripped before scanning,
which covers the common case; for the rest, edit files with the Edit/Write tools
rather than a heredoc, which is the right tool anyway and is not hooked.

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


# `pkill -f …` and `pgrep -f …` at a **command position** — start of input, or
# after a separator that begins one. The anchor matters: prose merely naming the
# command (a shell comment, a heredoc, a docstring in a file being written) is
# not the hazard, and this file and its test both have to discuss it.
_PKILL_F = re.compile(r"(?:^|[\n;&|]|\$\(|`)\s*pkill\b[^\n|;]*?\s-\w*f\w*(?:\s|$)")
_PGREP_F = re.compile(r"(?:^|[\n;&|]|\$\(|`)\s*pgrep\b[^\n|;]*?\s-\w*f\w*(?:\s|$)")

# `kill` as a command, so a `pgrep -f` used only to *look* stays allowed.
_KILL_CMD = re.compile(r"(?:^|[\n;&|]|\$\(|`|\bdo\s)\s*kill\b")

# A `#` comment to end of line. Stripped before scanning so prose about the
# hazard does not read as the hazard.
_SHELL_COMMENT = re.compile(r"(?m)(?:^|\s)#[^\n]*")


def pattern_kill_hazard(command: str) -> str | None:
    """Why this command's ``-f`` process matching will hit its own shell.

    ``-f`` matches against **full command lines**, and the shell running the
    command has the whole command — pattern included — in its own. The pattern
    is always present, because it is right there as the argument. So the match
    is not a risk to weigh: it is a certainty, and the shell dies (exit 143/144,
    no output) before the intended target is touched.

    Tricks like ``uvicorn[ ]main:app`` do not help — the character class still
    matches the literal text elsewhere in the same command — and neither does
    quoting.

    ``pgrep -f`` alone is fine, since looking is harmless; it becomes the same
    hazard the moment its output is piped or looped into ``kill``.

    Returns the reason, or None when there is nothing to warn about.
    """
    scannable = _SHELL_COMMENT.sub(" ", command)
    if _PKILL_F.search(scannable):
        return "pkill -f"
    if _PGREP_F.search(scannable) and _KILL_CMD.search(scannable):
        return "pgrep -f piped into kill"
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    hazard = pattern_kill_hazard(command)
    if hazard is not None:
        print(
            f"BLOCKED COMMAND: {hazard}\n"
            f"  Command: {command}\n"
            "  -f matches full command lines, and the shell running this has the\n"
            "  whole command — pattern included — in its own. It will kill itself\n"
            "  (exit 143/144, no output) and leave the real target running.\n"
            "  Quoting and tricks like 'uvi[c]orn' do not help.\n"
            "  To stop this project's dev server: ./start.sh stop\n"
            "  Otherwise kill a PID you captured earlier, or match on process\n"
            "  names without -f.",
            file=sys.stderr,
        )
        sys.exit(2)

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
