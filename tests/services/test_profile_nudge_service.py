"""Tests for ProfileNudgeService — community profile rules and who still owes them."""

import pytest

from application.services.profile_nudge_service import (
    CONFIG_KEY,
    ProfileCheck,
    ProfileNudgeService,
    ProfileSection,
)
from application.services.timezone_service import MODE_PINNED, MODE_USER, TimezoneService
from application.tenant_context import tenant_scope
from models import AuditLog, ProfileNudgeDismissal, Role, UserRole
from tests.factories import make_user


@pytest.fixture
async def setup(two_tenants):
    a, b = two_tenants
    staff = await make_user(discord_id=830, username='nudge_staff')
    await UserRole.create(user=staff, role=Role.STAFF, tenant=a)
    await UserRole.create(user=staff, role=Role.STAFF, tenant=b)
    member = await make_user(discord_id=831, username='nudge_member')
    return a, b, staff, member


def _rule(check: str, dismissible: bool = True, note: str | None = None) -> dict:
    return {'check': check, 'dismissible': dismissible, 'note': note}


class TestCleanRules:
    def test_garbage_is_empty(self):
        assert ProfileNudgeService._clean_rules(None) == []
        assert ProfileNudgeService._clean_rules({'rules': 'nope'}) == []

    def test_unknown_and_duplicate_checks_are_dropped(self):
        cleaned = ProfileNudgeService._clean_rules({'rules': [
            {'check': 'pronouns'}, {'check': 'shoe_size'}, {'check': 'pronouns', 'dismissible': False},
        ]})
        assert cleaned == [{'check': ProfileCheck.PRONOUNS, 'dismissible': True, 'note': None}]

    def test_catalogue_order_wins(self):
        cleaned = ProfileNudgeService._clean_rules({'rules': [{'check': 'pronouns'}, {'check': 'challonge'}]})
        assert [r['check'] for r in cleaned] == [ProfileCheck.CHALLONGE, ProfileCheck.PRONOUNS]


async def test_set_rules_persists_beside_other_config(setup):
    a, _, staff, _ = setup
    a.config = {'theme': {'primary': '#0e7470'}}
    await a.save()
    with tenant_scope(a.id):
        await ProfileNudgeService().set_rules(staff, [_rule('pronouns', False, '  Please  ')])
    await a.refresh_from_db()
    assert a.config['theme'] == {'primary': '#0e7470'}
    assert a.config[CONFIG_KEY] == {'rules': [_rule('pronouns', False, 'Please')]}
    assert await AuditLog.filter(action='profile_nudges.updated').count() == 1


async def test_set_rules_requires_staff(setup):
    a, _, _, member = setup
    with tenant_scope(a.id):
        with pytest.raises(PermissionError):
            await ProfileNudgeService().set_rules(member, [_rule('pronouns')])


async def test_set_rules_rejects_unknown_check_and_long_note(setup):
    a, _, staff, _ = setup
    with tenant_scope(a.id):
        with pytest.raises(ValueError, match='not a profile item'):
            await ProfileNudgeService().set_rules(staff, [_rule('shoe_size')])
        with pytest.raises(ValueError, match='under'):
            await ProfileNudgeService().set_rules(staff, [_rule('pronouns', note='x' * 201)])


async def test_pending_lists_unmet_rules_and_drops_met_ones(setup):
    a, _, staff, member = setup
    service = ProfileNudgeService()
    with tenant_scope(a.id):
        await service.set_rules(staff, [_rule('pronouns', note='Crew reads these.')])
        [nudge] = await service.pending_for(member)
        assert nudge.check is ProfileCheck.PRONOUNS
        assert nudge.section is ProfileSection.PERSONAL
        assert nudge.note == 'Crew reads these.'
        member.pronouns = 'they/them'
        assert await service.pending_for(member) == []


async def test_no_rules_means_no_banner(setup):
    a, _, _, member = setup
    with tenant_scope(a.id):
        assert await ProfileNudgeService().pending_for(member) == []
    assert await ProfileNudgeService().pending_for(None) == []


async def test_dismiss_hides_a_dismissible_rule(setup):
    a, _, staff, member = setup
    service = ProfileNudgeService()
    with tenant_scope(a.id):
        await service.set_rules(staff, [_rule('pronouns')])
        await service.dismiss(member, 'pronouns')
        await service.dismiss(member, 'pronouns')
        assert await service.pending_for(member) == []
    assert await ProfileNudgeDismissal.filter(user=member).count() == 1
    assert await AuditLog.filter(action='profile_nudge.dismissed').count() == 1


async def test_mandatory_rule_cannot_be_dismissed(setup):
    a, _, staff, member = setup
    service = ProfileNudgeService()
    with tenant_scope(a.id):
        await service.set_rules(staff, [_rule('pronouns', dismissible=False)])
        with pytest.raises(ValueError, match="can't be dismissed"):
            await service.dismiss(member, 'pronouns')
        assert [n.dismissible for n in await service.pending_for(member)] == [False]


async def test_making_a_rule_mandatory_overrides_an_earlier_dismissal(setup):
    a, _, staff, member = setup
    service = ProfileNudgeService()
    with tenant_scope(a.id):
        await service.set_rules(staff, [_rule('pronouns')])
        await service.dismiss(member, 'pronouns')
        await service.set_rules(staff, [_rule('pronouns', dismissible=False)])
        assert len(await service.pending_for(member)) == 1


async def test_dismissing_a_rule_that_is_off_is_refused(setup):
    a, _, _, member = setup
    with tenant_scope(a.id):
        with pytest.raises(ValueError, match="isn't on this community's list"):
            await ProfileNudgeService().dismiss(member, 'pronouns')


async def test_timezone_rule_only_applies_when_members_pick_their_own(setup):
    a, _, staff, member = setup
    service = ProfileNudgeService()
    with tenant_scope(a.id):
        await service.set_rules(staff, [_rule('timezone')])
        await TimezoneService.set_settings(staff, MODE_PINNED, 'America/New_York')
        assert await service.pending_for(member) == []
        await TimezoneService.set_settings(staff, MODE_USER, 'America/New_York')
        assert [n.check for n in await service.pending_for(member)] == [ProfileCheck.TIMEZONE]
