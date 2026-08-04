#!/usr/bin/env python3
"""
PreToolUse hook: block re-introduction of a per-test rebuild of an expensive,
immutable test fixture.

The suite's wall time is dominated by fixture setup, not assertions. Five shapes
have caused it in turn, all now built once per process and shared:

* a local ``FastAPI()`` with ``api.router`` mounted on it — ~200ms per test,
  because ``include_router`` resolves each route's dependency graph and builds a
  Pydantic response model per endpoint. Now ``build_api_app()`` in
  ``tests/api_helpers.py`` (``@functools.cache``), exposed as the ``app``
  fixture in ``tests/conftest.py``.
* ``Tortoise.generate_schemas()`` — re-derives the same CREATE TABLE script from
  model metadata on every DB-backed setup. Now ``_schema_sql()`` in
  ``tests/conftest.py``, rendered once and replayed.
* ``Tortoise.init()`` — ~15ms of it is ``_build_initial_querysets()`` rebuilding
  a filter map for all ~70 models; per test that was 60s of a 190s profiled run.
  Now once per worker, with each test restoring a template database.
* ``build_server()`` — ~230ms to derive a JSON schema per MCP tool, times the
  ~106 sessions in the suite. Now cached in ``tests/mcp/conftest.py``.
* ``seed_all()`` — ~1.5s per call. Now the ``seeded_db`` fixture, which
  snapshots the seeded database once per worker.

Every rule counts **net-new** occurrences (the idiom from
``check_dry_regressions.py``): the proposed content is compared against the
current on-disk content and the write is blocked only when the number of matches
*increases*, so rewriting or editing around an existing occurrence never blocks.
Both have a verified zero baseline in ``tests/`` today.

As a hook this fires only when Claude Code writes the file; ``scripts/guardrails.py``
replays it in CI over the diff. The load-bearing layer either way is
``tests/test_fixture_performance.py``, which asserts the same invariants (plus
the cache identity checks) against the finished tree rather than the diff.

Exit 0 = no net-new occurrence (or not applicable); exit 2 = a rebuild is being
re-introduced (stderr names the shared primitive to use instead).
"""

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from _hook_paths import anchor

anchor()  # hooks inherit the session's shell cwd; pin paths to the repo


def _norm(path: str) -> str:
    return "/" + path.replace("\\", "/").lstrip("/")


# ``test_fixture_performance.py`` is the pytest half of this guard: it names the
# banned shapes in its own prose and steers people away from them, so a content
# regex would flag it for describing what it forbids (the same self-reference
# gotcha the ``/.claude/`` skip exists for). Its AST scan is what polices it.
SELF = frozenset({"test_fixture_performance.py"})


def in_tests(norm: str, *, allow: frozenset = frozenset()) -> bool:
    return "/tests/" in norm and os.path.basename(norm) not in (allow | SELF)


def in_tests_except(norm: str, *allowed_suffixes: str) -> bool:
    """Like ``in_tests`` but allows by path tail, so one conftest can be named."""
    if "/tests/" not in norm or os.path.basename(norm) in SELF:
        return False
    return not any(norm.endswith(f"/tests/{suffix}") for suffix in allowed_suffixes)


@dataclass
class Rule:
    name: str
    applies: Callable[[str], bool]
    pattern: re.Pattern
    message: str
    # Optional second signal that must also be present in the proposed content.
    # Guard A keys on *mounting the router*, not on constructing an app: several
    # test modules legitimately build a bare ``FastAPI()`` to exercise middleware
    # and error handlers, and must not trip.
    requires: Optional[re.Pattern] = None


