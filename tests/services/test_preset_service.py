"""Tests for PresetService (PR 1) — tenant-authored seed-rolling presets.

CRUD + validation + built-in import. The management gate is exercised via the
system user (``is_system`` short-circuits ``can_manage_presets``), keeping these
tests free of per-tenant role setup — the gate itself is covered in
``test_auth_service.py``.
"""

import pytest

from application.services.preset_service import PresetService
from application.services.user_service import UserService
from models import Preset


@pytest.fixture
async def actor(db):
    """A management-authorized actor (the reserved system user)."""
    return await UserService().get_system_user()


@pytest.fixture
def service():
    return PresetService()


class TestCreatePreset:
    async def test_create_round_trips(self, service, actor):
        preset = await service.create_preset(
            actor, name='Open', randomizer='alttpr',
            settings={'mode': 'open'}, description='Open mode',
        )
        assert preset.id is not None
        assert preset.name == 'Open'
        assert preset.randomizer == 'alttpr'
        assert preset.settings == {'mode': 'open'}
        assert preset.description == 'Open mode'

    async def test_blank_name_raises(self, service, actor):
        with pytest.raises(ValueError, match='name is required'):
            await service.create_preset(actor, name='  ', randomizer='alttpr', settings={})

    async def test_unknown_randomizer_raises(self, service, actor):
        with pytest.raises(ValueError, match='Unknown randomizer'):
            await service.create_preset(actor, name='X', randomizer='nope', settings={})

    async def test_non_dict_settings_raises(self, service, actor):
        with pytest.raises(ValueError, match='must be a JSON object'):
            await service.create_preset(actor, name='X', randomizer='alttpr', settings=['nope'])

    async def test_duplicate_natural_key_raises(self, service, actor):
        await service.create_preset(actor, name='Dup', randomizer='alttpr', settings={})
        with pytest.raises(ValueError, match='already exists'):
            await service.create_preset(actor, name='Dup', randomizer='alttpr', settings={})

    async def test_same_name_different_randomizer_ok(self, service, actor):
        await service.create_preset(actor, name='Race', randomizer='alttpr', settings={})
        # Natural key includes randomizer, so this is a distinct preset.
        other = await service.create_preset(actor, name='Race', randomizer='ootr', settings={})
        assert other.id is not None


class TestUpdatePreset:
    async def test_update_changes_fields(self, service, actor):
        preset = await service.create_preset(actor, name='A', randomizer='alttpr', settings={'x': 1})
        updated = await service.update_preset(
            actor, preset.id, name='B', settings={'y': 2}, description='new',
        )
        assert updated.name == 'B'
        assert updated.settings == {'y': 2}
        assert updated.description == 'new'
        assert updated.randomizer == 'alttpr'

    async def test_update_missing_raises(self, service, actor):
        with pytest.raises(ValueError, match='Preset not found'):
            await service.update_preset(actor, 999999, name='X')

    async def test_update_to_existing_natural_key_raises(self, service, actor):
        await service.create_preset(actor, name='One', randomizer='alttpr', settings={})
        two = await service.create_preset(actor, name='Two', randomizer='alttpr', settings={})
        with pytest.raises(ValueError, match='already exists'):
            await service.update_preset(actor, two.id, name='One')


class TestDeletePreset:
    async def test_delete_removes_row(self, service, actor):
        preset = await service.create_preset(actor, name='Gone', randomizer='alttpr', settings={})
        await service.delete_preset(actor, preset.id)
        assert await Preset.filter(id=preset.id).count() == 0

    async def test_delete_missing_raises(self, service, actor):
        with pytest.raises(ValueError, match='Preset not found'):
            await service.delete_preset(actor, 999999)


class TestImportBuiltins:
    async def test_imports_committed_files(self, service, actor):
        created = await service.import_builtins(actor)
        names = {(p.randomizer, p.name) for p in created}
        # The committed ALTTPR presets land as rows.
        assert ('alttpr', 'casualboots') in names
        assert ('alttpr', 'sglive2025') in names

    async def test_alttpr_import_stores_settings_subtree(self, service, actor):
        await service.import_builtins(actor)
        casual = await service.repository.get_by_natural_key('alttpr', 'casualboots')
        assert casual is not None
        # ALTTPR files nest the payload under 'settings'; that subtree is stored
        # directly so seed generation can hand it to the randomizer unchanged.
        assert isinstance(casual.settings, dict)
        assert 'goal' in casual.settings
        assert 'settings' not in casual.settings

    async def test_import_is_idempotent(self, service, actor):
        first = await service.import_builtins(actor)
        assert first
        second = await service.import_builtins(actor)
        # Nothing new the second time — existing natural keys are skipped.
        assert second == []


class TestManagementGate:
    async def test_non_manager_cannot_create(self, service, db):
        from models import User
        # A plain user with no roles and no is_system fails the gate.
        user = await User.create(discord_id=555, username='nobody')
        with pytest.raises(PermissionError, match='manage presets'):
            await service.create_preset(user, name='X', randomizer='alttpr', settings={})
