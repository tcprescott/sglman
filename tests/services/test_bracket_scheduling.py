"""B9 tests — the native-bracket scheduling seam and Challonge exclusivity.

DB-backed (the ``db`` fixture: in-memory SQLite, default tenant id 1). These
exercise the seam that lets a native bracket reuse the same ``Match`` creation
path the Challonge integration proved out: scheduling an OPEN bracket match into
a real ``Match``, advancing the bracket when that match is confirmed, and the
mutual-exclusion guards that keep a tournament on a native bracket OR a Challonge
link, never both.
"""

import pytest

from application.services.auth_service import AuthService
from application.services.bracket_service import BracketService
from application.services.challonge_service import ChallongeService
from application.tenant_context import tenant_scope
from models import (
    BracketMatchState,
    BracketState,
    Match,
    MatchPlayers,
    Role,
    Tournament,
    User,
    UserRole,
)

pytestmark = pytest.mark.usefixtures("db")


# ---------------------------------------------------------------------------
# fixtures / builders
# ---------------------------------------------------------------------------
async def _staff(discord_id: int = 1234, username: str = 'staff') -> User:
    user = await User.create(discord_id=discord_id, username=username)
    await UserRole.create(user=user, role=Role.STAFF)
    return user


async def _proctor(discord_id: int = 2222, username: str = 'proctor') -> User:
    user = await User.create(discord_id=discord_id, username=username)
    await UserRole.create(user=user, role=Role.PROCTOR)
    return user


async def _player(discord_id: int, username: str) -> User:
    return await User.create(discord_id=discord_id, username=username)


@pytest.fixture
def service() -> BracketService:
    return BracketService()


async def _linked_bracket(service, actor, n=2, link_users=True):
    """Create + start a 2-entrant single-elim bracket with linked entrants.

    Returns ``(tournament, bracket, users, open_match)`` where ``open_match`` is
    the single round-1 OPEN match. When ``link_users`` is False, the second
    entrant is left as a placeholder (no linked ``user``).
    """
    t = await Tournament.create(name='Cup')
    bracket = await service.create_bracket(actor, t.id, 'Main', 'single_elim')
    users = []
    for i in range(1, n + 1):
        linked = link_users or i == 1
        user = await _player(1000 + i, f'p{i}') if linked else None
        users.append(user)
        entrant = await service.add_entrant(
            actor, t.id, f'P{i}', user_id=user.id if user else None
        )
        await service.enroll(actor, bracket.id, entrant.id, seed=i)
    await service.start_bracket(actor, bracket.id)
    open_matches = await service.get_open_matches(bracket.id)
    return t, bracket, users, open_matches[0]


# ---------------------------------------------------------------------------
# schedule_bracket_match
# ---------------------------------------------------------------------------
class TestScheduleBracketMatch:
    async def test_creates_match_attaches_players_and_links(self, service):
        actor = await _staff()
        t, bracket, users, bmatch = await _linked_bracket(service, actor)

        match = await service.schedule_bracket_match(
            actor, bmatch.id, scheduled_date='2026-06-12', scheduled_time='14:30',
        )

        assert match.tournament_id == t.id
        player_ids = {p.user_id for p in await MatchPlayers.filter(match=match)}
        assert player_ids == {users[0].id, users[1].id}

        await bmatch.refresh_from_db()
        assert bmatch.match_id == match.id

    async def test_placeholder_entrant_rejected(self, service):
        actor = await _staff()
        _, _, _, bmatch = await _linked_bracket(service, actor, link_users=False)
        with pytest.raises(ValueError, match='players must be linked'):
            await service.schedule_bracket_match(
                actor, bmatch.id,
                scheduled_date='2026-06-12', scheduled_time='14:30',
            )

    async def test_non_open_match_rejected(self, service):
        actor = await _staff()
        _, _, _, bmatch = await _linked_bracket(service, actor)
        bmatch.state = BracketMatchState.PENDING
        await bmatch.save()
        with pytest.raises(ValueError, match="isn't ready to schedule"):
            await service.schedule_bracket_match(
                actor, bmatch.id,
                scheduled_date='2026-06-12', scheduled_time='14:30',
            )

    async def test_already_scheduled_rejected(self, service):
        actor = await _staff()
        t, _, _, bmatch = await _linked_bracket(service, actor)
        existing = await Match.create(tournament=t)
        bmatch.match = existing
        await bmatch.save()
        with pytest.raises(ValueError, match='already been scheduled'):
            await service.schedule_bracket_match(
                actor, bmatch.id,
                scheduled_date='2026-06-12', scheduled_time='14:30',
            )

    async def test_non_staff_rejected(self, service):
        actor = await _staff()
        _, _, _, bmatch = await _linked_bracket(service, actor)
        outsider = await _player(5000, 'outsider')
        with pytest.raises(PermissionError):
            await service.schedule_bracket_match(
                outsider, bmatch.id,
                scheduled_date='2026-06-12', scheduled_time='14:30',
            )


