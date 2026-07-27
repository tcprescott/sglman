#!/usr/bin/env python3
"""
PostToolUse hook: a feature flag must gate BOTH the UI and the service layer.

CLAUDE.md > Feature flags: gating a subsystem is two obligations, and doing only
the first is the failure mode this hook exists to stop:

1. **Hide it at the entry surfaces** — ``@protected_page(feature=…)`` /
   ``@public_page(feature=…)``, ``require_feature(...)`` on a REST router,
   ``FeatureFlag.X in live`` on an admin/home tab, an ``is_enabled`` skip in a
   worker. Without this the feature is visible where it should not be.
2. **Enforce it in the owning service** — ``@requires_feature(FeatureFlag.X)``
   (or ``ensure_enabled(FeatureFlag.X)``) on the service's public entry methods.
   Without this the *UI* hides the feature while every other caller — a new page,
   a Discord interaction handler, a worker, a router nobody remembered to mount
   behind ``require_feature`` — still reaches it. UI-only gating is not gating.

Each flag declares its owning ``service_modules`` in its ``FeatureFlagSpec``, so
the check is exact rather than heuristic.

Runs only when an edit could plausibly change the answer (the registry, the enum,
a declared service module, or a known entry surface), so it stays cheap.

Exit 0 = clean / not applicable; exit 2 = violation (stderr explains).
"""

import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Entry surfaces scanned for the "hidden in the UI" half.
ENTRY_SURFACE_GLOBS = (
    'pages/**/*.py',
    'theme/**/*.py',
    'api/**/*.py',
    'mcpserver/**/*.py',
    'middleware/*.py',
    'application/services/*_worker.py',
)

REGISTRY = REPO / 'application' / 'feature_flags.py'
ENUM = REPO / 'models' / 'enums.py'


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return ''


def _flag_members() -> list[str]:
    """FeatureFlag enum member names, from models/enums.py."""
    src = _read(ENUM)
    m = re.search(r'class FeatureFlag\b.*?(?=\nclass |\Z)', src, re.S)
    if not m:
        return []
    return re.findall(r'^\s{4}([A-Z][A-Z0-9_]*) = ', m.group(0), re.M)


def _specs() -> dict[str, dict]:
    """Parse the registry statically: member -> {service_modules}.

    Static parse rather than importing the package: the hook must run without a
    configured environment (importing models pulls in Tortoise + env vars).
    """
    tree = ast.parse(_read(REGISTRY) or 'pass', filename=str(REGISTRY))
    specs: dict[str, dict] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'FeatureFlagSpec'):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Attribute) and isinstance(first.value, ast.Name)
                and first.value.id == 'FeatureFlag'):
            continue
        entry: dict = {'service_modules': []}
        for kw in node.keywords:
            if kw.arg == 'service_modules':
                entry['service_modules'] = [
                    e.value for e in getattr(kw.value, 'elts', [])
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                ]
        specs[first.attr] = entry
    return specs


def _files_for(declared: str) -> list[Path]:
    """Resolve a declared service_modules entry (file or package prefix)."""
    target = REPO / declared
    if declared.endswith('/'):
        return sorted(p for p in target.rglob('*.py') if p.name != '__init__.py')
    return [target] if target.is_file() else []


def _guards_flag(source: str, member: str) -> bool:
    """Whether ``source`` enforces FeatureFlag.<member> at the service layer.

    Three accepted forms, because the right response to "off" differs by caller:
    a service should *refuse* (``@requires_feature`` / ``ensure_enabled`` raise
    ``FeatureDisabledError``), while a background worker should *skip* the tenant
    quietly — raising in a loop over tenants would be a bug, so a bare
    ``is_enabled`` guard is correct there. The hook checks that the module
    consults the flag, not which form it picked.
    """
    return bool(
        re.search(rf'@requires_feature\(\s*FeatureFlag\.{member}\b', source)
        or re.search(rf'ensure_enabled\(\s*FeatureFlag\.{member}\b', source)
        or re.search(rf'is_enabled\(\s*FeatureFlag\.{member}\b', source)
    )


