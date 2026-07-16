"""Unit tests for TournamentService.

Permission gating, field stripping, audit logging, and role management
(admins / crew_coordinators) are exercised here. The repository and the
m2m manager methods are mocked.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.tournament_service import TournamentService


pytestmark = pytest.mark.usefixtures("bypass_auth")
@pytest.fixture
def service():
    svc = object.__new__(TournamentService)
    svc.repository = MagicMock()
    svc.repository.create = AsyncMock()
    svc.repository.update = AsyncMock(side_effect=lambda t, **f: t)
    svc.repository.get_all = AsyncMock(return_value=[])
    svc.repository.get_by_id = AsyncMock()
    svc.preset_repository = MagicMock()
    svc.preset_repository.get_by_id = AsyncMock()
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    return svc


def make_user(user_id=1):
    return SimpleNamespace(id=user_id, username='alice')


def make_tournament(tournament_id=1, **overrides):
    admins = MagicMock()
    admins.add = AsyncMock()
    admins.remove = AsyncMock()
    coordinators = MagicMock()
    coordinators.add = AsyncMock()
    coordinators.remove = AsyncMock()

    defaults = dict(
        id=tournament_id,
        name='Tournament',
        admins=admins,
        crew_coordinators=coordinators,
        delete=AsyncMock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# create_tournament
# ---------------------------------------------------------------------------


class TestCreateTournament:
    async def test_happy_path(self, service):
        created = make_tournament(tournament_id=10, name='New Cup')
        service.repository.create = AsyncMock(return_value=created)

        result = await service.create_tournament(
            name=' New Cup ', description=' desc ', actor=make_user(),
        )

        assert result is created
        kwargs = service.repository.create.await_args.kwargs
        assert kwargs['name'] == 'New Cup'
        assert kwargs['description'] == 'desc'

        details = service.audit_service.write_log.await_args.args[2]
        assert details == {'tournament_id': 10, 'name': 'New Cup'}

    async def test_empty_name_raises(self, service):
        with pytest.raises(ValueError, match='name is required'):
            await service.create_tournament(name='   ', actor=make_user())
        service.repository.create.assert_not_called()

    async def test_seed_generator_string_none_normalized(self, service):
        service.repository.create = AsyncMock(return_value=make_tournament())
        await service.create_tournament(
            name='X', seed_generator='None', actor=make_user(),
        )
        assert service.repository.create.await_args.kwargs['seed_generator'] is None

    async def test_optional_string_fields_stripped(self, service):
        service.repository.create = AsyncMock(return_value=make_tournament())
        await service.create_tournament(
            name='X',
            bracket_url=' https://challonge.com/x ',
            rules_url=' https://r.x ',
            tournament_format=' DE ',
            triforce_access_message=' Buy access at https://shop.x ',
            actor=make_user(),
        )
        kwargs = service.repository.create.await_args.kwargs
        assert kwargs['bracket_url'] == 'https://challonge.com/x'
        assert kwargs['rules_url'] == 'https://r.x'
        assert kwargs['tournament_format'] == 'DE'
        assert kwargs['triforce_access_message'] == 'Buy access at https://shop.x'

    async def test_non_staff_actor_denied(self, service, monkeypatch):
        from application.services import auth_service

        async def deny(*_a, **_kw):
            return False

        async def real_ensure(allowed, message=None):
            if not allowed:
                raise PermissionError(message or 'denied')

        monkeypatch.setattr(auth_service.AuthService, 'is_staff', deny)
        monkeypatch.setattr(auth_service.AuthService, 'ensure', real_ensure)

        with pytest.raises(PermissionError):
            await service.create_tournament(name='X', actor=make_user())


# ---------------------------------------------------------------------------
# config substrate (hybrid config validation)
# ---------------------------------------------------------------------------


class TestTournamentConfig:
    async def test_valid_config_normalized_and_passed_to_repo(self, service):
        service.repository.create = AsyncMock(return_value=make_tournament())
        await service.create_tournament(
            name='X',
            config={'messaging_templates': {'welcome': 'hi {player}'}},
            actor=make_user(),
        )
        assert service.repository.create.await_args.kwargs['config'] == {
            'messaging_templates': {'welcome': 'hi {player}'}
        }

    async def test_none_config_passed_through(self, service):
        service.repository.create = AsyncMock(return_value=make_tournament())
        await service.create_tournament(name='X', actor=make_user())
        assert service.repository.create.await_args.kwargs['config'] is None

    async def test_unknown_key_raises_before_create(self, service):
        with pytest.raises(ValueError, match='Invalid tournament config'):
            await service.create_tournament(
                name='X', config={'bogus_key': 1}, actor=make_user(),
            )
        service.repository.create.assert_not_called()

    async def test_update_with_valid_config(self, service):
        t = make_tournament()
        await service.update_tournament(
            t, config={'messaging_templates': {}}, actor=make_user(),
        )
        assert service.repository.update.await_args.kwargs['config'] == {
            'messaging_templates': {}
        }

    async def test_update_unknown_key_raises(self, service):
        t = make_tournament()
        with pytest.raises(ValueError, match='Invalid tournament config'):
            await service.update_tournament(
                t, config={'nope': True}, actor=make_user(),
            )
        service.repository.update.assert_not_called()

    async def test_update_without_config_leaves_it_untouched(self, service):
        t = make_tournament()
        await service.update_tournament(t, name='Renamed', actor=make_user())
        assert 'config' not in service.repository.update.await_args.kwargs


# ---------------------------------------------------------------------------
# preset_id wiring
# ---------------------------------------------------------------------------


class TestTournamentPreset:
    async def test_create_with_valid_preset_passes_id_to_repo(self, service):
        service.preset_repository.get_by_id.return_value = SimpleNamespace(id=7)
        await service.create_tournament(name='X', preset_id=7, actor=make_user())
        assert service.repository.create.await_args.kwargs['preset_id'] == 7

    async def test_create_with_unknown_preset_raises_before_create(self, service):
        service.preset_repository.get_by_id.return_value = None
        with pytest.raises(ValueError, match='Preset not found'):
            await service.create_tournament(name='X', preset_id=99, actor=make_user())
        service.repository.create.assert_not_awaited()

    async def test_create_without_preset_passes_none(self, service):
        await service.create_tournament(name='X', actor=make_user())
        assert service.repository.create.await_args.kwargs['preset_id'] is None
        service.preset_repository.get_by_id.assert_not_awaited()

    async def test_update_sets_preset_when_provided(self, service):
        service.preset_repository.get_by_id.return_value = SimpleNamespace(id=3)
        t = make_tournament()
        await service.update_tournament(t, preset_id=3, actor=make_user())
        assert service.repository.update.await_args.kwargs['preset_id'] == 3

    async def test_update_clears_preset_with_explicit_none(self, service):
        t = make_tournament()
        await service.update_tournament(t, preset_id=None, actor=make_user())
        assert service.repository.update.await_args.kwargs['preset_id'] is None
        service.preset_repository.get_by_id.assert_not_awaited()

    async def test_update_without_preset_leaves_it_untouched(self, service):
        t = make_tournament()
        await service.update_tournament(t, name='Renamed', actor=make_user())
        assert 'preset_id' not in service.repository.update.await_args.kwargs

    async def test_update_unknown_preset_raises(self, service):
        service.preset_repository.get_by_id.return_value = None
        t = make_tournament()
        with pytest.raises(ValueError, match='Preset not found'):
            await service.update_tournament(t, preset_id=42, actor=make_user())


# ---------------------------------------------------------------------------
# update_tournament
# ---------------------------------------------------------------------------


class TestUpdateTournament:
    async def test_only_provided_fields_written(self, service):
        t = make_tournament()
        await service.update_tournament(
            t, name='Renamed', actor=make_user(),
        )
        kwargs = service.repository.update.await_args.kwargs
        assert kwargs == {'name': 'Renamed'}

    async def test_empty_name_string_raises(self, service):
        t = make_tournament()
        with pytest.raises(ValueError, match='name cannot be empty'):
            await service.update_tournament(t, name='   ', actor=make_user())

    async def test_triforce_access_message_stripped_and_cleared(self, service):
        t = make_tournament()
        await service.update_tournament(
            t, triforce_access_message=' how to buy ', actor=make_user(),
        )
        assert service.repository.update.await_args.kwargs['triforce_access_message'] == 'how to buy'

        await service.update_tournament(t, triforce_access_message='', actor=make_user())
        assert service.repository.update.await_args.kwargs['triforce_access_message'] is None

    async def test_seed_generator_explicit_value_passed_through(self, service):
        # Real generators like 'alttpr' should land in update_data.
        # (The literal string "None" is normalized to Python None, which then
        # falls through the ``if seed_generator is not None`` guard and is
        # excluded from update_data — i.e. update doesn't support clearing
        # the seed generator via this path.)
        t = make_tournament()
        await service.update_tournament(
            t, seed_generator='alttpr', actor=make_user(),
        )
        kwargs = service.repository.update.await_args.kwargs
        assert kwargs['seed_generator'] == 'alttpr'

    async def test_changed_fields_recorded_in_audit(self, service):
        t = make_tournament(tournament_id=7)
        await service.update_tournament(
            t,
            name='X',
            is_active=False,
            players_per_match=4,
            actor=make_user(),
        )
        details = service.audit_service.write_log.await_args.args[2]
        assert details['tournament_id'] == 7
        assert set(details['changed_fields']) == {'name', 'is_active', 'players_per_match'}

    async def test_none_for_string_field_means_no_update(self, service):
        # Distinct from passing empty string; None means "don't update this field"
        t = make_tournament()
        await service.update_tournament(
            t, name='X', description=None, actor=make_user(),
        )
        kwargs = service.repository.update.await_args.kwargs
        assert kwargs == {'name': 'X'}

    async def test_empty_string_for_optional_url_becomes_none(self, service):
        t = make_tournament()
        await service.update_tournament(t, bracket_url='', actor=make_user())
        kwargs = service.repository.update.await_args.kwargs
        assert kwargs['bracket_url'] is None

    async def test_unauthorized_edit_denied(self, service, monkeypatch):
        from application.services import auth_service

        async def deny(*_a, **_kw):
            return False

        async def real_ensure(allowed, message=None):
            if not allowed:
                raise PermissionError(message or 'denied')

        monkeypatch.setattr(auth_service.AuthService, 'can_edit_tournament', deny)
        monkeypatch.setattr(auth_service.AuthService, 'ensure', real_ensure)

        with pytest.raises(PermissionError):
            await service.update_tournament(make_tournament(), name='X', actor=make_user())


# ---------------------------------------------------------------------------
# delete_tournament
# ---------------------------------------------------------------------------


class TestDeleteTournament:
    async def test_deletes_and_audits(self, service):
        t = make_tournament(tournament_id=33)
        await service.delete_tournament(t, actor=make_user())
        t.delete.assert_awaited_once()
        details = service.audit_service.write_log.await_args.args[2]
        assert details == {'tournament_id': 33}


# ---------------------------------------------------------------------------
# add/remove admin & crew_coordinator
# ---------------------------------------------------------------------------


class TestAdminAndCoordinator:
    async def test_add_admin_calls_m2m_and_audits(self, service):
        t = make_tournament(tournament_id=5)
        target = make_user(user_id=99)
        await service.add_admin(t, target, actor=make_user(user_id=1))
        t.admins.add.assert_awaited_once_with(target)
        action = service.audit_service.write_log.await_args.args[1]
        assert action == 'tournament.admin_granted'

    async def test_remove_admin_calls_m2m_and_audits(self, service):
        t = make_tournament(tournament_id=5)
        target = make_user(user_id=99)
        await service.remove_admin(t, target, actor=make_user(user_id=1))
        t.admins.remove.assert_awaited_once_with(target)
        action = service.audit_service.write_log.await_args.args[1]
        assert action == 'tournament.admin_revoked'

    async def test_add_admin_is_idempotent_at_orm_level(self, service):
        # Tortoise's M2M add silently dedupes. We just verify the service
        # forwards the add call without trying to pre-check membership.
        t = make_tournament()
        target = make_user()
        await service.add_admin(t, target, actor=make_user())
        await service.add_admin(t, target, actor=make_user())
        assert t.admins.add.await_count == 2

    async def test_add_crew_coordinator_calls_m2m_and_audits(self, service):
        t = make_tournament(tournament_id=5)
        target = make_user(user_id=99)
        await service.add_crew_coordinator(t, target, actor=make_user(user_id=1))
        t.crew_coordinators.add.assert_awaited_once_with(target)
        action = service.audit_service.write_log.await_args.args[1]
        assert action == 'tournament.crew_coordinator_granted'

    async def test_remove_crew_coordinator_calls_m2m_and_audits(self, service):
        t = make_tournament(tournament_id=5)
        target = make_user(user_id=99)
        await service.remove_crew_coordinator(t, target, actor=make_user(user_id=1))
        t.crew_coordinators.remove.assert_awaited_once_with(target)
        action = service.audit_service.write_log.await_args.args[1]
        assert action == 'tournament.crew_coordinator_revoked'

    async def test_non_staff_cannot_grant_admin(self, service, monkeypatch):
        from application.services import auth_service

        async def deny(*_a, **_kw):
            return False

        async def real_ensure(allowed, message=None):
            if not allowed:
                raise PermissionError(message or 'denied')

        monkeypatch.setattr(auth_service.AuthService, 'can_grant_roles', deny)
        monkeypatch.setattr(auth_service.AuthService, 'ensure', real_ensure)

        with pytest.raises(PermissionError):
            await service.add_admin(make_tournament(), make_user(), actor=make_user())


# ---------------------------------------------------------------------------
# read helpers
# ---------------------------------------------------------------------------


class TestReadHelpers:
    async def test_get_all_passes_active_only(self, service):
        await service.get_all_tournaments(active_only=True)
        service.repository.get_all.assert_awaited_once_with(active_only=True)

    async def test_get_by_id_delegates(self, service):
        t = make_tournament(tournament_id=99)
        service.repository.get_by_id = AsyncMock(return_value=t)
        result = await service.get_tournament_by_id(99)
        assert result is t
        service.repository.get_by_id.assert_awaited_once_with(99)
