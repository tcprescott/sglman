#!/usr/bin/env python3
"""
PreToolUse hook: block hand-rolled native date/time inputs in the UI.

A ``type=time`` field has to say which clock it means — the app no longer runs on
one timezone, so a bare "Time" label is a guess about whose wall clock the value
will be read on. ``theme/dialog/_helpers.py`` puts that label on every field it
builds (``Time (EDT)``), which only works while every field goes through it.

Four fields had hand-rolled the props string instead. Not by intent: the helper
could not express ``dense``, so anything wanting a compact inline row wrote its
own — and a hand-rolled field is one the zone label can never reach. The helpers
now take ``dense``/``stack_label``, so there is no longer a reason to bypass, and
this hook is what keeps that true.

Use ``native_date_input`` / ``native_time_input`` / ``native_datetime_input``.
Reads a Claude Code tool payload from stdin and exits with:
  0 — no violation (or not applicable)
  2 — violation found (stderr names the helper to use)
"""

import json
import re
import sys

from _hook_paths import anchor

anchor()  # hooks inherit the session's shell cwd; pin paths to the repo

# A props string requesting a native date/time control. Matches the prop
# anywhere in the string (``'type=time dense'``, ``"dense type=date"``).
_RULE = re.compile(r"""\.props\(\s*(['"])[^'"]*\btype=(date|time|datetime-local)\b""")

_HELPER = {
    'date': 'native_date_input',
    'time': 'native_time_input',
    'datetime-local': 'native_datetime_input',
}

# Only the UI layer builds these controls.
_GUARDED_PREFIXES = ('pages/', 'theme/')

# The module that defines the helpers is the one place the props string belongs.
_EXEMPT_SUFFIX = 'theme/dialog/_helpers.py'


def is_guarded(path: str) -> bool:
    norm = path.replace("\\", "/")
    if "/tests/" in norm or norm.startswith("tests/"):
        return False
    if norm.endswith(_EXEMPT_SUFFIX):
        return False
    # Accept both repo-relative and absolute paths.
    return any(f'/{p}' in norm or norm.startswith(p) for p in _GUARDED_PREFIXES)


def check(file_path: str, content: str) -> list[str]:
    violations = []
    for match in _RULE.finditer(content):
        kind = match.group(2)
        violations.append(
            f"HAND-ROLLED DATE/TIME INPUT in '{file_path}':\n"
            f"  Found a raw `type={kind}` props string.\n"
            f"  A native date/time control must come from theme/dialog/_helpers.py so it\n"
            f"  carries the timezone its value will be read in — a bare 'Time' label is\n"
            f"  ambiguous now that viewers are on different clocks.\n"
            f"  Fix: use `{_HELPER[kind]}(...)`. It takes dense=/stack_label= for compact\n"
            f"  rows, tz= when the field is read on the community's clock rather than the\n"
            f"  viewer's, and show_timezone=False when nearby copy already says it."
        )
    return violations


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path or not file_path.endswith(".py"):
        sys.exit(0)

    norm = file_path.replace("\\", "/")
    # Never inspect the hook scripts themselves (they hold the pattern literally).
    if "/.claude/" in norm or not is_guarded(file_path):
        sys.exit(0)

    if tool_name == "Write":
        content = tool_input.get("content", "")
    elif tool_name == "Edit":
        content = tool_input.get("new_string", "")
    else:
        sys.exit(0)

    if not content:
        sys.exit(0)

    violations = check(file_path, content)
    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
