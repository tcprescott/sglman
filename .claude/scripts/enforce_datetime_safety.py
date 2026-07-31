#!/usr/bin/env python3
"""
PreToolUse hook: block naive / non-UTC datetime construction.

CLAUDE.md: all datetimes are stored in UTC and rendered on a per-request local
clock. A *naive* datetime (no tzinfo) or `datetime.utcnow()` silently violates
that — it has no timezone, so storing or comparing it corrupts the UTC
invariant. A naive *date* boundary is the same bug one level up: it silently
picks UTC's day instead of the viewer's. Reads a Claude Code tool payload from
stdin and exits with:
  0 — no violation (or not applicable)
  2 — violation found (stderr explains the timezone-safe fix)

Blocked (any .py file outside tests/ and timezone.py):
  datetime.utcnow(...)              → always tz-naive; use datetime.now(timezone.utc)
  datetime.now()  / datetime.now() .x   → naive; pass a tz or use the helpers
  datetime.today()                  → naive; same fix
  datetime.combine(...) w/o tzinfo= → naive; use combine_local / local_day_bounds
  date.today()                      → UTC's day, not the viewer's; use today_local()

Deliberately NOT flagged (correct, used widely):
  datetime.now(timezone.utc), datetime.now(tz)       — a tz argument is present.
  datetime.combine(d, t, tzinfo=zone)                — explicitly zoned.
"""

import json
import re
import sys

from _hook_paths import anchor

anchor()  # hooks inherit the session's shell cwd; pin paths to the repo

class _NaiveCombine:
    """Matches ``datetime.combine(...)`` calls that pass no ``tzinfo=``.

    Scans forward from each ``datetime.combine(`` and reads to its matching
    close paren, tracking depth so a nested call (``time(0, 0)``) does not end
    the argument list early. Exposes ``.search`` so it drops into ``RULES``
    beside the compiled patterns.
    """

    _START = re.compile(r"\bdatetime\.combine\s*\(")

    def search(self, content: str):
        for m in self._START.finditer(content):
            depth, i = 1, m.end()
            while i < len(content) and depth:
                if content[i] == "(":
                    depth += 1
                elif content[i] == ")":
                    depth -= 1
                i += 1
            if "tzinfo=" not in content[m.end():i]:
                return m
        return None


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
        "(now_local, parse_local_datetime)",
    ),
    (
        # ``datetime.combine(...)`` with no ``tzinfo=``. The result is naive, and
        # the ORM reads a naive value as UTC — so a range bound built this way
        # silently selects the UTC day rather than the display-clock day. This
        # was a live bug in MatchRepository.get_for_date.
        # Matched call-by-call (below) rather than by one regex: "a combine()
        # whose own argument list lacks tzinfo=" is not a regular language, and
        # a lookbehind for it has to be fixed-width.
        _NaiveCombine(),
        "naive datetime.combine(...)",
        "use `combine_local(day, moment)` or `local_day_bounds(start, end)` from "
        "application/utils/timezone.py, or pass `tzinfo=` explicitly",
    ),
    (
        # ``date.today()`` is whatever day the *server process* is on, which is
        # UTC in every deployment — never the viewer's day.
        re.compile(r"\bdate\.today\s*\(\s*\)"),
        "date.today()",
        "use `today_local()` from application/utils/timezone.py — a calendar date "
        "has no meaning without a timezone",
    ),
]


def is_exempt(path: str) -> bool:
    norm = path.replace("\\", "/")
    return (
        "/tests/" in norm
        or norm.startswith("tests/")
        # Only the canonical helper module, not any file that happens to be
        # named timezone.py — the exemption exists so the helpers can build the
        # zoned values everyone else must ask them for.
        or norm.endswith("application/utils/timezone.py")
        or norm.endswith("application/timezone_context.py")
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
