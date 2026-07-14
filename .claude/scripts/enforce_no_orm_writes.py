#!/usr/bin/env python3
"""
PostToolUse hook: block direct ORM writes from the presentation layer.

CLAUDE.md allows read-only ORM lookups in pages/ and theme/ for display, but
*writes* must go through a service (which calls a repository). This inspects the
resulting file after a Write/Edit and rejects a write whose call chain is rooted
at a known Tortoise model class — e.g. `Match.create(...)` or
`Tournament.filter(id=x).delete()`. Reads such as `.filter().order_by()` are
left alone because they don't terminate in a write method.

Exit 0 = clean / not applicable; exit 2 = violation (stderr explains).
"""

import ast
import json
import os
import sys


WRITE_TERMINALS = {
    "create",
    "bulk_create",
    "get_or_create",
    "update_or_create",
    "bulk_update",
    "update",
    "delete",
    "save",
}


def is_presentation(path: str) -> bool:
    norm = path.replace("\\", "/")
    return "/pages/" in norm or "/theme/" in norm or norm.endswith("frontend.py")


def find_models_source(start_path: str) -> str | None:
    """Locate the model definitions: the ``models/`` package or a ``models.py``.

    Returns the package directory when models are split into ``models/*.py``, or
    the single file when it's still ``models.py``. ``None`` if neither is found
    while walking up from ``start_path``.
    """
    d = os.path.dirname(os.path.abspath(start_path))
    while True:
        pkg = os.path.join(d, "models")
        if os.path.isfile(os.path.join(pkg, "__init__.py")):
            return pkg
        single = os.path.join(d, "models.py")
        if os.path.isfile(single):
            return single
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _model_names_in(source: str) -> set[str]:
    try:
        with open(source, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError):
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = (
                    base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", None)
                )
                if base_name == "Model":
                    names.add(node.name)
                    break
    return names


def load_model_names(models_source: str) -> set[str]:
    """Model class names, whether ``models_source`` is a package dir or a file."""
    if os.path.isdir(models_source):
        names: set[str] = set()
        for entry in sorted(os.listdir(models_source)):
            if entry.endswith(".py"):
                names |= _model_names_in(os.path.join(models_source, entry))
        return names
    return _model_names_in(models_source)


def root_name(expr: ast.AST) -> str | None:
    """Walk a receiver chain (nested Call/Attribute) down to its root Name id."""
    while isinstance(expr, (ast.Attribute, ast.Call)):
        expr = expr.func if isinstance(expr, ast.Call) else expr.value
    return expr.id if isinstance(expr, ast.Name) else None


def find_violations(tree: ast.AST, models: set[str]) -> list[tuple[int, str, str]]:
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in WRITE_TERMINALS:
            continue
        root = root_name(func.value)
        if root in models:
            out.append((node.lineno, root, func.attr))
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

    models_source = find_models_source(file_path)
    if not models_source:
        sys.exit(0)
    models = load_model_names(models_source)
    if not models:
        sys.exit(0)

    violations = find_violations(tree, models)
    if violations:
        for line, model, method in violations:
            print(
                f"ARCHITECTURE VIOLATION in '{file_path}' (line {line}):\n"
                f"  Direct ORM write from the presentation layer: {model}.{method}(...)\n"
                f"  pages/ and theme/ may read for display, but must not write to the DB.\n"
                f"  Fix: move this write into a service method (which calls the repository).",
                file=sys.stderr,
            )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
