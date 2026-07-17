"""Unit tests for StreamRoomService.

Validation, permission gating, and audit-log fields are exercised here. The
repository is mocked so the tests do not depend on a database.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.stream_room_service import StreamRoomService


pytestmark = pytest.mark.usefixtures("bypass_auth")
@pytest.fixture
def service():
    svc = object.__new__(StreamRoomService)
    svc.repository = MagicMock()
    svc.repository.create = AsyncMock()
    svc.repository.update = AsyncMock(side_effect=lambda room, **f: room)
    svc.repository.get_by_id = AsyncMock()
    svc.repository.count_matches = AsyncMock(return_value=0)
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    return svc


def make_user(user_id=1):
    return SimpleNamespace(id=user_id, username='staff')


def make_room(room_id=10, **overrides):
    defaults = dict(
        id=room_id,
        name='Stage 1',
        stream_url='https://twitch.tv/x',
        is_active=True,
        delete=AsyncMock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# create_stream_room
# ---------------------------------------------------------------------------


class TestCreateStreamRoom:
    async def test_happy_path_creates_room_and_audits(self, service):
        created = make_room(room_id=1, name='Stage A')
        service.repository.create = AsyncMock(return_value=created)

        result = await service.create_stream_room(
            name=' Stage A ',
            stream_url=' https://x.tv ',
            actor=make_user(),
        )

        assert result is created
        # The repository should have been called with stripped strings.
        kwargs = service.repository.create.await_args.kwargs
        assert kwargs['name'] == 'Stage A'
        assert kwargs['stream_url'] == 'https://x.tv'
        assert kwargs['is_active'] is True

        service.audit_service.write_log.assert_awaited_once()
        details = service.audit_service.write_log.await_args.args[2]
        assert details == {'stream_room_id': 1, 'name': 'Stage A'}

    async def test_empty_name_raises_value_error(self, service):
        with pytest.raises(ValueError, match='name is required'):
            await service.create_stream_room(name='   ', actor=make_user())
        service.repository.create.assert_not_called()

    async def test_blank_name_raises_value_error(self, service):
        with pytest.raises(ValueError, match='name is required'):
            await service.create_stream_room(name='', actor=make_user())

    async def test_url_none_stored_as_none(self, service):
        service.repository.create = AsyncMock(return_value=make_room())
        await service.create_stream_room(name='Stage 1', stream_url=None, actor=make_user())
        assert service.repository.create.await_args.kwargs['stream_url'] is None

    async def test_unauthorized_actor_denied(self, service, monkeypatch):
        from application.services import auth_service

        async def deny(*_a, **_kw):
            return False

        async def real_ensure(allowed, message=None):
            if not allowed:
                raise PermissionError(message or 'denied')

        monkeypatch.setattr(auth_service.AuthService, 'can_manage_stream_rooms', deny)
        monkeypatch.setattr(auth_service.AuthService, 'ensure', real_ensure)

        with pytest.raises(PermissionError):
            await service.create_stream_room(name='Stage 1', actor=make_user())


# ---------------------------------------------------------------------------
# update_stream_room
# ---------------------------------------------------------------------------


class TestUpdateStreamRoom:
    async def test_only_changed_fields_are_written(self, service):
        room = make_room()
        await service.update_stream_room(room, name='Stage New', actor=make_user())

        kwargs = service.repository.update.await_args.kwargs
        assert kwargs == {'name': 'Stage New'}

    async def test_passing_none_for_field_does_not_update_it(self, service):
        room = make_room()
        await service.update_stream_room(
            room, name='X', stream_url=None, is_active=None, actor=make_user(),
        )
        kwargs = service.repository.update.await_args.kwargs
        assert kwargs == {'name': 'X'}

    async def test_empty_name_raises(self, service):
        room = make_room()
        with pytest.raises(ValueError, match='name cannot be empty'):
            await service.update_stream_room(room, name='   ', actor=make_user())

    async def test_audit_log_records_changed_field_names(self, service):
        room = make_room()
        await service.update_stream_room(
            room, name='New', is_active=False, actor=make_user(),
        )
        details = service.audit_service.write_log.await_args.args[2]
        assert details['stream_room_id'] == room.id
        assert set(details['changed_fields']) == {'name', 'is_active'}

    async def test_stream_url_is_stripped(self, service):
        room = make_room()
        await service.update_stream_room(
            room, stream_url='  https://x.tv  ', actor=make_user(),
        )
        kwargs = service.repository.update.await_args.kwargs
        assert kwargs['stream_url'] == 'https://x.tv'

    async def test_empty_stream_url_becomes_none(self, service):
        room = make_room()
        await service.update_stream_room(room, stream_url='', actor=make_user())
        kwargs = service.repository.update.await_args.kwargs
        assert kwargs['stream_url'] is None


# ---------------------------------------------------------------------------
# delete_stream_room
# ---------------------------------------------------------------------------


class TestDeleteStreamRoom:
    async def test_calls_delete_and_audits(self, service):
        room = make_room(room_id=99)
        await service.delete_stream_room(room, actor=make_user())
        room.delete.assert_awaited_once()
        details = service.audit_service.write_log.await_args.args[2]
        assert details == {'stream_room_id': 99}

    async def test_audit_uses_id_before_delete(self, service):
        # Even if the orm clears the id after delete(), audit_log should still have it.
        room = make_room(room_id=42)
        await service.delete_stream_room(room, actor=make_user())
        assert service.audit_service.write_log.await_args.args[2]['stream_room_id'] == 42

    async def test_refuses_delete_when_matches_assigned(self, service):
        room = make_room(room_id=7)
        service.repository.count_matches = AsyncMock(return_value=3)
        with pytest.raises(ValueError, match='inactive'):
            await service.delete_stream_room(room, actor=make_user())
        room.delete.assert_not_called()
        service.audit_service.write_log.assert_not_called()