def _entry_surface_hits(member: str) -> list[str]:
    """Files that hide FeatureFlag.<member> at an entry surface."""
    patterns = [
        rf'feature\s*=\s*FeatureFlag\.{member}\b',          # page decorator
        rf'require_feature\(\s*FeatureFlag\.{member}\b',      # REST router mount
        rf'FeatureFlag\.{member}\s+in\s+live\b',              # admin/home tab
        rf'is_enabled\(\s*FeatureFlag\.{member}\b',           # worker / dialog skip
    ]
    hits = []
    for glob in ENTRY_SURFACE_GLOBS:
        for path in REPO.glob(glob):
            if '/tests/' in path.as_posix():
                continue
            src = _read(path)
            if any(re.search(p, src) for p in patterns):
                hits.append(path.relative_to(REPO).as_posix())
    return hits


def audit() -> list[str]:
    members = _flag_members()
    specs = _specs()
    problems: list[str] = []

    for member in members:
        spec = specs.get(member)
        if spec is None:
            problems.append(
                f"FeatureFlag.{member} has no FeatureFlagSpec in application/feature_flags.py.\n"
                f"    An unregistered flag has no label/description, never appears on the\n"
                f"    admin Features tab or /platform, and so can never be turned on."
            )
            continue

        # --- half 1: hidden in the UI ------------------------------------
        if not _entry_surface_hits(member):
            problems.append(
                f"FeatureFlag.{member} is never gated at an entry surface.\n"
                f"    Nothing hides it, so the feature shows for tenants that lack it. Add one of:\n"
                f"      @protected_page('/path', feature=FeatureFlag.{member})   (a whole page)\n"
                f"      require_feature(FeatureFlag.{member})                    (a REST router mount)\n"
                f"      and FeatureFlag.{member} in live                         (an admin/home tab)\n"
                f"      is_enabled(FeatureFlag.{member})                         (a background worker)"
            )

        # --- half 2: enforced in the service -----------------------------
        declared = spec['service_modules']
        if not declared:
            problems.append(
                f"FeatureFlag.{member} declares no service_modules.\n"
                f"    Name the module(s) that own the feature in its FeatureFlagSpec so the\n"
                f"    service layer is verifiably enforcing it — UI-only gating means any\n"
                f"    caller without a gate (new page, Discord handler, worker, un-mounted\n"
                f"    router) still reaches the feature."
            )
            continue

        for entry in declared:
            files = _files_for(entry)
            if not files:
                problems.append(
                    f"FeatureFlag.{member} declares service_modules entry '{entry}',\n"
                    f"    which does not exist. Fix the path (or drop it) — a stale entry makes\n"
                    f"    this check vacuous."
                )
                continue
            if not any(_guards_flag(_read(f), member) for f in files):
                where = entry if entry.endswith('/') else files[0].relative_to(REPO).as_posix()
                problems.append(
                    f"FeatureFlag.{member} is not enforced in its own service ({where}).\n"
                    f"    Decorate the service's public entry methods — every mutation, plus the\n"
                    f"    top-level reads that return the feature's data:\n"
                    f"      from application.feature_flags import requires_feature\n"
                    f"      @requires_feature(FeatureFlag.{member})\n"
                    f"      async def do_the_thing(...): ...\n"
                    f"    The UI hiding the feature is not enough; the service must refuse it."
                )
    return problems


# An edit only changes the answer if it touches the registry, the enum, a
# declared service module, or an entry surface.
def _relevant(norm: str) -> bool:
    if norm.endswith(('application/feature_flags.py', 'models/enums.py')):
        return True
    if 'application/services/' in norm:
        return True
    return any(
        seg in norm
        for seg in ('/pages/', '/theme/', '/api/', '/mcpserver/', '/middleware/')
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = payload.get('tool_input', {}).get('file_path', '')
    if not file_path or not file_path.endswith('.py'):
        sys.exit(0)

    norm = file_path.replace('\\', '/')
    if '/.claude/' in norm or '/tests/' in norm or '/scripts/' in norm:
        sys.exit(0)
    if not _relevant(norm):
        sys.exit(0)

    problems = audit()
    if problems:
        print('FEATURE FLAG GATING VIOLATION:', file=sys.stderr)
        for problem in problems:
            print(f'  - {problem}', file=sys.stderr)
        print(
            '\n  Feature gating is two halves: hide it at the entry surfaces AND enforce it\n'
            '  in the owning service. See docs/features/feature-flags.md.',
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == '__main__':
    main()
