"""Guards against re-introducing a per-test rebuild of an expensive fixture.

The suite's wall time is dominated by fixture *setup*, not by assertions: before
commit f0ceb4b, 84% of the run (166s of 197s) was setup, and the single biggest
cause was ~400 API tests each rebuilding an identical, immutable FastAPI app.
Test *count* is close to free by comparison — see docs/development.md >
"Keeping it fast".

Two shapes are therefore built once per process and shared:

* ``build_api_app()`` (``tests/api_helpers.py``) — mounting the API router costs
  ~200ms, because ``include_router`` resolves each route's dependency graph and
  builds a Pydantic response model per endpoint. Exposed as the ``app`` fixture
  in ``tests/conftest.py``.
* ``_schema_sql()`` (``tests/conftest.py``) — the CREATE TABLE script, rendered
  once and replayed by the ``db`` fixture instead of re-derived from model
  metadata on all ~1450 DB-backed setups.

The checks here are **structural, not timing-based** — a wall-clock budget is
flaky on shared CI runners, and a flaky guard gets deleted. Two kinds: identity
assertions that the caches are still in place, and a single AST pass over
``tests/`` for the shapes that were removed.

``.claude/scripts/check_fixture_cost.py`` blocks the same shapes at write time,
but only for edits Claude Code makes; this module is the layer that binds an IDE
edit or an externally-authored PR, so it is the one that holds the line.
"""

import ast
import functools
import pathlib

import pytest

TESTS_DIR = pathlib.Path(__file__).resolve().parent

#: The one sanctioned builder of the full API app, and the conftest that shares it.
APP_BUILDER_FILES = {'api_helpers.py', 'conftest.py'}

USE_SHARED_APP = (
    'Use the shared `app` fixture in tests/conftest.py (it returns the cached '
    'build_api_app() from tests/api_helpers.py). A throwaway bare FastAPI() for '
    'middleware/error-handler coverage is fine — mounting the API router on it is not.'
)


@functools.cache
def _parsed_test_modules() -> tuple[tuple[pathlib.Path, ast.Module], ...]:
    """Every module under tests/, parsed once and shared by the checks below."""
    return tuple(
        (path, ast.parse(path.read_text(encoding='utf-8'), str(path)))
        for path in sorted(TESTS_DIR.rglob('*.py'))
    )


def _rel(path: pathlib.Path) -> str:
    return str(path.relative_to(TESTS_DIR.parent))


