"""Unit tests for UserService.

Covers permission gates, the concurrency-detection logic, the field-change
detection in self-edit, role grants/revokes, and tournament enrollment
set math.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.user_service import UserService
from models import Role, RoleSource


@pytest.fixture(autouse=True)
def bypass_auth(monkeypatch):
    from application.services import auth_service

    async def allow(*_args, **_kwargs):
        return True

    async def noop_ensure(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_service.AuthService, 'is_staff', allow)
    monkeypatch.setattr(auth_service.AuthService, 'can_grant_roles', allow)
    monkeypatch.setattr(auth_service.AuthService, 'ensure', noop_ensure)


@pytest.fixture
def service():
    svc = object.__new__(UserService)
    svc.repository = MagicMock()
    svc.repository.get_by_id = AsyncMock()
    svc.repository.get_by_discord_id = AsyncMock()
    svc.repository.create = AsyncMock()
    svc.repository.update = AsyncMock()
    svc.role_repository = MagicMock()
    svc.role_repository.add = AsyncMock()
    svc.role_repository.remove = AsyncMock()
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    return svc


def make_user(user_id=1, **overrides):
    defaults = dict(
        id=user_id,
        username='alice',
        display_name='Alice',
        pronouns='she/her',
        dm_notifications=False,
        is_active=True,
        discord_id='123',
        updated_at=datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
        save=AsyncMock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# get_current_user_from_storage
# ---------------------------------------------------------------------------


class TestGetCurrentUserFromStorage:
    async def test_returns_none_for_empty_discord_id(self, service):
        assert await service.get_current_user_from_storage(None) is None
        assert await service.get_current_user_from_storage('') is None
        service.repository.get_by_discord_id.assert_not_called()

    async def test_delegates_to_repository(self, service):
        u = make_user()
        service.repository.get_by_discord_id = AsyncMock(return_value=u)
        result = await service.get_current_user_from_storage('123')
        assert result is u
        service.repository.get_by_discord_id.assert_awaited_once_with('123')


# ---------------------------------------------------------------------------
# update_user_personal_info — self-edit field-change tracking
# ---------------------------------------------------------------------------


class TestUpdateUserPersonalInfo:
    async def test_saves_when_any_field_provided(self, service):
        user = make_user()
        await service.update_user_personal_info(
            user, actor=user, display_name='New Name',
        )
        user.save.assert_awaited_once()

    async def test_no_save_when_nothing_provided(self, service):
        user = make_user()
        await service.update_user_personal_info(user, actor=user)
        user.save.assert_not_called()
        service.audit_service.write_log.assert_not_called()

    async def test_only_records_audit_when_value_actually_changes(self, service):
        user = make_user(display_name='Alice', pronouns='she/her')
        await service.update_user_personal_info(
            user, actor=user, display_name='Alice', pronouns='she/her',
        )
        # save() is still called when any field was *provided*, but the audit log
        # should not be written because nothing actually changed.
        service.audit_service.write_log.assert_not_called()

    async def test_blank_string_clears_field_to_none(self, service):
        user = make_user(display_name='Alice')
        await service.update_user_personal_info(user, actor=user, display_name='   ')
        assert user.display_name is None

    async def test_audit_records_only_changed_fields(self, service):
        user = make_user(display_name='Old', pronouns='they/them', dm_notifications=False)
        await service.update_user_personal_info(
            user, actor=user,
            display_name='New',
            pronouns='they/them',  # unchanged
            dm_notifications=True,
        )
        details = service.audit_service.write_log.await_args.args[2]
        changed = details['changed_fields']
        assert set(changed.keys()) == {'display_name', 'dm_notifications'}
        assert changed['display_name'] == 'New'
        assert changed['dm_notifications'] is True


# ---------------------------------------------------------------------------
# update_user_profile — permission & concurrency detection
# ---------------------------------------------------------------------------


class TestUpdateUserProfile:
    async def test_self_edit_allowed(self, service):
        user = make_user(user_id=10)
        await service.update_user_profile(user, actor=user, display_name='New')
        service.repository.update.assert_awaited_once()

    async def test_staff_edit_allowed(self, service):
        user = make_user(user_id=10)
        actor = make_user(user_id=99)  # different from user
        # autouse bypass_auth makes is_staff=True
        await service.update_user_profile(user, actor=actor, display_name='New')
        service.repository.update.assert_awaited_once()

    async def test_non_self_non_staff_denied(self, service, monkeypatch):
        from application.services import auth_service

        async def deny(*_a, **_kw):
            return False

        monkeypatch.setattr(auth_service.AuthService, 'is_staff', deny)
        user = make_user(user_id=10)
        actor = make_user(user_id=99)
        with pytest.raises(PermissionError):
            await service.update_user_profile(user, actor=actor, display_name='Hi')

    async def test_concurrency_check_raises_when_user_modified(self, service):
        user = make_user(user_id=1)
        original_ts = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        # Repository returns a user with a different updated_at.
        latest = make_user(user_id=1, updated_at=original_ts + timedelta(minutes=5))
        service.repository.get_by_id = AsyncMock(return_value=latest)
        with pytest.raises(ValueError, match='modified by another'):
            await service.update_user_profile(
                user, actor=user,
                display_name='X',
                check_concurrency=True,
                initial_updated_at=original_ts,
            )
        service.repository.update.assert_not_called()

    async def test_concurrency_check_passes_when_unchanged(self, service):
        user = make_user(user_id=1)
        original_ts = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        latest = make_user(user_id=1, updated_at=original_ts)
        service.repository.get_by_id = AsyncMock(return_value=latest)
        await service.update_user_profile(
            user, actor=user,
            display_name='X',
            check_concurrency=True,
            initial_updated_at=original_ts,
        )
        service.repository.update.assert_awaited_once()

    async def test_concurrency_skipped_when_disabled(self, service):
        # check_concurrency=False (default) means repository.get_by_id is never called.
        user = make_user(user_id=1)
        await service.update_user_profile(user, actor=user, display_name='X')
        service.repository.get_by_id.assert_not_called()

    async def test_no_update_when_no_fields_change(self, service):
        user = make_user(user_id=1)
        await service.update_user_profile(user, actor=user)
        # No fields provided -> no repository call, no audit.
        service.repository.update.assert_not_called()
        service.audit_service.write_log.assert_not_called()

    async def test_audit_records_changed_fields(self, service):
        user = make_user(user_id=1)
        await service.update_user_profile(
            user, actor=user, display_name='Bob', pronouns='he/him',
        )
        action, details = (
            service.audit_service.write_log.await_args.args[1],
            service.audit_service.write_log.await_args.args[2],
        )
        assert action == 'user.profile_updated'
        assert details['target_user_id'] == 1
        assert details['changed_fields'] == {'display_name': 'Bob', 'pronouns': 'he/him'}


# ---------------------------------------------------------------------------
# update_user_admin_fields — staff-only, conditional audit
# ---------------------------------------------------------------------------


class TestUpdateUserAdminFields:
    async def test_only_audits_when_is_active_actually_flips(self, service):
        user = make_user(is_active=True)
        await service.update_user_admin_fields(user, actor=make_user(), is_active=True)
        # Repository.update was called but no audit (value didn't change).
        service.audit_service.write_log.assert_not_called()

    async def test_audits_when_activation_flips(self, service):
        user = make_user(is_active=True)
        await service.update_user_admin_fields(user, actor=make_user(), is_active=False)
        action = service.audit_service.write_log.await_args.args[1]
        assert action == 'user.activation_changed'
        assert service.audit_service.write_log.await_args.args[2]['is_active'] is False

    async def test_no_update_when_no_fields(self, service):
        user = make_user()
        await service.update_user_admin_fields(user, actor=make_user())
        service.repository.update.assert_not_called()

    async def test_concurrency_check_raises_when_modified(self, service):
        user = make_user(user_id=1)
        original_ts = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        latest = make_user(updated_at=original_ts + timedelta(seconds=1))
        service.repository.get_by_id = AsyncMock(return_value=latest)
        with pytest.raises(ValueError, match='modified by another'):
            await service.update_user_admin_fields(
                user, actor=make_user(),
                is_active=False,
                check_concurrency=True,
                initial_updated_at=original_ts,
            )

    async def test_non_staff_denied(self, service, monkeypatch):
        from application.services import auth_service

        async def deny(*_a, **_kw):
            return False

        async def real_ensure(allowed, message=None):
            if not allowed:
                raise PermissionError(message or 'denied')

        monkeypatch.setattr(auth_service.AuthService, 'is_staff', deny)
        monkeypatch.setattr(auth_service.AuthService, 'ensure', real_ensure)

        with pytest.raises(PermissionError):
            await service.update_user_admin_fields(
                make_user(), actor=make_user(), is_active=False,
            )


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------


class TestCreateUser:
    async def test_empty_username_raises(self, service):
        with pytest.raises(ValueError, match='Username is required'):
            await service.create_user(username='   ', actor=make_user())
        service.repository.create.assert_not_called()

    async def test_strips_inputs(self, service):
        created = make_user(user_id=7, username='bob', display_name='Bob', pronouns='he/him')
        service.repository.create = AsyncMock(return_value=created)
        await service.create_user(
            username=' bob ',
            display_name=' Bob ',
            pronouns=' he/him ',
            actor=make_user(),
        )
        kwargs = service.repository.create.await_args.kwargs
        assert kwargs['username'] == 'bob'
        assert kwargs['display_name'] == 'Bob'
        assert kwargs['pronouns'] == 'he/him'

    async def test_audits_created_user(self, service):
        created = make_user(user_id=7, username='bob')
        service.repository.create = AsyncMock(return_value=created)
        await service.create_user(username='bob', actor=make_user(), discord_id='42')
        details = service.audit_service.write_log.await_args.args[2]
        assert details['target_user_id'] == 7
        assert details['username'] == 'bob'
        assert details['discord_id'] == '42'


# ---------------------------------------------------------------------------
# grant_role / revoke_role
# ---------------------------------------------------------------------------


class TestRoleManagement:
    async def test_grant_role_calls_repository_and_audits(self, service):
        target = make_user(user_id=7)
        actor = make_user(user_id=1)
        await service.grant_role(target, Role.PROCTOR, actor)
        service.role_repository.add.assert_awaited_once_with(
            target, Role.PROCTOR, granted_by=actor, source=RoleSource.MANUAL
        )
        action = service.audit_service.write_log.await_args.args[1]
        assert action == 'user.role_granted'
        assert service.audit_service.write_log.await_args.args[2]['role'] == Role.PROCTOR.value

    async def test_revoke_role_calls_repository_and_audits(self, service):
        target = make_user(user_id=7)
        actor = make_user(user_id=1)
        await service.revoke_role(target, Role.PROCTOR, actor)
        service.role_repository.remove.assert_awaited_once_with(target, Role.PROCTOR)
        action = service.audit_service.write_log.await_args.args[1]
        assert action == 'user.role_revoked'

    async def test_non_staff_cannot_grant_role(self, service, monkeypatch):
        from application.services import auth_service

        async def deny(*_a, **_kw):
            return False

        async def real_ensure(allowed, message=None):
            if not allowed:
                raise PermissionError(message or 'denied')

        monkeypatch.setattr(auth_service.AuthService, 'can_grant_roles', deny)
        monkeypatch.setattr(auth_service.AuthService, 'ensure', real_ensure)

        with pytest.raises(PermissionError):
            await service.grant_role(make_user(), Role.STAFF, make_user())


# ---------------------------------------------------------------------------
# update_user_tournament_registrations — set math
# ---------------------------------------------------------------------------


class TestUpdateUserTournamentRegistrations:
    async def test_added_and_removed_ids_computed_correctly(self, service, monkeypatch):
        user = make_user()
        current = [
            SimpleNamespace(tournament_id=1, delete=AsyncMock()),
            SimpleNamespace(tournament_id=2, delete=AsyncMock()),
            SimpleNamespace(tournament_id=3, delete=AsyncMock()),
        ]

        # Mock Tournament.get_or_none and TournamentPlayers.create
        tournament_5 = SimpleNamespace(id=5)
        tournament_6 = SimpleNamespace(id=6)

        async def fake_get_or_none(id):
            return {5: tournament_5, 6: tournament_6}.get(id)

        create_mock = AsyncMock()
        monkeypatch.setattr(
            'application.services.user_service.Tournament.get_or_none',
            fake_get_or_none,
        )
        monkeypatch.setattr(
            'application.services.user_service.TournamentPlayers.create',
            create_mock,
        )

        # keep id=1, add 5 and 6, remove 2 and 3
        await service.update_user_tournament_registrations(
            user, actor=user,
            selected_tournament_ids={1, 5, 6},
            current_registrations=current,
        )

        # 2 and 3 should be deleted; 1 should not.
        current[0].delete.assert_not_called()
        current[1].delete.assert_awaited_once()
        current[2].delete.assert_awaited_once()

        # 5 and 6 are created.
        assert create_mock.await_count == 2

        # Audit log records the deltas (sorted).
        details = service.audit_service.write_log.await_args.args[2]
        assert details['added_tournament_ids'] == [5, 6]
        assert sorted(details['removed_tournament_ids']) == [2, 3]

    async def test_no_audit_when_no_changes(self, service):
        user = make_user()
        current = [
            SimpleNamespace(tournament_id=1, delete=AsyncMock()),
        ]
        await service.update_user_tournament_registrations(
            user, actor=user,
            selected_tournament_ids={1},
            current_registrations=current,
        )
        service.audit_service.write_log.assert_not_called()
        current[0].delete.assert_not_called()

    async def test_unknown_tournament_id_silently_skipped(self, service, monkeypatch):
        user = make_user()

        async def fake_get_or_none(id):
            return None  # tournament doesn't exist

        create_mock = AsyncMock()
        monkeypatch.setattr(
            'application.services.user_service.Tournament.get_or_none', fake_get_or_none,
        )
        monkeypatch.setattr(
            'application.services.user_service.TournamentPlayers.create', create_mock,
        )

        await service.update_user_tournament_registrations(
            user, actor=user,
            selected_tournament_ids={42},
            current_registrations=[],
        )
        create_mock.assert_not_called()
        service.audit_service.write_log.assert_not_called()


# ---------------------------------------------------------------------------
# provision_from_discord_login
# ---------------------------------------------------------------------------


class TestProvisionFromDiscordLogin:
    async def test_new_account_is_audited_and_not_username_synced(self, service):
        new_user = make_user(user_id=7, username='newbie', discord_id='999')
        service.repository.get_or_create_by_discord_id = AsyncMock(return_value=(new_user, True))

        user, created = await service.provision_from_discord_login(999, 'newbie')

        assert (user, created) == (new_user, True)
        service.repository.update.assert_not_awaited()
        service.audit_service.write_log.assert_awaited_once()
        actor, action, details = service.audit_service.write_log.await_args.args
        assert actor is new_user
        assert action == 'user.provisioned'
        assert details['source'] == 'discord_login'
        assert details['target_user_id'] == 7
        assert details['discord_id'] == '999'

    async def test_existing_active_user_synced_without_audit(self, service):
        existing = make_user(user_id=3, username='old_name', is_active=True)
        service.repository.get_or_create_by_discord_id = AsyncMock(return_value=(existing, False))

        user, created = await service.provision_from_discord_login(123, 'new_name')

        assert (user, created) == (existing, False)
        service.repository.update.assert_awaited_once_with(existing, username='new_name')
        service.audit_service.write_log.assert_not_awaited()

    async def test_existing_inactive_user_not_synced_or_audited(self, service):
        inactive = make_user(user_id=4, is_active=False)
        service.repository.get_or_create_by_discord_id = AsyncMock(return_value=(inactive, False))

        await service.provision_from_discord_login(123, 'new_name')

        service.repository.update.assert_not_awaited()
        service.audit_service.write_log.assert_not_awaited()


# ---------------------------------------------------------------------------
# create_mock_login_user
# ---------------------------------------------------------------------------


class TestCreateMockLoginUser:
    async def test_creates_user_with_roles_and_audits(self, service):
        new_user = make_user(user_id=9, username='dev', discord_id='555')
        service.repository.create = AsyncMock(return_value=new_user)

        user = await service.create_mock_login_user(
            discord_id=555,
            username='dev',
            display_name='Dev',
            role_values=[Role.STAFF.value, Role.PROCTOR.value],
        )

        assert user is new_user
        assert service.role_repository.add.await_count == 2
        service.audit_service.write_log.assert_awaited_once()
        actor, action, details = service.audit_service.write_log.await_args.args
        assert actor is new_user
        assert action == 'user.provisioned'
        assert details['source'] == 'mock_login'
        assert details['roles'] == [Role.STAFF.value, Role.PROCTOR.value]

    async def test_audits_even_with_no_roles(self, service):
        new_user = make_user(user_id=10, username='dev2', discord_id='556')
        service.repository.create = AsyncMock(return_value=new_user)

        await service.create_mock_login_user(discord_id=556, username='dev2')

        service.role_repository.add.assert_not_awaited()
        _, action, details = service.audit_service.write_log.await_args.args
        assert action == 'user.provisioned'
        assert details['roles'] == []
