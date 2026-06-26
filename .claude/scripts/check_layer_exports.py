#!/usr/bin/env python3
"""
PostToolUse hook: new services/repositories must be exported from __init__.py.

CLAUDE.md "Adding a new feature" step 4 requires exporting from each package's
__init__.py. When a Service/Repository class is added to
application/services/ or application/repositories/, this verifies the class is
both imported and listed in __all__ in the sibling __init__.py.

Exit 0 = exported / not applicable; exit 2 = missing export (stderr explains).
"""

import ast
import json
import os
import sys


def package_for(norm: str) -> str | None:
    """Return the package dir for an eligible service/repository source path."""
    base = os.path.basename(norm)
    if base == "__init__.py" or not base.endswith(".py"):
        return None
    if norm.endswith("_service.py") and "application/services/" in f"/{norm}":
        return os.path.dirname(norm)
    if norm.endswith("_repository.py") and "application/repositories/" in f"/{norm}":
        return os.path.dirname(norm)
    return None


def expected_class_name(norm: str) -> str:
    """snake_case filename -> PascalCase primary class (discord_service -> DiscordService)."""
    stem = os.path.basename(norm)[:-3]
    return "".join(part.capitalize() for part in stem.split("_"))


def primary_class(source: str, expected: str) -> str | None:
    """The filename-derived class, if the module actually defines it.

    Only the primary class is required to be exported — sibling/internal classes
    (e.g. MockDiscordService) are intentionally not in __all__.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None  # check_syntax.py owns syntax-error reporting
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == expected:
            return node.name
    return None


def exported_names(init_source: str) -> tuple[set[str], set[str]]:
    """Return (imported_names, __all__ entries) from an __init__.py source."""
    imported: set[str] = set()
    all_names: set[str] = set()
    try:
        tree = ast.parse(init_source)
    except SyntaxError:
        return imported, all_names

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                all_names.add(elt.value)
    return imported, all_names


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    norm = file_path.replace("\\", "/")
    package_dir = package_for(norm)
    if package_dir is None:
        sys.exit(0)

    expected = expected_class_name(norm)
    try:
        with open(file_path, encoding="utf-8") as fh:
            cls = primary_class(fh.read(), expected)
    except OSError:
        sys.exit(0)
    if cls is None:
        sys.exit(0)

    init_path = os.path.join(package_dir, "__init__.py")
    try:
        with open(init_path, encoding="utf-8") as fh:
            imported, all_names = exported_names(fh.read())
    except OSError:
        sys.exit(0)

    if cls not in imported or cls not in all_names:
        print(
            f"EXPORT CONVENTION VIOLATION in '{file_path}':\n"
            f"  {cls} is defined but not exported from '{init_path}'.\n"
            f"  Add `from .{os.path.basename(norm)[:-3]} import {cls}` and "
            f"list it in __all__.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
