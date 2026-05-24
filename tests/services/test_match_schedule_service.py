from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.match_schedule_service import MatchScheduleService


class MockTournament:
    def __init__(self, name="Test Tournament"):
        self.name = name


class MockMatch:
    """Minimal stand-in for a Match ORM object."""

    def __init__(self, *, seated_at=None, started_at=None, finished_at=None, confirmed_at=None, id=1):
        self.id = id
        self.seated_at = seated_at
        self.started_at = started_at
        self.finished_at = finished_at
        self.confirmed_at = confirmed_at
        self.tournament = MockTournament()
        self.save = AsyncMock()
        self.fetch_related = AsyncMock()


@pytest.fixture
def service():
    svc = object.__new__(MatchScheduleService)
    svc.match_repository = MagicMock()
    svc.discord_service = MagicMock()
    svc.seedgen_service = MagicMock()
    svc._seed_locks = {}
    svc.notify_match_participants = AsyncMock()
    return svc


class TestSeatMatch:
    async def test_sets_seated_at(self, service):
        match = MockMatch()
        await service.seat_match(match)
        assert match.seated_at is not None

    async def test_persists_the_change(self, service):
        match = MockMatch()
        await service.seat_match(match)
        match.save.assert_awaited_once()

    async def test_seated_at_is_recent(self, service):
        match = MockMatch()
        before = datetime.now()
        await service.seat_match(match)
        after = datetime.now()
        assert before <= match.seated_at <= after

    async def test_raises_if_already_seated(self, service):
        match = MockMatch(seated_at=datetime.now())
        with pytest.raises(ValueError, match="already checked in"):
            await service.seat_match(match)

    async def test_does_not_save_on_error(self, service):
        match = MockMatch(seated_at=datetime.now())
        with pytest.raises(ValueError):
            await service.seat_match(match)
        match.save.assert_not_awaited()


class TestStartMatch:
    async def test_sets_started_at(self, service):
        match = MockMatch(seated_at=datetime.now())
        await service.start_match(match)
        assert match.started_at is not None

    async def test_persists_the_change(self, service):
        match = MockMatch(seated_at=datetime.now())
        await service.start_match(match)
        match.save.assert_awaited_once()

    async def test_raises_if_not_seated(self, service):
        match = MockMatch()
        with pytest.raises(ValueError, match="checked in before starting"):
            await service.start_match(match)

    async def test_raises_if_already_started(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now)
        with pytest.raises(ValueError, match="already started"):
            await service.start_match(match)

    async def test_does_not_modify_seated_at(self, service):
        seated = datetime(2025, 1, 15, 10, 0)
        match = MockMatch(seated_at=seated)
        await service.start_match(match)
        assert match.seated_at == seated


class TestFinishMatch:
    async def test_sets_finished_at(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now)
        await service.finish_match(match)
        assert match.finished_at is not None

    async def test_persists_the_change(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now)
        await service.finish_match(match)
        match.save.assert_awaited_once()

    async def test_raises_if_not_started(self, service):
        match = MockMatch()
        with pytest.raises(ValueError, match="started before finishing"):
            await service.finish_match(match)

    async def test_raises_if_already_finished(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now, finished_at=now)
        with pytest.raises(ValueError, match="already finished"):
            await service.finish_match(match)

    async def test_does_not_require_confirmed_at_to_be_none(self, service):
        # confirmed_at is irrelevant to finish check
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now)
        await service.finish_match(match)
        assert match.finished_at is not None


class TestConfirmMatch:
    async def test_sets_confirmed_at(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now, finished_at=now)
        await service.confirm_match(match)
        assert match.confirmed_at is not None

    async def test_persists_the_change(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now, finished_at=now)
        await service.confirm_match(match)
        match.save.assert_awaited_once()

    async def test_raises_if_not_finished(self, service):
        match = MockMatch()
        with pytest.raises(ValueError, match="finished before confirming"):
            await service.confirm_match(match)

    async def test_raises_if_already_confirmed(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now, finished_at=now, confirmed_at=now)
        with pytest.raises(ValueError, match="already confirmed"):
            await service.confirm_match(match)


class TestFullLifecycle:
    async def test_seat_start_finish_confirm_in_order(self, service):
        match = MockMatch()
        await service.seat_match(match)
        await service.start_match(match)
        await service.finish_match(match)
        await service.confirm_match(match)
        assert match.confirmed_at is not None
        assert match.save.await_count == 4

    async def test_cannot_skip_seat_to_start(self, service):
        match = MockMatch()
        with pytest.raises(ValueError):
            await service.start_match(match)

    async def test_cannot_skip_start_to_finish(self, service):
        match = MockMatch(seated_at=datetime.now())
        with pytest.raises(ValueError):
            await service.finish_match(match)

    async def test_cannot_skip_finish_to_confirm(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now)
        with pytest.raises(ValueError):
            await service.confirm_match(match)


class TestCreateSeedDmMessage:
    def test_contains_player_name(self, service):
        msg = service._create_seed_dm_message("Alice", 42, "ALttPR Open", "https://alttpr.com/h/abc")
        assert "Alice" in msg

    def test_contains_match_id(self, service):
        msg = service._create_seed_dm_message("Alice", 42, "ALttPR Open", "https://alttpr.com/h/abc")
        assert "42" in msg

    def test_contains_tournament_name(self, service):
        msg = service._create_seed_dm_message("Alice", 42, "ALttPR Open", "https://alttpr.com/h/abc")
        assert "ALttPR Open" in msg

    def test_contains_seed_url(self, service):
        url = "https://alttpr.com/h/abc123"
        msg = service._create_seed_dm_message("Alice", 42, "ALttPR Open", url)
        assert url in msg

    def test_is_non_empty_string(self, service):
        msg = service._create_seed_dm_message("Bob", 1, "OoTR", "https://ootrandomizer.com/seed/1")
        assert isinstance(msg, str)
        assert len(msg) > 0
