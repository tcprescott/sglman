#!/usr/bin/env python3
"""
PostToolUse hook: block hardcoded secrets in source files.

Secrets must come from the environment (`os.environ` / `os.getenv`), never be
committed as literals. This flags two things in the edited file:
  1. A string that matches the Discord bot-token shape.
  2. An assignment to a secret-named variable (STORAGE_SECRET, DB_PASSWORD,
     *_TOKEN, *_SECRET, *_API_KEY, …) whose value is a hardcoded string literal.

Exit 0 = clean / not applicable; exit 2 = likely secret (stderr explains).
"""

import ast
import json
import re
import sys

DISCORD_TOKEN_RX = re.compile(r"\b[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b")
SECRET_NAME_RX = re.compile(r"(?:SECRET|TOKEN|PASSWORD|PASSWD|API_?KEY)", re.IGNORECASE)
PLACEHOLDER_RX = re.compile(
    r"your|change[\s_-]?me|example|placeholder|replace|dummy|fake|test|<|\{|xxxx", re.IGNORECASE
)


def looks_like_secret_literal(value: str) -> bool:
    if len(value) < 12:
        return False
    if PLACEHOLDER_RX.search(value):
        return False
    return True


def assignment_targets(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    norm = file_path.replace("\\", "/")
    if "/.claude/" in norm or "/tests/" in norm or norm.startswith("tests/"):
        sys.exit(0)
    if norm.endswith(".env.example") or norm.endswith("/.env.example"):
        sys.exit(0)

    try:
        with open(file_path, encoding="utf-8") as fh:
            source = fh.read()
    except OSError:
        sys.exit(0)

    violations: list[tuple[int, str]] = []

    for m in DISCORD_TOKEN_RX.finditer(source):
        line = source.count("\n", 0, m.start()) + 1
        violations.append((line, "string matching a Discord bot-token shape"))

    if file_path.endswith(".py"):
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                targets = assignment_targets(node)
                if not targets:
                    continue
                value = getattr(node, "value", None)
                if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    continue
                if not looks_like_secret_literal(value.value):
                    continue
                for name in targets:
                    if SECRET_NAME_RX.search(name):
                        violations.append(
                            (node.lineno, f"hardcoded literal assigned to secret-named '{name}'")
                        )

    if violations:
        for line, what in sorted(set(violations)):
            print(
                f"POSSIBLE SECRET LEAK in '{file_path}' (line {line}): {what}.\n"
                f"  Read secrets from the environment (os.environ / os.getenv), "
                f"never hardcode them.",
                file=sys.stderr,
            )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
