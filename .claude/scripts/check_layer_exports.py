#!/usr/bin/env python3
"""
PostToolUse hook: new services/repositories must be exported from __init__.py.

CLAUDE.md "Adding a new feature" step 4 requires exporting from each package's
__init__.py. When a Service/Repository class is added to
application/services/ or application/repositories/, this verifies the class is
both imported and listed in __all__ in the sibling __init__.py.

A ``*_service.py``/``*_repository.py`` module with **no** matching class but
public top-level functions (the ``discord_queue`` shape — e.g.
``oauth_handoff_service.py``) must instead have its module *stem* imported
(``from . import stem``) and listed in __all__.

Underscore-prefixed modules are skipped outright: ``_crew_repository.py``,
``_base.py`` and ``_tenant.py`` are package-private by convention, holding shared
bases and helpers for their siblings rather than public API.

Known miss, deliberately kept:
acronym-cased primaries (``SpeedGamingETLService`` vs the filename-derived
``SpeedgamingEtlService``) are invisible to both branches.

Exit 0 = exported / not applicable; exit 2 = missing export (stderr explains).
"""

import ast
import json
import os
import sys

from _hook_paths import anchor

anchor()  # hooks inherit the session's shell cwd; pin paths to the repo


def is_conventional(norm: str) -> bool:
    """A ``*_service.py`` / ``*_repository.py`` module — the named-class shape."""
    return norm.endswith("_service.py") or norm.endswith("_repository.py")


def package_for(norm: str) -> str | None:
    """Return the package dir for an eligible service/repository source path.

    Any public module under the two layers counts, not only the ``*_service.py``
    / ``*_repository.py`` filenames. The suffix rule matched the class-bearing
    modules and missed everything else — the mixins, the helper modules — which
    is where the export was actually forgotten: `notification_links.py`,
    `discord_member_events.py`, `async_qualifier_expiry.py` and the station mixin
    each needed a follow-up commit to export it, and the hook was silent for all
    four because none of the filenames ends in `_service.py`.
    """
    base = os.path.basename(norm)
    if base == "__init__.py" or not base.endswith(".py"):
        return None
    # An underscore-prefixed module is package-private by convention
    # (``_crew_repository.py``, ``_base.py``, ``_tenant.py``): whatever it defines
    # is a shared base or helper for its siblings, deliberately *not* part of the
    # package's public surface. Demanding a ``Generic[T]`` base be re-exported
    # would invert the convention.
    if base.startswith("_"):
        return None
    slashed = f"/{norm}"
    if (
        "/application/services/" not in slashed
        and "/application/repositories/" not in slashed
    ):
        return None
    package_dir = os.path.dirname(norm)
    # The same convention one level up: a `_bracket/`-style private subpackage.
    if any(part.startswith("_") for part in package_dir.split("/")[-2:]):
        return None
    init_path = os.path.join(package_dir, "__init__.py")
    if not os.path.isfile(init_path):
        return None
    # A barrel that imports its siblings dynamically already exports everything;
    # there is no literal name to look for. `bracket_engines/` does this, and
    # session-start.sh honours the same convention.
    try:
        with open(init_path, encoding="utf-8") as fh:
            if "iter_modules" in fh.read():
                return None
    except OSError:
        return None
    return package_dir


def public_top_level_names(source: str) -> set[str]:
    """Public classes and functions defined at module level."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }


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


def module_shape(source: str) -> tuple[bool, bool]:
    """(defines a public *Service/*Repository class, defines a public function)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return True, False  # fail open: pretend class-bearing so no branch fires
    has_layer_class = any(
        isinstance(n, ast.ClassDef)
        and not n.name.startswith("_")
        and (n.name.endswith("Service") or n.name.endswith("Repository"))
        for n in tree.body
    )
    has_public_fn = any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not n.name.startswith("_")
        for n in tree.body
    )
    return has_layer_class, has_public_fn


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
            source = fh.read()
    except OSError:
        sys.exit(0)
    cls = primary_class(source, expected)

    stem = os.path.basename(norm)[:-3]
    accepted = {stem}
    if cls is None:
        has_layer_class, has_public_fn = module_shape(source)
        if is_conventional(norm):
            if has_layer_class or not has_public_fn:
                sys.exit(0)  # acronym-cased primary, or nothing exportable
            fix = f"Add `from . import {stem}` and list '{stem}' in __all__"
            what = f"functional module '{stem}'"
        else:
            # A module outside the naming convention: a mixin, a helper, a set of
            # functions. Any one of its public names standing in for it is the
            # export — `notification_links` by stem, `StationAssignmentMixin` by
            # class — so accept whichever the package chose.
            names = public_top_level_names(source)
            if not names:
                sys.exit(0)
            accepted |= names
            fix = (
                f"Add `from .{stem} import <name>` (or `from . import {stem}`) "
                f"and list it in __all__"
            )
            what = f"module '{stem}'"
    else:
        accepted = {cls}
        fix = f"Add `from .{stem} import {cls}` and list it in __all__"
        what = cls

    init_path = os.path.join(package_dir, "__init__.py")
    try:
        with open(init_path, encoding="utf-8") as fh:
            imported, all_names = exported_names(fh.read())
    except OSError:
        sys.exit(0)

    if not (accepted & imported & all_names):
        print(
            f"EXPORT CONVENTION VIOLATION in '{file_path}':\n"
            f"  {what} is defined but not exported from '{init_path}'.\n"
            f"  {fix} (the discord_queue convention for function-only modules).",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
