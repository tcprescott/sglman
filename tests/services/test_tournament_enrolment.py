"""Enrolment from the tournament's own screen.

The Tournaments tab has always said "click a player count to manage entrants";
the dialog behind it was a read-only list. These cover the service the writable
version calls — in particular that it refuses a non-member at the service, not
merely by omitting them from the picker. UI-only gating is not gating.
"""

import pytest

from application.repositories.user_role_repository import UserRoleRepository
from application.services.tenant_membership_service import TenantMembershipService
from application.services.tournament_service import TournamentService
from models import AuditLog, Role, TenantMembership, Tournament, TournamentPlayers, User


@pytest.fixture
async def staff(db):
    boss = await User.create(discord_id=5200, username='boss')
    await UserRoleRepository.add(boss, Role.STAFF)
    await TenantMembership.create(user=boss, tenant_id=1)
    return boss


@pytest.fixture
async def tournament(db):
    return await Tournament.create(name='Spring Open')


@pytest.fixture
async def member(staff, db):
    person = await User.create(discord_id=5201, username='entrant')
    await TenantMembershipService().add_member(staff, person)
    return person


async def test_entrants_can_be_added_and_removed(staff, tournament, member):
    service = TournamentService()
    await service.enroll_player(tournament, member, staff)
    assert [tp.user_id for tp in await service.get_enrolled_players(tournament)] == [member.id]

    await service.unenroll_player(tournament, member, staff)
    assert await service.get_enrolled_players(tournament) == []


async def test_the_enrolment_row_is_tenant_stamped(staff, tournament, member):
    await TournamentService().enroll_player(tournament, member, staff)
    row = await TournamentPlayers.get(tournament=tournament, user=member)
    assert row.tenant_id == 1


async def test_adding_a_non_member_is_refused(staff, tournament, db):
    stranger = await User.create(discord_id=5202, username='stranger')
    with pytest.raises(ValueError) as exc:
        await TournamentService().enroll_player(tournament, stranger, staff)
    assert 'not a member' in str(exc.value)
    assert await TournamentPlayers.filter(user=stranger).count() == 0


async def test_enrolling_twice_is_refused_rather_than_silently_duplicated(
    staff, tournament, member,
):
    service = TournamentService()
    await service.enroll_player(tournament, member, staff)
    with pytest.raises(ValueError) as exc:
        await service.enroll_player(tournament, member, staff)
    assert 'already enrolled' in str(exc.value)


async def test_entrant_management_requires_role_granting_authority(tournament, db):
    nobody = await User.create(discord_id=5203, username='nobody')
    target = await User.create(discord_id=5204, username='target')
    with pytest.raises(PermissionError):
        await TournamentService().enroll_player(tournament, target, nobody)
    with pytest.raises(PermissionError):
        await TournamentService().unenroll_player(tournament, target, nobody)


async def test_entrant_changes_are_audited_under_the_shared_action(
    staff, tournament, member,
):
    """One fact reached from three screens keeps one audit action.

    The per-user edit dialog and the match dialog already write
    ``user.tournament_enrollment_updated``; a parallel action for the same
    change made from the tournament screen is how an audit log stops being
    answerable.
    """
    service = TournamentService()
    await service.enroll_player(tournament, member, staff)
    await service.unenroll_player(tournament, member, staff)

    rows = await AuditLog.filter(action='user.tournament_enrollment_updated')
    assert len(rows) == 2
    import json
    added, removed = (json.loads(r.details) for r in rows)
    assert added['added_tournament_ids'] == [tournament.id]
    assert added['removed_tournament_ids'] == []
    assert removed['removed_tournament_ids'] == [tournament.id]
    assert removed['added_tournament_ids'] == []


# ---------------------------------------------------------------------------
# The match-create side effect reports itself
# ---------------------------------------------------------------------------


async def test_ensure_players_enrolled_reports_who_it_enrolled(staff, tournament, member, db):
    """The dialog can only say "Alice was enrolled" if the service tells it."""
    from application.services import MatchService

    service = MatchService()
    newly = await service.ensure_players_enrolled(tournament.id, [member.id])
    assert [u.id for u in newly] == [member.id]

    # Second time round nobody is new, so the dialog says nothing.
    assert await service.ensure_players_enrolled(tournament.id, [member.id]) == []


async def test_ensure_players_enrolled_reports_nothing_for_an_empty_roster(tournament, db):
    from application.services import MatchService

    assert await MatchService().ensure_players_enrolled(tournament.id, []) == []
