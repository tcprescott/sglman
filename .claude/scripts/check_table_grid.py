#!/usr/bin/env python3
"""
PostToolUse hook: warn when a presentation-layer ``ui.table`` has no mobile
grid (card) view.

The bug this catches
---------------------
A wide ``ui.table`` renders as an HTML ``<table>`` at every viewport. On a phone
the columns — and every row-action button in the ``actions`` column — slide off
the right edge behind a horizontal scroll, so the table is effectively unusable.
The app's fix is to switch the table into Quasar *grid* mode below the ``lt.md``
breakpoint and render each row as a stacked card::

    from theme.tables.mobile_grid import enable_mobile_grid

    table = ui.table(columns=COLUMNS, rows=[], row_key='id').classes('w-full wiz-table')
    table.add_slot('body-cell-actions', ACTIONS)          # desktop cell
    enable_mobile_grid(table, COLUMNS, actions=ACTION_BUTTONS)

or, for the bespoke family tables, an inline ``:grid="Quasar.Screen.lt.md"`` prop
plus a hand-written ``item`` slot (match / user / tournament / equipment).

Detection
---------
Runs *after* the file is on disk, so the whole file is visible (an Edit fragment
would miss a later ``.props``/``enable_mobile_grid`` call). Using the AST it finds
every ``ui.table(...)`` call and treats it as compliant when any of these hold:

  * the table's construction statement contains ``Quasar.Screen`` (inline
    ``:grid`` prop in the ``.classes(...).props(...)`` chain);
  * a later ``<name>.props(...)`` on the same table carries ``Quasar.Screen``;
  * ``enable_mobile_grid(<table>, ...)`` is called on it (named or inline).

Opt out for a table that legitimately should stay a table (a narrow 2-column
reference, say) with a ``mobile-grid: exempt`` (or ``noqa: mobile-grid``) comment
on the ``ui.table`` line or the line above.

Only presentation-layer files (pages/, theme/, frontend.py) are inspected.
Exits 2 with guidance on a hit; exits 0 otherwise (fail open — non-Python,
unreadable, unparseable, or no ``ui.table`` present).
"""

import ast
import json
import re
import sys

_EXEMPT_RE = re.compile(r"mobile-grid:\s*exempt|noqa:\s*mobile-grid", re.IGNORECASE)


def is_presentation(path: str) -> bool:
    norm = path.replace("\\", "/")
    return "/pages/" in norm or "/theme/" in norm or norm.endswith("frontend.py")


def _is_ui_table(node: ast.Call) -> bool:
    """True for `ui.table(...)` calls."""
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
    """Source text of the name a ui.table is assigned to, e.g. 'table' or
    'self.table'. None when the table isn't a simple assignment target."""
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

    # enable_mobile_grid(<first-arg>, ...) — collect first-arg source texts, and
    # remember the call nodes so an inline ui.table argument counts too.
    helper_first_args: set[str] = set()
    helper_calls: list[ast.Call] = []
    # <base>.props(<... 'Quasar.Screen' ...>) — collect the base source texts.
    grid_prop_bases: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name == "enable_mobile_grid":
            helper_calls.append(node)
            if node.args:
                helper_first_args.add(_seg(source, node.args[0]))
        elif name == "props":
            args_src = " ".join(_seg(source, a) for a in node.args)
            if "Quasar.Screen" in args_src and isinstance(fn, ast.Attribute):
                grid_prop_bases.add(_seg(source, fn.value))

    def _in_helper(call: ast.Call) -> bool:
        for hc in helper_calls:
            for sub in ast.walk(hc):
                if sub is call:
                    return True
        return False

    violations: list[str] = []
    seen: set[int] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_ui_table(node)):
            continue
        if node.lineno in seen:
            continue
        seen.add(node.lineno)

        # Opt-out comment on the table line or the line just above.
        window = "\n".join(lines[max(0, node.lineno - 2): node.lineno])
        if _EXEMPT_RE.search(window):
            continue

        stmt = _enclosing_stmt(node, parents)
        stmt_src = _seg(source, stmt) if stmt is not None else ""
        target = _assign_target(stmt, source) if stmt is not None else None

        compliant = (
            "Quasar.Screen" in stmt_src               # inline :grid prop in chain
            or _in_helper(node)                       # enable_mobile_grid(ui.table(...))
            or (target is not None and target in helper_first_args)
            or (target is not None and target in grid_prop_bases)
        )
        if compliant:
            continue

        violations.append(
            f"MOBILE-GRID MISSING in '{file_path}' (line {node.lineno}):\n"
            f"  This ui.table has no mobile grid/card view, so on a phone its "
            f"columns and row-action\n"
            f"  buttons scroll off-screen. Add the app's responsive card:\n"
            f"    from theme.tables.mobile_grid import enable_mobile_grid\n"
            f"    table = ui.table(columns=COLUMNS, rows=[], row_key='id').classes('w-full wiz-table')\n"
            f"    # ...body-cell-* slots, event handlers...\n"
            f"    enable_mobile_grid(table, COLUMNS, actions=ACTION_BUTTONS_HTML)\n"
            f"  (pass field_slots={{'status': '<q-badge...>'}} for badge/chip columns).\n"
            f"  A family table may instead use an inline :grid=\"Quasar.Screen.lt.md\" prop\n"
            f"  plus a hand-written 'item' slot. If this table should stay a table on\n"
            f"  mobile, add a `# mobile-grid: exempt` comment. See docs/reference/frontend.md."
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
