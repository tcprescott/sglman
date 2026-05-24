from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.audit_service import AuditActions
from application.services.match_watcher_service import MatchWatcherService


@pytest.fixture
def service():
    svc = object.__new__(MatchWatcherService)
    svc.repository = MagicMock()
    svc.match_repository = MagicMock()
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    return svc


def make_user(id=1, discord_id=12345):
    return SimpleNamespace(id=id, discord_id=discord_id)


def make_match(id=1, confirmed_at=None):
    return SimpleNamespace(id=id, confirmed_at=confirmed_at)


class TestWatch:
    async def test_creates_watcher_when_not_existing(self, service):
        match = make_match()
        user = make_user()
        watcher = SimpleNamespace(id=1)
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        service.repository.get_or_create = AsyncMock(return_value=(watcher, True))

        result = await service.watch(match.id, user)

        assert result is watcher
        service.repository.get_or_create.assert_awaited_once_with(match=match, user=user)

    async def test_audit_logs_on_first_watch(self, service):
        service.match_repository.get_by_id = AsyncMock(return_value=make_match())
        service.repository.get_or_create = AsyncMock(return_value=(SimpleNamespace(), True))

        user = make_user()
        await service.watch(7, user)

        service.audit_service.write_log.assert_awaited_once()
        args, _ = service.audit_service.write_log.call_args
        assert args[0] is user
        assert args[1] == AuditActions.MATCH_WATCHER_ADDED
        assert args[2] == {'match_id': 7}

    async def test_no_audit_log_when_already_watching(self, service):
        service.match_repository.get_by_id = AsyncMock(return_value=make_match())
        service.repository.get_or_create = AsyncMock(return_value=(SimpleNamespace(), False))

        await service.watch(7, make_user())

        service.audit_service.write_log.assert_not_awaited()

    async def test_raises_when_match_not_found(self, service):
        service.match_repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await service.watch(999, make_user())

    async def test_raises_when_match_already_confirmed(self, service):
        service.match_repository.get_by_id = AsyncMock(
            return_value=make_match(confirmed_at=datetime.now()),
        )

        with pytest.raises(ValueError, match="already confirmed"):
            await service.watch(1, make_user())

    async def test_does_not_create_when_match_confirmed(self, service):
        service.match_repository.get_by_id = AsyncMock(
            return_value=make_match(confirmed_at=datetime.now()),
        )
        service.repository.get_or_create = AsyncMock()

        with pytest.raises(ValueError):
            await service.watch(1, make_user())

        service.repository.get_or_create.assert_not_awaited()


class TestUnwatch:
    async def test_removes_existing_watcher(self, service):
        match = make_match()
        user = make_user()
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        service.repository.delete_by_match_and_user = AsyncMock(return_value=True)

        result = await service.unwatch(match.id, user)

        assert result is True
        service.repository.delete_by_match_and_user.assert_awaited_once_with(match=match, user=user)

    async def test_audit_logs_on_successful_unwatch(self, service):
        service.match_repository.get_by_id = AsyncMock(return_value=make_match())
        service.repository.delete_by_match_and_user = AsyncMock(return_value=True)

        user = make_user()
        await service.unwatch(42, user)

        service.audit_service.write_log.assert_awaited_once()
        args, _ = service.audit_service.write_log.call_args
        assert args[0] is user
        assert args[1] == AuditActions.MATCH_WATCHER_REMOVED
        assert args[2] == {'match_id': 42}

    async def test_no_audit_log_when_not_watching(self, service):
        service.match_repository.get_by_id = AsyncMock(return_value=make_match())
        service.repository.delete_by_match_and_user = AsyncMock(return_value=False)

        result = await service.unwatch(42, make_user())

        assert result is False
        service.audit_service.write_log.assert_not_awaited()

    async def test_returns_false_when_match_not_found(self, service):
        service.match_repository.get_by_id = AsyncMock(return_value=None)
        service.repository.delete_by_match_and_user = AsyncMock()

        result = await service.unwatch(999, make_user())

        assert result is False
        service.repository.delete_by_match_and_user.assert_not_awaited()


class TestIsWatching:
    async def test_delegates_to_repository(self, service):
        service.repository.is_watching = AsyncMock(return_value=True)
        user = make_user(id=5)

        result = await service.is_watching(10, user)

        assert result is True
        service.repository.is_watching.assert_awaited_once_with(10, 5)


class TestListWatchedMatchIds:
    async def test_returns_repository_ids(self, service):
        service.repository.get_match_ids_for_user = AsyncMock(return_value=[1, 2, 3])
        user = make_user()

        result = await service.list_watched_match_ids(user)

        assert result == [1, 2, 3]
        service.repository.get_match_ids_for_user.assert_awaited_once_with(user)