def _is_fixture(node: ast.AST) -> bool:
    """True for a function decorated with pytest.fixture (bare or called)."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr == 'fixture':
            return True
        if isinstance(target, ast.Name) and target.id == 'fixture':
            return True
    return False


def _mounts_api_router(call: ast.Call) -> bool:
    """True for ``some_app.include_router(api.router, ...)``."""
    if not isinstance(call.func, ast.Attribute) or call.func.attr != 'include_router':
        return False
    if not call.args:
        return False
    first = call.args[0]
    if isinstance(first, ast.Attribute) and first.attr == 'router':
        return True
    return isinstance(first, ast.Name) and first.id == 'router'


def _is_bare_app_alias(node: ast.AST) -> bool:
    """True for a fixture whose entire body is ``return build_api_app()``.

    Narrow on purpose: a fixture that *assembles* a context (tokens, tenants,
    rows) and happens to include the cached app in its return value is
    legitimate and costs nothing — only the trivial alias is flagged, which is
    the shape a re-pasted local ``app`` fixture takes once it is renamed.
    """
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    value = body[0].value
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == 'build_api_app'
    )


@functools.cache
def _scan() -> dict:
    """One walk over the parsed tree, collecting every location the checks need.

    Kept to a single pass so this module stays cheap — the whole point of the
    guard is that the suite is fast.
    """
    found = {'app_fixtures': [], 'router_mounts': [], 'schema_calls': [], 'app_aliases': []}
    for path, tree in _parsed_test_modules():
        is_builder = path.name in APP_BUILDER_FILES
        where = _rel(path)
        for node in ast.walk(tree):
            if _is_fixture(node) and not is_builder:
                if node.name == 'app':
                    found['app_fixtures'].append(f'{where}:{node.lineno}')
                elif _is_bare_app_alias(node):
                    found['app_aliases'].append(f'{where}:{node.lineno} ({node.name})')
            elif isinstance(node, ast.Call):
                if not is_builder and _mounts_api_router(node):
                    found['router_mounts'].append(f'{where}:{node.lineno}')
                if path.name != 'conftest.py' and isinstance(node.func, ast.Attribute) \
                        and node.func.attr == 'generate_schemas':
                    found['schema_calls'].append(f'{where}:{node.lineno}')
    return {key: tuple(value) for key, value in found.items()}


class TestCachesAreIntact:
    """Identity implies the cache survived — no timing involved."""

    def test_build_api_app_is_cached(self):
        from tests.api_helpers import build_api_app

        assert hasattr(build_api_app, 'cache_info'), (
            'build_api_app() lost its @functools.cache (tests/api_helpers.py). '
            'Rebuilding the API app per test cost more than every DB query in the '
            'suite combined — 135s of the old 207s run.'
        )
        assert build_api_app() is build_api_app(), (
            'build_api_app() returned two different app objects, so it is being '
            'rebuilt per call. Restore the @functools.cache in tests/api_helpers.py.'
        )

    async def test_schema_sql_is_cached(self, db):
        from tests.conftest import _schema_sql

        assert hasattr(_schema_sql, 'cache_info'), (
            '_schema_sql() lost its @functools.cache (tests/conftest.py). The '
            'CREATE TABLE script is a pure function of the models, so re-deriving '
            'it on each of the ~1450 DB-backed setups is wasted work.'
        )
        assert _schema_sql() is _schema_sql(), (
            '_schema_sql() re-rendered the schema instead of returning the cached '
            'script. Restore the @functools.cache in tests/conftest.py.'
        )


class TestNoPerTestRebuilds:
    """AST scan of tests/ for the shapes commit f0ceb4b removed."""

    def test_only_conftest_defines_an_app_fixture(self):
        offenders = _scan()['app_fixtures']
        assert not offenders, (
            'A local `app` fixture shadows the shared one: ' + ', '.join(offenders)
            + '. Two modules re-pasted this fixture once already and bypassed the '
              'cache entirely. ' + USE_SHARED_APP
        )

    def test_no_test_mounts_the_api_router(self):
        offenders = _scan()['router_mounts']
        assert not offenders, (
            'A test mounts the API router on its own app: ' + ', '.join(offenders)
            + '. That costs ~200ms per test and the result is immutable. '
            + USE_SHARED_APP
        )

    def test_no_test_regenerates_the_schema(self):
        offenders = _scan()['schema_calls']
        assert not offenders, (
            'A test re-derives the schema from model metadata: ' + ', '.join(offenders)
            + '. Depend on the `db` fixture in tests/conftest.py — it replays the '
              'script rendered once by _schema_sql().'
        )

    def test_no_fixture_is_a_bare_alias_for_the_cached_app(self):
        offenders = _scan()['app_aliases']
        assert not offenders, (
            'A fixture is a bare alias for the cached app: ' + ', '.join(offenders)
            + '. That is the shared `app` fixture from tests/conftest.py under a '
              'different name — request `app` instead.'
        )


def test_ast_scan_actually_sees_the_test_tree():
    """A broken scan would make every check above pass vacuously."""
    parsed = _parsed_test_modules()
    assert len(parsed) > 50, f'only {len(parsed)} modules parsed under {TESTS_DIR}'
    assert any(path.name == 'conftest.py' for path, _ in parsed)


@pytest.mark.parametrize('name', ['app', 'db'])
def test_shared_fixtures_still_live_in_conftest(name):
    """The failure messages above steer people here; fail loudly if one is renamed."""
    conftest = next(
        tree for path, tree in _parsed_test_modules()
        if path == TESTS_DIR / 'conftest.py'
    )
    assert any(
        _is_fixture(node) and node.name == name for node in ast.walk(conftest)
    ), f'tests/conftest.py no longer defines a `{name}` fixture'
