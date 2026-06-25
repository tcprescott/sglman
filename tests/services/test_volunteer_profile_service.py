"""Tests for VolunteerProfileService (unit, no DB)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.volunteer_profile_service import VolunteerProfileService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    svc = object.__new__(VolunteerProfileService)
    svc.repository = MagicMock()
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    return svc


def make_profile(**overrides):
    defaults = dict(opted_in_at=None, note=None)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_user(uid=1):
    return SimpleNamespace(id=uid, preferred_name='Alice')


# ---------------------------------------------------------------------------
# get_or_create
# ---------------------------------------------------------------------------


class TestGetOrCreate:
    async def test_delegates_to_repository(self, service):
        profile = make_profile()
        service.repository.get_or_create_for_user = AsyncMock(return_value=profile)
        result = await service.get_or_create(make_user())
        assert result is profile


# ---------------------------------------------------------------------------
# is_opted_in
# ---------------------------------------------------------------------------


class TestIsOptedIn:
    async def test_returns_false_when_no_profile(self, service):
        service.repository.get_for_user = AsyncMock(return_value=None)
        assert await service.is_opted_in(make_user()) is False

    async def test_returns_false_when_opted_in_at_is_none(self, service):
        service.repository.get_for_user = AsyncMock(return_value=make_profile(opted_in_at=None))
        assert await service.is_opted_in(make_user()) is False

    async def test_returns_true_when_opted_in_at_is_set(self, service):
        profile = make_profile(opted_in_at=datetime.now(timezone.utc))
        service.repository.get_for_user = AsyncMock(return_value=profile)
        assert await service.is_opted_in(make_user()) is True


# ---------------------------------------------------------------------------
# opt_in
# ---------------------------------------------------------------------------


class TestOptIn:
    async def test_sets_opted_in_at_when_none(self, service):
        user = make_user()
        profile = make_profile(opted_in_at=None)
        service.repository.get_or_create_for_user = AsyncMock(return_value=profile)
        service.repository.save = AsyncMock()
        result = await service.opt_in(user)
        assert result.opted_in_at is not None
        service.repository.save.assert_awaited_once_with(profile)
        service.audit_service.write_log.assert_awaited_once()

    async def test_does_not_overwrite_existing_opted_in_at(self, service):
        user = make_user()
        existing_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        profile = make_profile(opted_in_at=existing_ts)
        service.repository.get_or_create_for_user = AsyncMock(return_value=profile)
        service.repository.save = AsyncMock()
        await service.opt_in(user)
        assert profile.opted_in_at == existing_ts

    async def test_sets_note_when_provided(self, service):
        user = make_user()
        profile = make_profile()
        service.repository.get_or_create_for_user = AsyncMock(return_value=profile)
        service.repository.save = AsyncMock()
        await service.opt_in(user, note='Prefer mornings')
        assert profile.note == 'Prefer mornings'

    async def test_note_none_does_not_overwrite(self, service):
        user = make_user()
        profile = make_profile(note='Old note')
        service.repository.get_or_create_for_user = AsyncMock(return_value=profile)
        service.repository.save = AsyncMock()
        await service.opt_in(user, note=None)
        assert profile.note == 'Old note'


# ---------------------------------------------------------------------------
# opt_out
# ---------------------------------------------------------------------------


class TestOptOut:
    async def test_clears_opted_in_at_and_saves(self, service):
        user = make_user()
        profile = make_profile(opted_in_at=datetime.now(timezone.utc))
        service.repository.get_or_create_for_user = AsyncMock(return_value=profile)
        service.repository.save = AsyncMock()
        result = await service.opt_out(user)
        assert result.opted_in_at is None
        service.repository.save.assert_awaited_once()
        service.audit_service.write_log.assert_awaited_once()

    async def test_no_save_when_already_opted_out(self, service):
        user = make_user()
        profile = make_profile(opted_in_at=None)
        service.repository.get_or_create_for_user = AsyncMock(return_value=profile)
        service.repository.save = AsyncMock()
        await service.opt_out(user)
        service.repository.save.assert_not_awaited()
        service.audit_service.write_log.assert_not_awaited()


# ---------------------------------------------------------------------------
# update_note
# ---------------------------------------------------------------------------


class TestUpdateNote:
    async def test_updates_note_and_saves(self, service):
        user = make_user()
        profile = make_profile(note=None)
        service.repository.get_or_create_for_user = AsyncMock(return_value=profile)
        service.repository.save = AsyncMock()
        result = await service.update_note(user, 'Available weekends')
        assert result.note == 'Available weekends'
        service.repository.save.assert_awaited_once()

    async def test_clears_note_when_none(self, service):
        user = make_user()
        profile = make_profile(note='Something')
        service.repository.get_or_create_for_user = AsyncMock(return_value=profile)
        service.repository.save = AsyncMock()
        result = await service.update_note(user, None)
        assert result.note is None


# ---------------------------------------------------------------------------
# assignable_volunteers
# ---------------------------------------------------------------------------


class TestAssignableVolunteers:
    async def test_returns_empty_when_no_volunteer_role_users(self, monkeypatch):
        import application.services.volunteer_profile_service as mod

        class FakeUserRole:
            @staticmethod
            def filter(**_kw):
                class _QS:
                    @staticmethod
                    async def values_list(*_, **__):
                        return []
                return _QS()

        monkeypatch.setattr(mod, 'UserRole', FakeUserRole)
        svc = object.__new__(mod.VolunteerProfileService)
        svc.repository = MagicMock()
        svc.audit_service = MagicMock()
        result = await svc.assignable_volunteers()
        assert result == []

    async def test_returns_sorted_users(self, monkeypatch):
        import application.services.volunteer_profile_service as mod

        alice = SimpleNamespace(id=1, preferred_name='Alice')
        bob = SimpleNamespace(id=2, preferred_name='Bob')

        class FakeUserRole:
            @staticmethod
            def filter(**_kw):
                class _QS:
                    @staticmethod
                    async def values_list(*_, **__):
                        return [1, 2]
                return _QS()

        class FakeUser:
            @staticmethod
            async def filter(**_kw):
                return [bob, alice]

        monkeypatch.setattr(mod, 'UserRole', FakeUserRole)
        monkeypatch.setattr(mod, 'User', FakeUser)
        svc = object.__new__(mod.VolunteerProfileService)
        svc.repository = MagicMock()
        svc.audit_service = MagicMock()
        result = await svc.assignable_volunteers()
        assert result[0].preferred_name == 'Alice'
        assert result[1].preferred_name == 'Bob'
