#!/usr/bin/env python3
"""
PostToolUse hook: run the test file(s) related to an edited source file.

After a Write/Edit to a service/repository/api/test module, find the matching
pytest file and run just that file so regressions surface in-loop (CI runs the
full suite separately). Tests use in-memory SQLite with MOCK_DISCORD.

Exit 0 = passed / no related test / not applicable; exit 2 = the related test
failed (captured output goes to stderr for Claude to fix).
"""

import json
import os
import subprocess
import sys

# Run pytest with a margin under the hook's configured timeout so a clean message
# is produced instead of the harness killing the process.
PYTEST_TIMEOUT = 50


def candidate_tests(norm: str) -> list[str]:
    """Map a source path to the test files that should exercise it."""
    # Editing a test file → run that file directly.
    if "/tests/" in norm or norm.startswith("tests/"):
        return [norm] if norm.endswith(".py") and os.path.basename(norm).startswith("test_") else []

    base = os.path.basename(norm)
    if not base.endswith(".py") or base == "__init__.py":
        return []
    stem = base[:-3]

    candidates: list[str] = []
    if norm.startswith("application/services/") or "/application/services/" in norm:
        candidates.append(f"tests/services/test_{stem}.py")
    elif norm.startswith("application/repositories/") or "/application/repositories/" in norm:
        candidates += [f"tests/services/test_{stem}.py", f"tests/test_{stem}.py"]
    elif norm.startswith("api/") or "/api/" in norm:
        candidates += [f"tests/test_api_{stem}.py", f"tests/test_{stem}.py"]
    else:
        candidates.append(f"tests/test_{stem}.py")

    # Deduplicate while preserving order, keep only files that exist.
    seen: set[str] = set()
    existing: list[str] = []
    for c in candidates:
        if c not in seen and os.path.isfile(c):
            seen.add(c)
            existing.append(c)
    return existing


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    norm = file_path.replace("\\", "/")
    if "/.claude/" in norm:
        sys.exit(0)

    tests = candidate_tests(norm)
    if not tests:
        sys.exit(0)

    env = {**os.environ, "MOCK_DISCORD": "true"}
    try:
        result = subprocess.run(
            ["poetry", "run", "pytest", "-q", *tests],
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT,
            env=env,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Slow run or pytest/poetry unavailable: don't block productivity.
        sys.exit(0)

    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        print(
            f"RELATED TESTS FAILED for {', '.join(tests)} (after editing {file_path}):\n"
            f"{output}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
