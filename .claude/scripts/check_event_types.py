#!/usr/bin/env python3
"""
PostToolUse hook: keep the EventType external contract consistent.

CLAUDE.md > Event publishing: ``EventType`` names are an external contract —
webhook subscribers match on them, and ``EventType.ALL`` drives the webhook UI
multiselect + validation. Two failure modes, both silent at runtime:

1. **Registry drift** (when editing ``application/events/event_types.py``): a
   new constant that isn't added to ``ALL`` can be published but never
   subscribed to (the UI won't offer it and ``is_valid`` rejects it); an ``ALL``
   entry with no matching constant is a NameError only at import of the set.
   Also flags two constants sharing one string value (a copy-paste slip that
   merges two events on the wire).

2. **Literal event names** (any other non-test file): ``Event.create('match.x',
   ...)`` with a string literal bypasses the registry entirely — the event is
   published but invisible to the UI/validation. Requires an ``EventType.*``
   constant, mirroring what check_audit_actions.py does for audit actions.

Exit 0 = clean / not applicable; exit 2 = violation (stderr explains).
"""

import ast
import json
import sys


def check_registry(tree: ast.AST) -> list[str]:
    """Consistency of the EventType class in event_types.py."""
    cls = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "EventType"),
        None,
    )
    if cls is None:
        return []

    constants: dict[str, str] = {}
    all_names: set[str] | None = None
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            name, value = stmt.targets[0].id, stmt.value
            if name == "WILDCARD":
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str) and name.isupper():
                constants[name] = value.value
        target = None
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            target = stmt.target.id
            value = stmt.value
        elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            target = stmt.targets[0].id
            value = stmt.value
        if target == "ALL" and isinstance(value, ast.Call) and value.args:
            inner = value.args[0]
            if isinstance(inner, (ast.Set, ast.Tuple, ast.List)):
                all_names = {e.id for e in inner.elts if isinstance(e, ast.Name)}

    problems = []
    if all_names is None:
        return problems  # shape changed beyond what this check understands: fail open

    missing = sorted(set(constants) - all_names)
    if missing:
        problems.append(
            f"EventType constant(s) not listed in EventType.ALL: {', '.join(missing)}.\n"
            f"  An event absent from ALL can be published but never subscribed to\n"
            f"  (the webhook UI multiselect and is_valid() are driven by ALL)."
        )
    unknown = sorted(all_names - set(constants))
    if unknown:
        problems.append(
            f"EventType.ALL references undefined constant(s): {', '.join(unknown)}."
        )
    by_value: dict[str, list[str]] = {}
    for name, value in constants.items():
        by_value.setdefault(value, []).append(name)
    for value, names in sorted(by_value.items()):
        if len(names) > 1:
            problems.append(
                f"Duplicate event name {value!r} shared by: {', '.join(sorted(names))}.\n"
                f"  Two constants with one wire value merge two events for subscribers."
            )
    return problems


def check_literals(tree: ast.AST) -> list[tuple[int, str]]:
    """Event.create('literal', ...) calls outside the registry."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "create"
            and isinstance(func.value, ast.Name)
            and func.value.id == "Event"
        ):
            continue
        arg = None
        for kw in node.keywords:
            if kw.arg == "event_type":
                arg = kw.value
        if arg is None and node.args:
            arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            out.append((node.lineno, arg.value))
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
    if "/.claude/" in norm or "/tests/" in norm:
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

    if norm.endswith("application/events/event_types.py"):
        problems = check_registry(tree)
        if problems:
            for problem in problems:
                print(f"EVENT REGISTRY VIOLATION in '{file_path}':\n  {problem}", file=sys.stderr)
            sys.exit(2)
        sys.exit(0)

    literals = check_literals(tree)
    if literals:
        for line, literal in literals:
            print(
                f"EVENT CONVENTION VIOLATION in '{file_path}' (line {line}):\n"
                f"  Event.create() called with a string-literal event name: {literal!r}\n"
                f"  Use an EventType.* constant (add it to EventType AND EventType.ALL in\n"
                f"  application/events/event_types.py if it's a new event — names are an\n"
                f"  external webhook contract).",
                file=sys.stderr,
            )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
