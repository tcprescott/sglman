"""NavPreferenceService: a member's side menu pins and open sections."""

import pytest

from application.repositories._tenant import current_tenant_id
from application.services import NavPreferenceService
from application.services.nav_preference_service import DEFAULT_PINS, RUN_SHEET_PIN
from models import NavPreference, Role, UserRole
from tests.factories import make_member, make_user


async def test_a_member_who_never_edited_gets_the_default_pins(db):
    player = await make_member(901)
    pins, open_sections = await NavPreferenceService().load(player)
    assert pins == list(DEFAULT_PINS)
    assert open_sections is None


async def test_staff_also_get_the_admin_schedule_pin(db):
    staff = await make_member(902)
    await UserRole.create(user=staff, role=Role.STAFF, tenant_id=current_tenant_id())
    pins, _ = await NavPreferenceService().load(staff)
    assert pins == [*DEFAULT_PINS, RUN_SHEET_PIN]


async def test_signed_out_gets_nothing(db):
    assert await NavPreferenceService().load(None) == ([], None)


async def test_saved_pins_keep_their_order_and_drop_duplicates(db):
    player = await make_member(903)
    service = NavPreferenceService()
    saved = await service.save_pins(player, ['/live', '/home/event', '/live'])
    assert saved == ['/live', '/home/event']
    assert (await service.load(player))[0] == ['/live', '/home/event']


async def test_unpinning_everything_is_kept_rather_than_reset_to_defaults(db):
    player = await make_member(904)
    service = NavPreferenceService()
    await service.save_pins(player, [])
    assert (await service.load(player))[0] == []


async def test_open_sections_save_without_touching_pins(db):
    player = await make_member(905)
    service = NavPreferenceService()
    await service.save_pins(player, ['/live'])
    await service.save_open_sections(player, ['admin', 'admin:Operations'])
    assert await service.load(player) == (['/live'], ['admin', 'admin:Operations'])
    assert await NavPreference.filter(user=player).count() == 1


@pytest.mark.parametrize('bad', [
    'not-a-list', [42], [''], ['https://evil.example'], ['//evil.example'], ['/' + 'x' * 200],
])
async def test_bad_pins_are_refused(db, bad):
    player = await make_member(906)
    with pytest.raises(ValueError):
        await NavPreferenceService().save_pins(player, bad)


async def test_too_many_pins_are_refused(db):
    player = await make_member(907)
    with pytest.raises(ValueError, match='up to 12'):
        await NavPreferenceService().save_pins(player, [f'/p{i}' for i in range(13)])


async def test_a_non_member_cannot_save(db):
    outsider = await make_user(908)
    with pytest.raises(ValueError, match='Join this community'):
        await NavPreferenceService().save_pins(outsider, ['/live'])
    assert await NavPreference.all().count() == 0