# ---------------------------------------------------------------------------
# list_open_matches_for_user
# ---------------------------------------------------------------------------
class TestListOpenMatchesForUser:
    async def test_returns_only_users_open_matches(self, service):
        actor = await _staff()
        _, bracket, users, bmatch = await _linked_bracket(service, actor)

        for user in users:
            got = await service.list_open_matches_for_user(user.id)
            assert [m.id for m in got] == [bmatch.id]

        # A user in no bracket match sees nothing.
        stranger = await _player(7777, 'stranger')
        assert await service.list_open_matches_for_user(stranger.id) == []

    async def test_scheduled_match_drops_off(self, service):
        actor = await _staff()
        _, _, users, bmatch = await _linked_bracket(service, actor)
        await service.schedule_bracket_match(
            actor, bmatch.id, scheduled_date='2026-06-12', scheduled_time='14:30',
        )
        assert await service.list_open_matches_for_user(users[0].id) == []


# ---------------------------------------------------------------------------
# advance_if_linked
# ---------------------------------------------------------------------------
class TestAdvanceIfLinked:
    async def _scheduled(self, service, actor):
        t, bracket, users, bmatch = await _linked_bracket(service, actor)
        match = await service.schedule_bracket_match(
            actor, bmatch.id, scheduled_date='2026-06-12', scheduled_time='14:30',
        )
        return bracket, users, bmatch, match

    async def test_advances_bracket_from_finish_rank(self, service):
        actor = await _staff()
        bracket, users, bmatch, match = await self._scheduled(service, actor)

        # users[0] wins.
        await MatchPlayers.filter(match=match, user=users[0]).update(finish_rank=1)
        await MatchPlayers.filter(match=match, user=users[1]).update(finish_rank=2)

        advanced = await service.advance_if_linked(match, actor)
        assert advanced is True

        await bmatch.refresh_from_db()
        assert bmatch.state == BracketMatchState.COMPLETE
        # The winning entry belongs to the entrant linked to users[0].
        winner = await service.repository.get_entry(bmatch.winner_id)
        entrant = await winner.entrant
        assert entrant.user_id == users[0].id

        # single-elim final resolved -> stage auto-completes.
        await bracket.refresh_from_db()
        assert bracket.state == BracketState.COMPLETE

    async def test_non_staff_confirmation_still_advances(self, service):
        # Regression: the auto-advance seam must NOT be Staff-gated. A Proctor (or
        # system user) confirming a linked match must still advance the bracket —
        # the Challonge peer push_match_result has no staff gate either.
        actor = await _staff()  # staff sets up + schedules the bracket
        bracket, users, bmatch, match = await self._scheduled(service, actor)
        proctor = await _proctor()
        assert await AuthService.is_staff(proctor) is False

        await MatchPlayers.filter(match=match, user=users[0]).update(finish_rank=1)
        await MatchPlayers.filter(match=match, user=users[1]).update(finish_rank=2)

        advanced = await service.advance_if_linked(match, proctor)
        assert advanced is True

        await bmatch.refresh_from_db()
        assert bmatch.state == BracketMatchState.COMPLETE
        winner = await service.repository.get_entry(bmatch.winner_id)
        entrant = await winner.entrant
        assert entrant.user_id == users[0].id

        # single-elim final resolved by a non-staff confirmation -> stage completes.
        await bracket.refresh_from_db()
        assert bracket.state == BracketState.COMPLETE

    async def test_unlinked_match_is_noop(self, service):
        actor = await _staff()
        t = await Tournament.create(name='Standalone')
        match = await Match.create(tournament=t)
        assert await service.advance_if_linked(match, actor) is False

    async def test_none_actor_is_noop(self, service):
        actor = await _staff()
        _, _, _, match = await self._scheduled(service, actor)
        assert await service.advance_if_linked(match, None) is False

    async def test_already_complete_is_noop_returns_true(self, service):
        actor = await _staff()
        bracket, users, bmatch, match = await self._scheduled(service, actor)
        # Refresh so saving doesn't clobber the ``match`` link set by scheduling.
        await bmatch.refresh_from_db()
        bmatch.state = BracketMatchState.COMPLETE
        await bmatch.save()
        # No finish_rank set; should short-circuit before touching players.
        assert await service.advance_if_linked(match, actor) is True


# ---------------------------------------------------------------------------
# Challonge exclusivity (symmetric guards)
# ---------------------------------------------------------------------------
class TestExclusivity:
    async def test_native_bracket_rejected_when_challonge_linked(self, service):
        actor = await _staff()
        t = await Tournament.create(name='T', challonge_tournament_id='T1')
        with pytest.raises(ValueError, match='never both'):
            await service.create_bracket(actor, t.id, 'Main', 'single_elim')

    async def test_challonge_link_rejected_when_native_bracket_exists(self, service):
        actor = await _staff()
        t = await Tournament.create(name='T')
        await service.create_bracket(actor, t.id, 'Main', 'single_elim')
        with pytest.raises(ValueError, match='native bracket'):
            await ChallongeService().link_tournament(t.id, 'https://challonge.com/x', actor)


# ---------------------------------------------------------------------------
# tenant scoping
# ---------------------------------------------------------------------------
async def test_bracket_match_not_schedulable_across_tenants(service, two_tenants):
    tenant_a, tenant_b = two_tenants
    with tenant_scope(tenant_a.id):
        actor = await _staff()
        _, _, _, bmatch = await _linked_bracket(service, actor)

    # From tenant B, the bracket match is invisible -> load-or-404.
    with tenant_scope(tenant_b.id):
        b_actor = await _staff(discord_id=4321, username='b-staff')
        with pytest.raises(Exception):
            await service.schedule_bracket_match(
                b_actor, bmatch.id,
                scheduled_date='2026-06-12', scheduled_time='14:30',
            )
