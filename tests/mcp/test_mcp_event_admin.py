"""Event-day administration tools: stages, volunteer schedule, members, equipment, payouts.

The connection gate for every write is covered in ``test_mcp_writes.py``; these
assert each tool reaches its service, the service's permission check holds, and
another community's rows stay out of reach.
"""

from datetime import datetime, timedelta, timezone

from models import (
    Equipment,
    Role,
    Stage,
    Tenant,
    TenantMembership,
    Tournament,
    User,
    UserRole,
    VolunteerAssignment,
    VolunteerPosition,
    VolunteerShift,
)
from tests.api_helpers import create_community_member
from tests.mcp.conftest import call_tool, create_oauth_token, mcp_session

TENANT = 'default'


def _iso(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0).isoformat()


class TestStages:
    async def test_create_update_delete(self, db):
        _, raw = await create_oauth_token(roles=[Role.STREAM_MANAGER], write=True)
        async with mcp_session() as client:
            is_error, stage = await call_tool(
                client, raw, 'create_stage', tenant=TENANT, name='Main Stage',
                stream_url='https://twitch.tv/speedgaming',
            )
            assert not is_error, stage
            is_error, payload = await call_tool(
                client, raw, 'update_stage', tenant=TENANT, stage_id=stage['id'], is_active=False,
            )
            assert not is_error and payload['is_active'] is False, payload
            is_error, payload = await call_tool(
                client, raw, 'delete_stage', tenant=TENANT, stage_id=stage['id'],
            )
            assert not is_error, payload
        assert not await Stage.filter(id=stage['id']).exists()

    async def test_another_communitys_stage_is_not_found(self, db):
        other = await Tenant.create(slug='other-community', name='Other', is_active=True)
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        theirs = await Stage.create(name='Their Stage', tenant_id=other.id)
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'delete_stage', tenant=TENANT, stage_id=theirs.id,
            )
        assert is_error and 'not_found:' in payload, payload
        assert await Stage.filter(id=theirs.id).exists()


class TestVolunteerSchedule:
    async def test_a_coordinator_builds_and_staffs_a_shift(self, db):
        _, raw = await create_oauth_token(roles=[Role.VOLUNTEER_COORDINATOR], write=True)
        volunteer = await create_community_member(username='vol', dm_notifications=False)
        async with mcp_session() as client:
            is_error, position = await call_tool(
                client, raw, 'create_volunteer_position', tenant=TENANT, name='Runner',
            )
            assert not is_error, position
            is_error, shift = await call_tool(
                client, raw, 'create_volunteer_shift', tenant=TENANT,
                position_id=position['id'], starts_at=_iso(24), ends_at=_iso(28),
            )
            assert not is_error, shift
            is_error, payload = await call_tool(
                client, raw, 'update_volunteer_shift', tenant=TENANT,
                shift_id=shift['id'], slots_needed=3, label='Opening',
            )
            assert not is_error, payload
            assert payload['slots_needed'] == 3 and payload['label'] == 'Opening'
            is_error, assigned = await call_tool(
                client, raw, 'assign_volunteer', tenant=TENANT,
                shift_id=shift['id'], user_id=volunteer.id,
            )
            assert not is_error, assigned
            assignment_id = assigned['assignment']['id']
            is_error, payload = await call_tool(
                client, raw, 'unassign_volunteer', tenant=TENANT, assignment_id=assignment_id,
            )
            assert not is_error, payload
        assert not await VolunteerAssignment.filter(id=assignment_id).exists()

    async def test_a_non_member_cannot_be_assigned(self, db):
        _, raw = await create_oauth_token(roles=[Role.VOLUNTEER_COORDINATOR], write=True)
        stranger = await User.create(discord_id=884001, username='stranger')
        position = await VolunteerPosition.create(name='Desk')
        start = datetime.now(timezone.utc) + timedelta(hours=24)
        shift = await VolunteerShift.create(position=position, starts_at=start, ends_at=start + timedelta(hours=2))
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'assign_volunteer', tenant=TENANT, shift_id=shift.id, user_id=stranger.id,
            )
        assert is_error and 'not_found:' in payload, payload

    async def test_a_volunteer_cannot_create_shifts(self, db):
        _, raw = await create_oauth_token(roles=[Role.VOLUNTEER], write=True)
        position = await VolunteerPosition.create(name='Desk')
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'create_volunteer_shift', tenant=TENANT,
                position_id=position.id, starts_at=_iso(24), ends_at=_iso(26),
            )
        assert is_error and 'forbidden:' in payload, payload
        assert not await VolunteerShift.filter(position=position).exists()


