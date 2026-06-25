#!/usr/bin/env python3
"""
PostToolUse hook: audit actions must be AuditActions.* constants, not literals.

CLAUDE.md: audit action strings are namespaced `verb.object` and should come
from the AuditActions class. This inspects the resulting file after a Write/Edit
and flags any `write_log(...)` call whose `action` argument is a bare string
literal instead of an `AuditActions.*` constant.

Exit 0 = clean / not applicable; exit 2 = violation (stderr explains).
"""

import ast
import json
import sys


def action_arg(call: ast.Call) -> ast.AST | None:
    for kw in call.keywords:
        if kw.arg == "action":
            return kw.value
    # Positional signature: write_log(actor, action, details=None)
    if len(call.args) >= 2:
        return call.args[1]
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path or not file_path.endswith(".py"):
        sys.exit(0)

    norm = file_path.replace("\\", "/")
    if "/.claude/" in norm or "/tests/" in norm or norm.endswith("/audit_service.py"):
        sys.exit(0)

    try:
        with open(file_path, encoding="utf-8") as fh:
            source = fh.read()
    except OSError:
        sys.exit(0)

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        sys.exit(0)  # check_syntax.py owns syntax-error reporting

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "write_log":
            continue
        arg = action_arg(node)
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            violations.append((node.lineno, arg.value))

    if violations:
        for line, literal in violations:
            print(
                f"AUDIT CONVENTION VIOLATION in '{file_path}' (line {line}):\n"
                f"  write_log() called with a string-literal action: {literal!r}\n"
                f"  Use an AuditActions.* constant (add one to AuditActions if it doesn't exist).",
                file=sys.stderr,
            )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
