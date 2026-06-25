#!/usr/bin/env python3
"""
PostToolUse hook: audit calls must not be guarded by `if actor:`.

CLAUDE.md: pass `actor: User` explicitly — never guard an audit call with
`if actor:`. A swallowed actor means a silently-missing audit entry. This
inspects the resulting file after a Write/Edit and flags any `if` statement
whose test is an `actor` truthiness/None check **when its body contains a
`write_log(...)` call** (kept narrow to avoid flagging unrelated `if actor:`).

Exit 0 = clean / not applicable; exit 2 = violation (stderr explains).
"""

import ast
import json
import sys


def is_actor_test(test: ast.AST) -> bool:
    # if actor:
    if isinstance(test, ast.Name) and test.id == "actor":
        return True
    # if not actor:
    if (
        isinstance(test, ast.UnaryOp)
        and isinstance(test.op, ast.Not)
        and isinstance(test.operand, ast.Name)
        and test.operand.id == "actor"
    ):
        return True
    # if actor is None: / if actor is not None:
    if (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "actor"
        and len(test.ops) == 1
        and isinstance(test.ops[0], (ast.Is, ast.IsNot))
    ):
        return True
    return False


def body_writes_log(nodes: list[ast.stmt]) -> bool:
    for stmt in nodes:
        for node in ast.walk(stmt):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "write_log"
            ):
                return True
    return False


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
        if not isinstance(node, ast.If):
            continue
        if not is_actor_test(node.test):
            continue
        if body_writes_log(node.body) or body_writes_log(node.orelse):
            violations.append(node.lineno)

    if violations:
        for line in violations:
            print(
                f"AUDIT CONVENTION VIOLATION in '{file_path}' (line {line}):\n"
                f"  write_log() guarded by an `if actor:` check.\n"
                f"  Pass `actor: User` explicitly — never guard the audit call with `if actor:`.",
                file=sys.stderr,
            )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
