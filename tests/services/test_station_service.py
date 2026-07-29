"""Unit tests for StationService — the venue's station pool CRUD.

Validation, permission gating and the audit fields are exercised here. The
repository is mocked so the tests do not depend on a database; the pool's
tenant scoping is covered by tests/tenancy/test_station_tenant_isolation.py.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.errors import NotFoundError
from application.services.audit_service import AuditActions
from application.services.station_service import StationService


pytestmark = pytest.mark.usefixtures("bypass_auth")


async def _apply_fields(station, **fields):
    """Stand in for the repository's setattr-loop update."""
    for key, value in fields.items():
        setattr(station, key, value)
    return station


@pytest.fixture
def service():
    svc = object.__new__(StationService)
    svc.repository = MagicMock()
    svc.repository.create = AsyncMock(side_effect=lambda **f: SimpleNamespace(id=7, **f))
    svc.repository.update = AsyncMock(side_effect=_apply_fields)
    svc.repository.delete = AsyncMock()
    svc.repository.get_all = AsyncMock(return_value=[])
    svc.repository.get_active = AsyncMock(return_value=[])
    svc.repository.get_by_id = AsyncMock(return_value=None)
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    return svc


def _actor():
    return SimpleNamespace(id=1, username='staff')


def _station(station_id=7, name='1', is_active=True):
    return SimpleNamespace(id=station_id, name=name, section=None, sort_order=0,
                           is_active=is_active)


class TestCreateStation:
    async def test_rejects_a_blank_name(self, service):
        with pytest.raises(ValueError, match='name is required'):
            await service.create_station('   ', _actor())

    async def test_rejects_a_duplicate_name(self, service):
        service.repository.get_all = AsyncMock(return_value=[_station(name='1')])
        with pytest.raises(ValueError, match='already exists'):
            await service.create_station(' 1 ', _actor())

    async def test_trims_and_audits(self, service):
        station = await service.create_station('  3  ', _actor(), section='  North  ')
        assert station.name == '3'
        assert station.section == 'North'
        actor, action, details = service.audit_service.write_log.call_args.args
        assert action == AuditActions.STATION_CREATED
        assert details == {'station_id': station.id, 'name': '3'}

    async def test_blank_section_stores_null(self, service):
        station = await service.create_station('3', _actor(), section='   ')
        assert station.section is None

    async def test_requires_staff(self, service, monkeypatch):
        from application.services import auth_service

        async def deny(*_a, **_k):
            return False

        async def real_ensure(allowed, message=None):
            if not allowed:
                raise PermissionError(message or 'denied')

        monkeypatch.setattr(auth_service.AuthService, 'is_staff', deny)
        monkeypatch.setattr(auth_service.AuthService, 'ensure', real_ensure)
        with pytest.raises(PermissionError, match='Only Staff'):
            await service.create_station('3', _actor())


class TestUpdateStation:
    async def test_missing_station_is_not_found(self, service):
        with pytest.raises(NotFoundError):
            await service.update_station(99, _actor(), is_active=False)

    async def test_deactivating_records_the_changed_field(self, service):
        station = _station()
        service.repository.get_by_id = AsyncMock(return_value=station)
        result = await service.update_station(7, _actor(), is_active=False)
        assert result.is_active is False
        _, action, details = service.audit_service.write_log.call_args.args
        assert action == AuditActions.STATION_UPDATED
        assert details == {'station_id': 7, 'changed_fields': ['is_active']}

    async def test_renaming_onto_another_station_is_rejected(self, service):
        station = _station(name='1')
        service.repository.get_by_id = AsyncMock(return_value=station)
        service.repository.get_all = AsyncMock(
            return_value=[station, _station(station_id=8, name='2')]
        )
        with pytest.raises(ValueError, match='already exists'):
            await service.update_station(7, _actor(), name='2')

    async def test_keeping_its_own_name_is_allowed(self, service):
        station = _station(name='1')
        service.repository.get_by_id = AsyncMock(return_value=station)
        service.repository.get_all = AsyncMock(return_value=[station])
        await service.update_station(7, _actor(), name='1', sort_order=3)
        assert station.sort_order == 3

    async def test_rejects_a_blank_rename(self, service):
        service.repository.get_by_id = AsyncMock(return_value=_station())
        with pytest.raises(ValueError, match='name is required'):
            await service.update_station(7, _actor(), name='  ')


class TestDeleteStation:
    async def test_missing_station_is_not_found(self, service):
        with pytest.raises(NotFoundError):
            await service.delete_station(99, _actor())

    async def test_deletes_and_audits(self, service):
        station = _station(name='4')
        service.repository.get_by_id = AsyncMock(return_value=station)
        await service.delete_station(7, _actor())
        service.repository.delete.assert_awaited_once_with(station)
        _, action, details = service.audit_service.write_log.call_args.args
        assert action == AuditActions.STATION_DELETED
        assert details == {'station_id': 7, 'name': '4'}


class TestListStations:
    async def test_active_only_uses_the_active_query(self, service):
        await service.list_stations(active_only=True)
        service.repository.get_active.assert_awaited_once()
        service.repository.get_all.assert_not_awaited()

    async def test_default_lists_the_whole_pool(self, service):
        await service.list_stations()
        service.repository.get_all.assert_awaited_once()
