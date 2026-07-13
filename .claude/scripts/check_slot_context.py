#!/usr/bin/env python3
"""
PostToolUse hook: warn when a background-task coroutine calls NiceGUI UI
functions without restoring a slot context.

The bug this catches
---------------------
A coroutine handed to ``background_tasks.create(...)`` runs with an empty slot
stack. Any ``ui.*`` call inside it (``ui.notify``, element creation, navigation,
``ui.run_javascript`` …) then raises::

    RuntimeError: The current slot cannot be determined because the slot stack
    for this task is empty.

The fix (per CLAUDE.md) is to capture ``context.client`` at the call site and
restore it inside the coroutine with a **sync** ``with`` block. In NiceGUI 3.x
``Client`` implements ``__enter__``/``__exit__`` only (no ``__aenter__``), so
``async with client:`` raises ``TypeError`` — the guard must be sync ``with``::

    table.on('evt', lambda e: background_tasks.create(handle(e.args, context.client)))

    async def handle(row, client):
        with client:
            ...
            ui.notify('Done', color='positive')

Detection
---------
Runs *after* the file is on disk (full file available, so the call site and the
coroutine body are both visible even for fragment Edits). Using the AST it:

  1. Finds every ``background_tasks.create(fn(...))`` and resolves ``fn``.
  2. For each locally-defined async ``fn``, flags any ``ui.*(...)`` call that is
     NOT lexically inside a sync ``with <name>:`` block (the fix pattern). Only
     sync ``with`` counts: ``Client`` is sync-only, so ``async with client:``
     would itself raise ``TypeError`` and is not accepted. An httpx-style
     ``async with httpx.AsyncClient() as c:`` is a Call, not a bare Name, so it
     does not count as a guard either.

Only presentation-layer files (pages/, theme/, frontend.py) are inspected.
Exits 2 with guidance on a hit; exits 0 otherwise (fail open — non-Python,
unreadable, unparseable, or no coroutine body to inspect).
"""

import ast
import json
import sys


def is_presentation(path: str) -> bool:
    norm = path.replace("\\", "/")
    return "/pages/" in norm or "/theme/" in norm or norm.endswith("frontend.py")


def _is_background_create(node: ast.Call) -> bool:
    """True for `background_tasks.create(...)` calls."""
    fn = node.func
    return (
        isinstance(fn, ast.Attribute)
        and fn.attr == "create"
        and isinstance(fn.value, ast.Name)
        and fn.value.id == "background_tasks"
    )


def _coroutine_name(call: ast.Call) -> str | None:
    """Name of the coroutine being scheduled: `create(foo(...))` -> 'foo'."""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
        return arg.func.id
    return None


def _ui_target(call: ast.Call) -> str | None:
    """Return a label for a `ui.*` call (incl. `ui.navigate.to`), else None."""
    fn = call.func
    if not isinstance(fn, ast.Attribute):
        return None
    # Walk the attribute chain down to its root Name.
    root = fn
    parts = []
    while isinstance(root, ast.Attribute):
        parts.append(root.attr)
        root = root.value
    if isinstance(root, ast.Name) and root.id == "ui":
        return "ui." + ".".join(reversed(parts))
    return None


def _with_binds_name(node: ast.AST) -> bool:
    """True if a **sync** ``with`` binds a bare Name, e.g. `with client:`.

    The only correct fix is a sync ``with client:`` — NiceGUI's ``Client`` is a
    sync-only context manager (``__enter__``/``__exit__`` with no ``__aenter__``),
    so ``async with client:`` raises ``TypeError`` at runtime. An ``async with``
    guard is therefore deliberately NOT accepted (it would itself be a bug). An
    unrelated `with contextlib.suppress(...):` is a Call, not a bare Name, so it
    does not qualify and won't mask a missing slot guard.
    """
    if not isinstance(node, ast.With):
        return False
    return any(isinstance(item.context_expr, ast.Name) for item in node.items)


def _find_unguarded_ui_calls(func: ast.AST) -> list[tuple[int, str]]:
    """ui.* calls in `func` not inside a `with <name>:` block."""
    hits: list[tuple[int, str]] = []

    def walk(node: ast.AST, guarded: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef)):
                # A nested function defines its own slot scope; skip it here.
                continue
            child_guarded = guarded
            if _with_binds_name(child):
                child_guarded = True
            if isinstance(child, ast.Call) and not guarded:
                label = _ui_target(child)
                if label is not None:
                    hits.append((child.lineno, label))
            walk(child, child_guarded)

    walk(func, False)
    return hits


def check(source: str, file_path: str) -> list[str]:
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return []  # check_syntax.py owns this; fail open here.

    # Map every (async) function name to its node(s).
    async_defs: dict[str, list[ast.AsyncFunctionDef]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            async_defs.setdefault(node.name, []).append(node)

    # Collect coroutine names scheduled via background_tasks.create(...).
    scheduled: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_background_create(node):
            name = _coroutine_name(node)
            if name:
                scheduled.add(name)

    violations: list[str] = []
    seen: set[tuple[str, int]] = set()
    for name in sorted(scheduled):
        for func in async_defs.get(name, []):
            for line, label in _find_unguarded_ui_calls(func):
                key = (name, line)
                if key in seen:
                    continue
                seen.add(key)
                violations.append(
                    f"SLOT-CONTEXT RISK in '{file_path}' (line {line}):\n"
                    f"  '{name}' is run via background_tasks.create(...) but calls "
                    f"{label}(...) with no slot context.\n"
                    f"  In a background task the slot stack is empty, so this raises "
                    f"RuntimeError: 'The current slot cannot be determined...'.\n"
                    f"  Fix: capture context.client at the call site and restore it with a\n"
                    f"  sync `with` block (Client is sync-only; `async with` raises TypeError):\n"
                    f"    background_tasks.create({name}(..., context.client))\n"
                    f"    async def {name}(..., client):\n"
                    f"        with client:\n"
                    f"            ...  # {label}(...) and other ui.* calls go here\n"
                    f"  (from nicegui import context). See CLAUDE.md > NiceGUI patterns."
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
