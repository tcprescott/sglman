"""The go/no-go for closing the membership gate.

Gating a community on ``TenantMembership`` locks out anyone the backfill missed.
The exposure is specific: the multitenancy migration wrote a membership per user
*at that point*, and until the "a role implies membership" invariant landed
nothing wrote one afterwards except the first-admin grant. So the people at risk
are accounts created since — enrolled players, match players, crew, volunteers —
who never received a role.
"""

from datetime import datetime, timedelta, timezone

import pytest

from application.tenant_context import tenant_scope
from models import (
    AuditLog,
    Commentator,
    Match,
    MatchPlayers,
    Role,
    Tenant,
    TenantMembership,
    Tournament,
    TournamentPlayers,
    Tracker,
    User,
    UserRole,
    VolunteerAssignment,
    VolunteerPosition,
    VolunteerShift,
)
from scripts.backfill_memberships import backfill
from scripts.membership_coverage import coverage_gaps, grantable_gaps


@pytest.fixture
async def participant(db):
    """A user with no membership anywhere — the shape the gate would lock out."""
    return await User.create(discord_id=7200, username='participant')


async def test_a_clean_database_reports_no_gaps(db):
    await User.create(discord_id=7201, username='bystander')
    assert await grantable_gaps() == []


async def test_audit_reports_a_participant_without_a_membership(participant, db):
    tournament = await Tournament.create(name='T')
    await TournamentPlayers.create(tournament=tournament, user=participant)

    gaps = await coverage_gaps()
    assert gaps['enrolled in a tournament'] == {(participant.id, 1)}
    assert await grantable_gaps() == [(participant.id, 1)]


async def test_a_membership_removes_the_gap(participant, db):
    tournament = await Tournament.create(name='T')
    await TournamentPlayers.create(tournament=tournament, user=participant)
    await TenantMembership.create(user=participant, tenant_id=1)
    assert await grantable_gaps() == []


@pytest.mark.parametrize('signal', [
    'enrolled in a tournament',
    'played in a match',
    'signed up as a commentator',
    'signed up as a tracker',
    'took a volunteer shift',
    'holds a role',
])
async def test_backfill_grants_membership_for_each_covered_signal(signal, participant, db):
    tournament = await Tournament.create(name='T')
    match = await Match.create(tournament=tournament)

    if signal == 'enrolled in a tournament':
        await TournamentPlayers.create(tournament=tournament, user=participant)
    elif signal == 'played in a match':
        await MatchPlayers.create(match=match, user=participant)
    elif signal == 'signed up as a commentator':
        await Commentator.create(match=match, user=participant)
    elif signal == 'signed up as a tracker':
        await Tracker.create(match=match, user=participant)
    elif signal == 'took a volunteer shift':
        position = await VolunteerPosition.create(name='Runner')
        starts = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
        shift = await VolunteerShift.create(
            position=position, starts_at=starts, ends_at=starts + timedelta(hours=2),
        )
        await VolunteerAssignment.create(shift=shift, user=participant)
    elif signal == 'holds a role':
        await UserRole.create(user=participant, role=Role.PROCTOR, tenant_id=1)

    assert (participant.id, 1) in await grantable_gaps()
    await backfill()
    assert await grantable_gaps() == []
    assert await TenantMembership.filter(user=participant, tenant_id=1).count() == 1


async def test_backfill_ignores_the_audit_log_signal(participant, db):
    """Appearing in an audit row can mean somebody acted *on* you.

    A role revoke or a deactivation names its target; granting membership on
    that would quietly re-admit people staff had just removed.
    """
    await AuditLog.create(user=participant, action='user.role_revoked', tenant_id=1)

    reported = await coverage_gaps(include_report_only=True)
    assert reported['appears in the audit log'] == {(participant.id, 1)}
    assert await grantable_gaps() == []

    await backfill()
    assert await TenantMembership.filter(user=participant).count() == 0


async def test_backfill_is_idempotent(participant, db):
    tournament = await Tournament.create(name='T')
    await TournamentPlayers.create(tournament=tournament, user=participant)

    assert await backfill() == 1
    assert await backfill() == 0
    assert await TenantMembership.filter(user=participant, tenant_id=1).count() == 1


async def test_dry_run_writes_nothing(participant, db):
    tournament = await Tournament.create(name='T')
    await TournamentPlayers.create(tournament=tournament, user=participant)

    assert await backfill(dry_run=True) == 1
    assert await TenantMembership.filter(user=participant).count() == 0


async def test_super_admin_is_not_made_a_member_of_anything(db):
    """Its row carries tenant=NULL by design, and it belongs to no community."""
    root = await User.create(discord_id=7202, username='root')
    await UserRole.create(user=root, role=Role.SUPER_ADMIN, tenant=None)

    assert await grantable_gaps() == []
    await backfill()
    assert await TenantMembership.filter(user=root).count() == 0


async def test_the_backfill_grants_only_in_the_tenant_that_participated(db):
    a = await Tenant.get(id=1)
    b = await Tenant.create(name='B', slug='tenant-b2')
    person = await User.create(discord_id=7203, username='person')
    with tenant_scope(b.id):
        tournament = await Tournament.create(name='B Cup')
        await TournamentPlayers.create(tournament=tournament, user=person)

    await backfill()
    assert await TenantMembership.filter(user=person, tenant=b).count() == 1
    assert await TenantMembership.filter(user=person, tenant=a).count() == 0


async def test_the_seeded_database_has_no_gaps(db):
    """The dev fixtures must not themselves produce a lockout.

    They did: the SpeedGaming placeholder was put on a community's schedule
    without being made a member of it.
    """
    from scripts.seed_dev import seed_all

    await seed_all()
    assert await grantable_gaps() == []
