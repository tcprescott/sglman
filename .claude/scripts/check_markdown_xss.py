#!/usr/bin/env python3
"""
PostToolUse hook: flag ui.markdown()/ui.html() rendering non-literal content.

NiceGUI's ui.markdown() and ui.html() pass raw HTML through unsanitized, so feeding
them a stored, user-writable value is a stored-XSS sink (commit 1fd0ab3:
ui.markdown(tournament.triforce_access_message) — admin-writable, shown to every
player). This inspects the resulting presentation file and rejects a ui.markdown/
ui.html call whose first positional argument is not a pure string literal — i.e. a
variable, attribute, or function result. Static literals (the rich text a developer
authored) are allowed.

Scoped to the presentation layer (pages/, theme/, frontend.py). Module-qualified
nicegui.ui.markdown(x) is deliberately not matched (precision over recall, like the
ORM-write hook). Exit 0 = clean / not applicable; exit 2 = violation (stderr explains).
"""

import ast
import json
import sys


SINKS = {"markdown", "html"}


def is_presentation(path: str) -> bool:
    norm = path.replace("\\", "/")
    return "/pages/" in norm or "/theme/" in norm or norm.endswith("frontend.py")


def is_pure_literal(node: ast.AST) -> bool:
    """True if node is a constant or an f-string / + concat composed only of literals."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.JoinedStr):
        return all(
            is_pure_literal(v.value)
            for v in node.values
            if isinstance(v, ast.FormattedValue)
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return is_pure_literal(node.left) and is_pure_literal(node.right)
    return False


def find_violations(tree: ast.AST) -> list[tuple[int, str, str]]:
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in SINKS:
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "ui"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not is_pure_literal(first):
            rendered = ast.unparse(first) if hasattr(ast, "unparse") else "<dynamic>"
            out.append((node.lineno, func.attr, rendered))
    return out


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path or not file_path.endswith(".py"):
        sys.exit(0)

    norm = file_path.replace("\\", "/")
    if "/.claude/" in norm or not is_presentation(file_path):
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

    violations = find_violations(tree)
    if violations:
        for line, sink, rendered in violations:
            print(
                f"XSS RISK in '{file_path}' (line {line}):\n"
                f"  ui.{sink}(...) is rendering non-literal content ({rendered}).\n"
                f"  NiceGUI ui.markdown()/ui.html() pass raw HTML through unsanitized, so a\n"
                f"  stored, user-writable value becomes a stored-XSS sink shown to every viewer.\n"
                f"  Fix: render dynamic text with ui.label(...).style('white-space: pre-wrap'),\n"
                f"  or sanitize before rendering. Reserve ui.markdown/ui.html for static literals.\n"
                f"  See docs/security-audit.md #1.",
                file=sys.stderr,
            )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
