# Feature: Test Suite

_Added: PRs #2, #13 | Status: Partial_

## Coverage

Tests live in `tests/`. Current coverage:

| Area | Tests | Notes |
|---|---|---|
| Timezone utilities | `tests/test_timezone.py` | Eastern↔UTC parse/format, DST boundaries |
| Match state machine | `tests/test_match_state.py` | `current_state` property; lifecycle transitions |
| Match service | `tests/test_match_service.py` | `create_match`, `update_match`, notification fan-out |
| API endpoints | `tests/test_api.py` | `/api/*` happy paths; requires test DB |
| Reports service | `tests/test_reports.py` | CSV escaping, crew-hours aggregation |

## Running Tests

```bash
poetry run pytest
# or with coverage:
poetry run pytest --cov=. --cov-report=term-missing
```

Tests use a SQLite in-memory database (via Tortoise's test helpers) rather than a live PostgreSQL instance. This catches logic errors but not PostgreSQL-specific query behavior.

## What Is Not Covered

- Discord bot interactions (require live Discord connection)
- NiceGUI UI rendering (no headless browser tests)
- OAuth flow (requires live Discord OAuth or mock; integration only)
- Repository layer (covered indirectly via service tests only)

## Test Patterns

```python
# Service test pattern
from tortoise.contrib.test import TestCase
from application.services.match_service import MatchService

class TestMatchService(TestCase):
    async def test_create_match(self):
        tournament = await Tournament.create(...)
        match = await MatchService.create_match(...)
        self.assertEqual(match.current_state, 'Scheduled')
```

## Known Gaps (PR #13 review)

- Crew service approval flow has no tests.
- Triforce text submission validation has no tests.
- Audit log write coverage is not verified in tests.

Adding tests for new features: create a `tests/test_<service_name>.py`, use `tortoise.contrib.test.TestCase`, and mock `DiscordService` calls with `unittest.mock.AsyncMock`.