class TestMembersAndRoles:
    async def test_add_grant_revoke_remove(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        person = await User.create(discord_id=885001, username='newcomer', dm_notifications=False)
        async with mcp_session() as client:
            for tool, args in (
                ('add_community_member', {}),
                ('grant_community_role', {'role': 'proctor'}),
            ):
                is_error, payload = await call_tool(
                    client, raw, tool, tenant=TENANT, user_id=person.id, **args,
                )
                assert not is_error, (tool, payload)
            assert await UserRole.filter(user=person, role=Role.PROCTOR).exists()

            is_error, payload = await call_tool(
                client, raw, 'remove_community_member', tenant=TENANT, user_id=person.id,
            )
            assert is_error, payload

            for tool, args in (
                ('revoke_community_role', {'role': 'proctor'}),
                ('remove_community_member', {}),
            ):
                is_error, payload = await call_tool(
                    client, raw, tool, tenant=TENANT, user_id=person.id, **args,
                )
                assert not is_error, (tool, payload)
        assert not await TenantMembership.filter(user=person, tenant_id=1).exists()

    async def test_an_unknown_role_lists_the_valid_ones(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        person = await create_community_member(username='someone')
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'grant_community_role', tenant=TENANT, user_id=person.id, role='wizard',
            )
        assert is_error and 'proctor' in payload, payload

    async def test_super_admin_cannot_be_granted(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        person = await create_community_member(username='someone')
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'grant_community_role', tenant=TENANT, user_id=person.id, role='super_admin',
            )
        assert is_error, payload
        assert not await UserRole.filter(user=person, role=Role.SUPER_ADMIN).exists()


class TestEquipment:
    async def test_create_lend_return_delete(self, db):
        _, raw = await create_oauth_token(roles=[Role.EQUIPMENT_MANAGER], write=True)
        borrower = await create_community_member(username='borrower')
        async with mcp_session() as client:
            is_error, created = await call_tool(
                client, raw, 'create_equipment', tenant=TENANT, name='Controller', count=2,
                description='SNES pad',
            )
            assert not is_error, created
            assert len(created['result']) == 2
            asset_id = created['result'][0]['id']

            is_error, payload = await call_tool(
                client, raw, 'update_equipment', tenant=TENANT, equipment_id=asset_id, name='Pad A',
            )
            assert not is_error, payload
            assert payload['name'] == 'Pad A' and payload['description'] == 'SNES pad'

            is_error, payload = await call_tool(
                client, raw, 'check_out_equipment', tenant=TENANT,
                equipment_id=asset_id, borrower_id=borrower.id,
            )
            assert not is_error and payload['status'] == 'checked_out', payload
            is_error, payload = await call_tool(
                client, raw, 'delete_equipment', tenant=TENANT, equipment_id=asset_id,
            )
            assert is_error, payload
            is_error, payload = await call_tool(
                client, raw, 'check_in_equipment', tenant=TENANT, equipment_id=asset_id,
            )
            assert not is_error and payload['status'] == 'available', payload
            is_error, payload = await call_tool(
                client, raw, 'delete_equipment', tenant=TENANT, equipment_id=asset_id,
            )
            assert not is_error, payload
        assert not await Equipment.filter(id=asset_id).exists()


class TestPayouts:
    async def test_set_pool_and_split(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        winner = await create_community_member(username='winner')
        tournament = await Tournament.create(name='Cup')
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'set_tournament_prize_pool', tenant=TENANT,
                tournament_id=tournament.id, prize_pool='1000',
            )
            assert not is_error, payload
            is_error, payload = await call_tool(
                client, raw, 'set_tournament_payout_split', tenant=TENANT, tournament_id=tournament.id,
                lines=[
                    {'place': 1, 'percentage': '60', 'entrant_id': winner.id},
                    {'place': 2, 'percentage': '40'},
                ],
            )
            assert not is_error, payload
        assert float(payload['total']) == 1000
        assert [float(line['amount']) for line in payload['lines']] == [600, 400]

    async def test_over_100_percent_is_refused(self, db):
        _, raw = await create_oauth_token(roles=[Role.STAFF], write=True)
        tournament = await Tournament.create(name='Cup')
        async with mcp_session() as client:
            is_error, payload = await call_tool(
                client, raw, 'set_tournament_payout_split', tenant=TENANT, tournament_id=tournament.id,
                lines=[{'place': 1, 'percentage': '70'}, {'place': 2, 'percentage': '40'}],
            )
        assert is_error, payload
