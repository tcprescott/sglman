#!/usr/bin/env python3
"""
PreToolUse hook: block naive / non-UTC datetime construction.

CLAUDE.md: all datetimes are stored in UTC and shown in US/Eastern. A *naive*
datetime (no tzinfo) or `datetime.utcnow()` silently violates that — it has no
timezone, so storing or comparing it corrupts the UTC invariant. Reads a Claude
Code tool payload from stdin and exits with:
  0 — no violation (or not applicable)
  2 — violation found (stderr explains the timezone-safe fix)

Blocked (any .py file outside tests/ and timezone.py):
  datetime.utcnow(...)              → always tz-naive; use datetime.now(timezone.utc)
  datetime.now()  / datetime.now() .x   → naive; pass a tz or use the helpers
  datetime.today()                  → naive; same fix

Deliberately NOT flagged (correct, used widely):
  datetime.now(timezone.utc), datetime.now(eastern)  — a tz argument is present.
"""

import json
import re
import sys


# (compiled pattern, short name, fix hint). Each anchors on a *naive* call.
RULES = [
    (
        re.compile(r"\bdatetime\.utcnow\s*\("),
        "datetime.utcnow(...)",
        "utcnow() returns a tz-naive datetime — use `datetime.now(timezone.utc)` for UTC storage",
    ),
    (
        # `datetime.now()` / `datetime.today()` with an empty arg list only.
        # `datetime.now(timezone.utc)` has an argument and is not matched.
        re.compile(r"\bdatetime\.(?:now|today)\s*\(\s*\)"),
        "naive datetime.now()/today()",
        "pass a timezone (`datetime.now(timezone.utc)`) or use application/utils/timezone.py "
        "(now_eastern, parse_eastern_datetime)",
    ),
]


def is_exempt(path: str) -> bool:
    norm = path.replace("\\", "/")
    return (
        "/tests/" in norm
        or norm.startswith("tests/")
        or norm.endswith("/timezone.py")
        or norm == "application/utils/timezone.py"
    )


def check(file_path: str, content: str) -> list[str]:
    violations = []
    for rx, name, fix in RULES:
        if rx.search(content):
            violations.append(
                f"TIMEZONE SAFETY VIOLATION in '{file_path}':\n"
                f"  Naive datetime detected: {name}\n"
                f"  All datetimes are stored in UTC — a tz-naive value breaks that invariant.\n"
                f"  Fix: {fix}."
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
    # Never inspect the hook scripts themselves (they contain these patterns as literals).
    if "/.claude/" in norm or is_exempt(file_path):
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
