# Feature: Test Suite

_Added: PRs #2, #13 | Status: Partial_

## Coverage

Tests live in `tests/` (root) and `tests/services/`. Current layout:

| Area | Tests | Notes |
|---|---|---|
| Timezone utilities | `tests/test_timezone.py` | Eastern↔UTC parse/format, DST boundaries |
| CSV export | `tests/test_csv_export.py` | Formula-injection escaping, filename generation |
| API endpoints | `tests/test_api_matches.py` | `GET /api/matches` filters, limits, approved-crew filtering |
| Audit service | `tests/services/test_audit_service.py` | Write/list/filter audit logs |
| Auth service | `tests/services/test_auth_service.py` | Role checks, permission helpers |
| Crew service | `tests/services/test_crew_service.py` | Approval flow, acknowledgment |
| Match schedule service | `tests/services/test_match_schedule_service.py` | Lifecycle transitions (seat/start/finish/confirm), notifications |
| Match service | `tests/services/test_match_service.py` | Match CRUD, crew signup, acknowledgment |
| Match watcher service | `tests/services/test_match_watcher_service.py` | Watch/unwatch, watched-match queries |
| Reports service | `tests/services/test_reports_service.py` | Report aggregation |
| Stream room service | `tests/services/test_stream_room_service.py` | Stream room CRUD |
| System config service | `tests/services/test_system_config_service.py` | Config get/set, typed accessors |
| Tournament notification service | `tests/services/test_tournament_notification_service.py` | Preference upserts |
| Tournament service | `tests/services/test_tournament_service.py` | Tournament CRUD, admin/coordinator management |
| Triforce text service | `tests/services/test_triforce_text_service.py` | Submission, moderation |
| User service | `tests/services/test_user_service.py` | Profile updates, roles, enrollments |

## Running Tests

```bash
poetry run pytest
```

`asyncio_mode = "auto"` is configured in `pyproject.toml`, so async tests need no decorator. (There is no coverage tooling configured; `pytest-cov` is not a dev dependency.)

## Fixtures

- `db` (`tests/conftest.py`) — function-scoped in-memory SQLite: runs `Tortoise.init` + `generate_schemas` per test, so each test starts with a fresh schema and no leakage. Logic errors are caught, but PostgreSQL-specific query behavior is not.
- `stub_discord_queue` (`tests/services/conftest.py`, autouse) — monkeypatches `discord_queue.enqueue` to capture coroutines without running them, letting tests assert a notification was enqueued while avoiding "coroutine was never awaited" warnings.

## Test Patterns

```python
# Service test pattern — uses the in-memory db fixture
from application.services.match_service import MatchService

async def test_create_match(db):
    tournament = await Tournament.create(...)
    match = await MatchService().create_match(...)
    assert match.current_state == 'Scheduled'
```

Adding tests for a new service: create `tests/services/test_<service_name>.py`, take the `db` fixture, and rely on the autouse `stub_discord_queue` to capture Discord sends.

## What Is Not Covered

- Discord bot interaction handlers (`discordbot/`) — require a live Discord connection
- NiceGUI UI rendering (`pages/`, `theme/`) — no headless browser tests
- OAuth flow (`middleware/auth.py`) — requires live Discord OAuth
- Repository layer — exercised only indirectly through service tests
- Seed generation against real randomizer APIs (network calls)

See [development.md](../development.md) for the day-to-day testing workflow.
