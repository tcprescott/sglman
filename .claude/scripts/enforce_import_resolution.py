#!/usr/bin/env python3
"""
Stop + PostToolUse hook: flag an import of a name a first-party module does not provide.

Catches an ImportError-at-startup left behind by a rename/refactor (commit 5edab8e):
a `from PKG import old_name` whose target module no longer defines `old_name`. Such a
stale import usually sits in a file the session never touched, so the load-bearing
mode is the whole-repo sweep at Stop; the PostToolUse mode gives fast feedback on the
one file just edited.

Only FIRST-PARTY modules are resolved — those whose top segment maps to a repo file or
directory (flat layout, `package-mode = false`, so detection is by path existence, not
by __init__.py). Third-party / stdlib imports are skipped. The check fails open on
every ambiguity: an unresolved module, a `from x import *` or module-level __getattr__
in the target, a parse/read error, a namespace-package name, a relative import that
escapes the repo, or a path under /.claude/.

Stop event:       no tool_input.file_path -> sweep every .py under the repo root.
PostToolUse event: tool_input.file_path present -> check just that file.
Exit 0 = clean / fail-open; exit 2 = unresolved first-party import (stderr explains).
"""

import ast
import json
import os
import subprocess
import sys


_PROVIDED_CACHE: dict[str, frozenset[str] | None] = {}


def repo_root() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return os.getcwd()


def is_first_party_top(top: str, root: str) -> bool:
    return os.path.isdir(os.path.join(root, top)) or os.path.isfile(
        os.path.join(root, top + ".py")
    )


def resolve_module(dotted: str, root: str) -> tuple[str | None, str | None]:
    """Resolve a dotted module to (path, kind) where kind is module/package/namespace."""
    parts = [p for p in dotted.split(".") if p]
    if not parts:
        return None, None
    py = os.path.join(root, *parts) + ".py"
    if os.path.isfile(py):
        return py, "module"
    pkg_init = os.path.join(root, *parts, "__init__.py")
    if os.path.isfile(pkg_init):
        return pkg_init, "package"
    d = os.path.join(root, *parts)
    if os.path.isdir(d):
        return d, "namespace"
    return None, None


def _add_target(target: ast.AST, names: set[str]) -> None:
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _add_target(elt, names)
    elif isinstance(target, ast.Starred):
        _add_target(target.value, names)


def _module_level_names(tree: ast.Module) -> tuple[set[str], bool]:
    """Collect names bound at module level. Returns (names, fail_open).

    Descends through top-level control flow (try/if/for/while/with) so a
    conditionally-defined name still counts, but never into def/class bodies
    (those open a new scope). fail_open is True on a star import or __getattr__.
    """
    names: set[str] = set()
    fail_open = False
    all_entries: set[str] = set()

    def visit(stmts: list[ast.stmt]) -> None:
        nonlocal fail_open
        for s in stmts:
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(s.name)
                if s.name == "__getattr__":
                    fail_open = True
            elif isinstance(s, ast.ClassDef):
                names.add(s.name)
            elif isinstance(s, ast.Assign):
                for t in s.targets:
                    _add_target(t, names)
                    if isinstance(t, ast.Name) and t.id == "__all__":
                        all_entries.update(_string_elts(s.value))
            elif isinstance(s, ast.AnnAssign):
                _add_target(s.target, names)
                if (
                    isinstance(s.target, ast.Name)
                    and s.target.id == "__all__"
                    and s.value is not None
                ):
                    all_entries.update(_string_elts(s.value))
            elif isinstance(s, ast.Import):
                for a in s.names:
                    names.add(a.asname or a.name.split(".")[0])
            elif isinstance(s, ast.ImportFrom):
                for a in s.names:
                    if a.name == "*":
                        fail_open = True
                    else:
                        names.add(a.asname or a.name)
            elif isinstance(s, ast.Try):
                visit(s.body)
                for h in s.handlers:
                    visit(h.body)
                visit(s.orelse)
                visit(s.finalbody)
            elif isinstance(s, ast.If):
                visit(s.body)
                visit(s.orelse)
            elif isinstance(s, (ast.For, ast.AsyncFor, ast.While)):
                visit(s.body)
                visit(s.orelse)
            elif isinstance(s, (ast.With, ast.AsyncWith)):
                visit(s.body)

    visit(tree.body)
    names |= all_entries
    return names, fail_open


def _string_elts(node: ast.AST) -> set[str]:
    out: set[str] = set()
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for e in node.elts:
            if isinstance(e, ast.Constant) and isinstance(e.value, str):
                out.add(e.value)
    return out