RULES = [
    Rule(
        "local-api-app",
        lambda n: in_tests(n, allow=frozenset({"conftest.py", "api_helpers.py"})),
        re.compile(r"include_router\(\s*api\.router\b"),
        "A test is mounting api.router on its own FastAPI app.\n"
        "  That costs ~200ms per test — include_router resolves every route's\n"
        "  dependency graph and builds a Pydantic response model per endpoint —\n"
        "  and the result is immutable, so ~400 API tests were rebuilding an\n"
        "  identical app (135s of the old 207s suite).\n"
        "  Use the shared `app` fixture in tests/conftest.py, which returns the\n"
        "  cached build_api_app() from tests/api_helpers.py. A test that needs a\n"
        "  throwaway app for middleware/error-handler coverage may still build a\n"
        "  bare FastAPI() — just do not mount api.router on it.",
        requires=re.compile(r"\bFastAPI\s*\("),
    ),
    Rule(
        "test-generate-schemas",
        lambda n: in_tests(n, allow=frozenset({"conftest.py"})),
        re.compile(r"\bgenerate_schemas\s*\("),
        "Tortoise.generate_schemas() in a test.\n"
        "  It re-derives the same CREATE TABLE script from model metadata on every\n"
        "  call (~18ms x ~1450 DB-backed setups). The `db` fixture in\n"
        "  tests/conftest.py already renders it once via the cached _schema_sql()\n"
        "  and replays the script — depend on `db` instead of initialising your own\n"
        "  schema.",
    ),
    Rule(
        "test-tortoise-init",
        lambda n: in_tests(n, allow=frozenset({"conftest.py"})),
        re.compile(r"\bTortoise\.init\s*\("),
        "Tortoise.init() in a test.\n"
        "  Most of it is _build_initial_querysets() rebuilding a filter map for all\n"
        "  ~70 models — 60s of a 190s profiled run when it ran per test. The `db`\n"
        "  fixture in tests/conftest.py now does it once per worker and gives each\n"
        "  test a pristine database by restoring a template snapshot. Depend on `db`.",
    ),
    Rule(
        "test-mcp-build-server",
        lambda n: in_tests_except(n, "mcp/conftest.py"),
        re.compile(r"\bbuild_server\s*\("),
        "A test is building its own MCP server.\n"
        "  Registering the 77 tools derives a JSON schema per tool and costs ~230ms;\n"
        "  the ~106 MCP sessions in the suite paid it every time (~24s a run). The\n"
        "  catalogue is immutable — only the transport is single-use. Use\n"
        "  mcp_session() from tests/mcp/conftest.py, which mounts the cached server\n"
        "  with a freshly minted session manager.",
    ),
    Rule(
        "test-inline-dev-seed",
        lambda n: in_tests_except(n, "conftest.py", "test_seed_coverage.py"),
        re.compile(r"\bseed_all\s*\("),
        "A test runs the dev seed inline.\n"
        "  seed_all() costs ~1.5s. Request the `seeded_db` fixture from\n"
        "  tests/conftest.py instead: it seeds once per worker, snapshots the result\n"
        "  and restores it for every later test. Call seed_all() directly only when\n"
        "  the seed *running* is what is under test (idempotency, ordering).",
    ),
]


def proposed_content(payload: dict) -> Optional[tuple]:
    """Return (file_path, old_content, new_content), or None to fail open."""
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path or not file_path.endswith(".py"):
        return None

    try:
        with open(file_path, encoding="utf-8") as fh:
            old = fh.read()
    except OSError:
        old = ""

    if tool_name == "Write":
        return file_path, old, tool_input.get("content", "")
    if tool_name == "Edit":
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
        if not old_string or old_string not in old:
            return None  # the Edit itself will fail; nothing to judge
        count = -1 if tool_input.get("replace_all") else 1
        return file_path, old, old.replace(old_string, new_string, count)
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    result = proposed_content(payload)
    if result is None:
        sys.exit(0)
    file_path, old, new = result

    norm = _norm(file_path)
    if "/.claude/" in norm:
        sys.exit(0)

    violations = []
    for rule in RULES:
        if not rule.applies(norm):
            continue
        if rule.requires is not None and not rule.requires.search(new):
            continue
        if len(rule.pattern.findall(new)) > len(rule.pattern.findall(old)):
            violations.append(
                f"SLOW FIXTURE ({rule.name}) in '{file_path}':\n  {rule.message}"
            )

    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        print(
            "  (Net-new check: pre-existing occurrences in this file do not block —\n"
            "  only adding another one does. Background: docs/development.md >\n"
            "  'Keeping it fast'.)",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
