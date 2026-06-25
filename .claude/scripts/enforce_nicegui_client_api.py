#!/usr/bin/env python3
"""
PreToolUse hook: block the non-existent ``Client.current`` accessor.

NiceGUI 3.x exposes the per-request client as ``context.client`` (``from nicegui
import context``). There is no ``current`` attribute on the ``Client`` *class*, so
``Client.current`` raises ``AttributeError: type object 'Client' has no attribute
'current'`` the moment the handler fires. This bites the slot-context fix pattern in
particular: capturing the client for a ``background_tasks.create(...)`` coroutine with
``Client.current`` looks right but crashes at runtime (commit bca4d7a introduced exactly
this while "fixing" a slot-context error).

Reads a Claude Code tool payload from stdin and exits with:
  0 — no violation (or not applicable)
  2 — violation found (stderr explains the crash and the fix)

Content regex (same approach as enforce_async_safety.py): matches ``Client.current`` in
the incoming Write/Edit fragment. ``\bClient`` won't match a longer name like
``MyClient.current``, and the codebase never has a legitimate ``Client.current`` (the
class has no such attribute), so false positives are ~0.
"""

import json
import re
import sys


CLIENT_CURRENT = re.compile(r"\bClient\.current\b")


def check(file_path: str, content: str) -> list[str]:
    violations = []
    if CLIENT_CURRENT.search(content):
        violations.append(
            f"NICEGUI CLIENT API VIOLATION in '{file_path}':\n"
            f"  `Client.current` does not exist in NiceGUI 3.x — it raises\n"
            f"  `AttributeError: type object 'Client' has no attribute 'current'` at runtime.\n"
            f"  Fix: use `context.client` (from nicegui import context). To capture the client\n"
            f"  for a background_tasks.create(...) coroutine, pass `context.client` at the call site."
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

    # Never inspect the hook scripts themselves (they contain this pattern as a literal).
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
