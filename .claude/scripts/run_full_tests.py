#!/usr/bin/env python3
"""
Stop hook: run the full pytest suite when source code changed this session.

Gated like doc-check.sh — only runs when `git diff` (working tree + staged) or
untracked files show a changed non-test `.py` under application/, api/, pages/,
theme/, discordbot/, or models.py. Keeps idle turns fast while catching
regressions before they reach CI.

Exit 0 = suite passed / nothing relevant changed; exit 2 = suite failed
(captured output goes to stderr so Claude can fix before ending the turn).
"""

import os
import subprocess
import sys

PYTEST_TIMEOUT = 110

SOURCE_PREFIXES = (
    "application/",
    "api/",
    "pages/",
    "theme/",
    "discordbot/",
)


def is_source(path: str) -> bool:
    if not path.endswith(".py"):
        return False
    if "/tests/" in path or path.startswith("tests/"):
        return False
    if path == "models.py" or path == "frontend.py":
        return True
    return any(path.startswith(p) for p in SOURCE_PREFIXES)


def changed_files() -> list[str]:
    files: set[str] = set()
    for cmd in (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
        files.update(line.strip() for line in out.stdout.splitlines() if line.strip())
    return sorted(files)


def main() -> None:
    # Stop hooks must drain stdin or they can hang.
    try:
        sys.stdin.read()
    except Exception:
        pass

    if not any(is_source(f.replace("\\", "/")) for f in changed_files()):
        sys.exit(0)

    env = {**os.environ, "MOCK_DISCORD": "true"}
    try:
        result = subprocess.run(
            ["poetry", "run", "pytest", "-q"],
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT,
            env=env,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        sys.exit(0)

    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        print(
            "FULL TEST SUITE FAILED (source files changed this session):\n"
            f"{output}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