def _submodule_names(directory: str) -> set[str]:
    out: set[str] = set()
    try:
        for entry in os.listdir(directory):
            full = os.path.join(directory, entry)
            if entry.endswith(".py") and entry != "__init__.py":
                out.add(entry[:-3])
            elif os.path.isdir(full) and not entry.startswith("."):
                out.add(entry)
    except OSError:
        pass
    return out


def provided_names(path: str, kind: str, root: str) -> frozenset[str] | None:
    """Names a resolved first-party target provides, or None to fail open."""
    if kind == "namespace":
        return None  # only submodules are importable; don't risk a false positive
    if path in _PROVIDED_CACHE:
        return _PROVIDED_CACHE[path]
    result: frozenset[str] | None
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
    except (OSError, SyntaxError, ValueError):
        result = None
    else:
        names, fail_open = _module_level_names(tree)
        if fail_open:
            result = None
        else:
            if kind == "package":
                names |= _submodule_names(os.path.dirname(path))
            result = frozenset(names)
    _PROVIDED_CACHE[path] = result
    return result


def _resolve_relative(rel_file: str, level: int, module: str | None, root: str) -> str | None:
    """Turn a relative import in rel_file into an absolute dotted module, or None."""
    pkg_parts = os.path.dirname(rel_file).replace("\\", "/").split("/")
    pkg_parts = [p for p in pkg_parts if p]
    if level - 1 > len(pkg_parts):
        return None  # escapes the repo root
    base = pkg_parts[: len(pkg_parts) - (level - 1)]
    if module:
        base = base + module.split(".")
    return ".".join(base) if base else None


def check_file(abs_path: str, rel_path: str, root: str) -> list[tuple[int, str, str]]:
    """Return (lineno, imported_name, module) for each unresolved first-party import."""
    try:
        with open(abs_path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=abs_path)
    except (OSError, SyntaxError, ValueError):
        return []  # fail open; check_syntax.py owns syntax errors

    violations: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                dotted = _resolve_relative(rel_path, node.level, node.module, root)
                if not dotted:
                    continue
            else:
                if not node.module:
                    continue
                top = node.module.split(".")[0]
                if not is_first_party_top(top, root):
                    continue
                dotted = node.module
            path, kind = resolve_module(dotted, root)
            if path is None:
                continue  # unresolved -> fail open
            provided = provided_names(path, kind, root)
            if provided is None:
                continue  # fail open
            for alias in node.names:
                if alias.name == "*":
                    continue
                if alias.name not in provided:
                    violations.append((node.lineno, alias.name, dotted))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if not is_first_party_top(top, root):
                    continue
                path, _ = resolve_module(alias.name, root)
                if path is None:
                    violations.append((node.lineno, alias.name, alias.name))
    return violations


def _walk_py(root: str) -> list[str]:
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in {".git", "__pycache__", ".claude"} and not d.startswith(".")
        ]
        for f in filenames:
            if f.endswith(".py"):
                out.append(os.path.join(dirpath, f))
    return out


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # also drains stdin

    root = repo_root()
    file_path = payload.get("tool_input", {}).get("file_path", "")

    if file_path:
        norm = file_path.replace("\\", "/")
        if not norm.endswith(".py") or "/.claude/" in norm:
            sys.exit(0)
        abs_path = os.path.abspath(file_path)
        rel = os.path.relpath(abs_path, root)
        violations = [(rel, ln, name, mod) for (ln, name, mod) in check_file(abs_path, rel, root)]
        if violations:
            for _rel, ln, name, mod in violations:
                print(
                    f"IMPORT RESOLUTION ERROR in '{_rel}' (line {ln}):\n"
                    f"  '{name}' is not provided by first-party module '{mod}'.\n"
                    f"  This is an ImportError at startup — the app will not boot.\n"
                    f"  Fix: import the correct name (it may have been renamed or moved) "
                    f"or update the call site.",
                    file=sys.stderr,
                )
            sys.exit(2)
        sys.exit(0)

    # Stop event: whole-repo sweep.
    all_violations: list[tuple[str, int, str, str]] = []
    for abs_path in _walk_py(root):
        rel = os.path.relpath(abs_path, root)
        for ln, name, mod in check_file(abs_path, rel, root):
            all_violations.append((rel, ln, name, mod))

    if all_violations:
        lines = "\n".join(
            f"  {rel}:{ln}  '{name}' not in '{mod}'" for rel, ln, name, mod in all_violations
        )
        print(
            f"IMPORT RESOLUTION SWEEP found {len(all_violations)} unresolved "
            f"first-party import(s):\n"
            f"{lines}\n"
            f"  Each crashes the app at import (ImportError at startup). Fix each to "
            f"the current export name (a rename/refactor likely left it stale).",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
