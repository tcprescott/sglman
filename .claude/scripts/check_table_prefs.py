#!/usr/bin/env python3
"""
PostToolUse hook: warn when a presentation-layer ``ui.table`` has no preference
key, so its columns cannot be customized.

The gap this catches
--------------------
Every desktop table in the app lets a person choose which columns they see, in
what order and at what width, remembered per account. That capability rides on a
single argument, and a table that ships without it is not broken — it is just
quietly the one board nobody can adapt, which is exactly the state the whole
feature exists to end. It is also invisible in review: the table renders fine.

So the rule is the same shape as the mobile-card rule next door — a new table
either opts in or says why not::

    from theme.tables.mobile_grid import enable_mobile_grid
    from theme.tables.preferences import TableKeys

    table = ui.table(columns=COLUMNS, rows=[], row_key='id').classes('w-full wiz-table')
    table.add_slot('body-cell-actions', ACTIONS)
    enable_mobile_grid(table, COLUMNS, actions=ACTIONS, table_key=TableKeys.MY_TABLE)

A bespoke table that wires its own ``item`` slot calls ``customize_table`` itself,
**after** that slot is registered.

Detection
---------
Runs after the file is on disk, so the whole file is visible. Using the AST it
finds every ``ui.table(...)`` and treats it as compliant when any of these hold:

  * ``enable_mobile_grid(<table>, …, table_key=…)`` is called on it;
  * ``customize_table(<table>, …)`` is called on it;
  * a ``table-prefs: exempt`` / ``noqa: table-prefs`` comment sits on the
    construction line or the line above.

Exits 2 with guidance on a hit; exits 0 otherwise (fail open — non-Python,
unreadable, unparseable, or no ``ui.table`` present).
"""

import ast
import json
import re
import sys

from _hook_paths import anchor

anchor()  # hooks inherit the session's shell cwd; pin paths to the repo

_EXEMPT_RE = re.compile(r"table-prefs:\s*exempt|noqa:\s*table-prefs", re.IGNORECASE)


def is_presentation(path: str) -> bool:
    norm = path.replace("\\", "/")
    return "/pages/" in norm or "/theme/" in norm or norm.endswith("frontend.py")


def _is_ui_table(node: ast.Call) -> bool:
    fn = node.func
    return (
        isinstance(fn, ast.Attribute)
        and fn.attr == "table"
        and isinstance(fn.value, ast.Name)
        and fn.value.id == "ui"
    )


def _seg(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def _parent_map(tree: ast.AST) -> dict:
    parents: dict = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _enclosing_stmt(node: ast.AST, parents: dict) -> ast.stmt | None:
    cur = node
    while cur is not None and not isinstance(cur, ast.stmt):
        cur = parents.get(cur)
    return cur if isinstance(cur, ast.stmt) else None


def _assign_target(stmt: ast.stmt, source: str) -> str | None:
    if isinstance(stmt, ast.Assign) and stmt.targets:
        return _seg(source, stmt.targets[0])
    if isinstance(stmt, ast.AnnAssign):
        return _seg(source, stmt.target)
    return None


def check(source: str, file_path: str) -> list[str]:
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return []  # check_syntax.py owns this; fail open here.

    parents = _parent_map(tree)
    lines = source.splitlines()

    # First-arg source text of every call that makes a table customizable.
    customized: set[str] = set()
    # A view class takes the key as a constructor argument and passes it on; the
    # table it builds is compliant by construction.
    passes_key_through = "self.table_key" in source

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name == "customize_table":
            customized.add(_seg(source, node.args[0]))
        elif name == "enable_mobile_grid":
            if any(kw.arg == "table_key" for kw in node.keywords):
                customized.add(_seg(source, node.args[0]))

    violations: list[str] = []
    seen: set[int] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_ui_table(node)):
            continue
        if node.lineno in seen:
            continue
        seen.add(node.lineno)

        window = "\n".join(lines[max(0, node.lineno - 2): node.lineno])
        if _EXEMPT_RE.search(window):
            continue

        stmt = _enclosing_stmt(node, parents)
        target = _assign_target(stmt, source) if stmt is not None else None

        if passes_key_through or (target is not None and target in customized):
            continue

        violations.append(
            f"TABLE PREFERENCES MISSING in '{file_path}' (line {node.lineno}):\n"
            f"  This ui.table has no preference key, so nobody can hide, reorder or\n"
            f"  resize its columns — every other table in the app can. Add one:\n"
            f"    from theme.tables.preferences import TableKeys\n"
            f"    enable_mobile_grid(table, COLUMNS, actions=ACTIONS,\n"
            f"                       table_key=TableKeys.MY_TABLE)\n"
            f"  A bespoke table with its own 'item' slot calls customize_table(table,\n"
            f"  COLUMNS, key=TableKeys.MY_TABLE) **after** registering that slot.\n"
            f"  Declare the key in TableKeys (theme/tables/preferences.py) rather than\n"
            f"  inlining a string. If this table genuinely should not be customizable,\n"
            f"  add a `# table-prefs: exempt — <reason>` comment."
        )
    return violations


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path or not file_path.endswith(".py"):
        sys.exit(0)
    if "/.claude/" in file_path.replace("\\", "/"):
        sys.exit(0)
    if not is_presentation(file_path):
        sys.exit(0)

    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            source = fh.read()
    except OSError:
        sys.exit(0)

    violations = check(source, file_path)
    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
