#!/usr/bin/env python3
"""
PreToolUse hook: block event-loop-blocking calls.

All users share one asyncio event loop — a single blocking call freezes the
whole app. Reads a Claude Code tool payload from stdin and exits with:
  0 — no violation (or not applicable)
  2 — violation found (stderr explains the blocker and the async-safe fix)

Repo-wide bans (any .py file):
  import requests / from requests   → use `async with httpx.AsyncClient()`
  time.sleep(...)                   → use `await asyncio.sleep(...)`

Presentation-only bans (pages/, theme/, frontend.py):
  asyncio.create_task(...) / asyncio.ensure_future(...)
                                    → use `background_tasks.create(coro())`
"""

import json
import re
import sys


# (compiled pattern, short name, fix hint) applied to every .py file.
REPO_WIDE = [
    (
        re.compile(r"^\s*(?:import\s+requests\b|from\s+requests\b)", re.MULTILINE),
        "synchronous 'requests' library",
        "use `async with httpx.AsyncClient()` — requests blocks the shared event loop",
    ),
    (
        re.compile(r"\btime\.sleep\s*\("),
        "time.sleep(...)",
        "use `await asyncio.sleep(...)` — time.sleep blocks the shared event loop",
    ),
]

# Applied only to presentation-layer files (NiceGUI-specific guidance).
PRESENTATION_ONLY = [
    (
        re.compile(r"\basyncio\.(?:create_task|ensure_future)\s*\("),
        "asyncio.create_task()/ensure_future()",
        "use `background_tasks.create(coro())` (from nicegui import background_tasks) — "
        "bare tasks get garbage-collected and swallow exceptions",
    ),
]


def is_presentation(path: str) -> bool:
    norm = path.replace("\\", "/")
    return "/pages/" in norm or "/theme/" in norm or norm.endswith("frontend.py")


def check(file_path: str, content: str) -> list[str]:
    violations = []
    for rx, name, fix in REPO_WIDE:
        if rx.search(content):
            violations.append(
                f"EVENT-LOOP SAFETY VIOLATION in '{file_path}':\n"
                f"  Blocking call detected: {name}\n"
                f"  All users share one asyncio event loop — blocking it freezes the app.\n"
                f"  Fix: {fix}."
            )
    if is_presentation(file_path):
        for rx, name, fix in PRESENTATION_ONLY:
            if rx.search(content):
                violations.append(
                    f"EVENT-LOOP SAFETY VIOLATION in '{file_path}':\n"
                    f"  Disallowed in the presentation layer: {name}\n"
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

    # Never inspect the hook scripts themselves (they contain these patterns as literals).
    if "/.claude/" in file_path.replace("\\", "/"):
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
