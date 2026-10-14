"""Comments on a match, and who reads which.

The audience rules are the feature: a player's comment reaches staff and never
the opponent, a private staff note never reaches players, and only a staff
message to players DMs them.
"""

import pytest

import application.services.discord as discord_pkg
from application.events import EventType, event_bus
from application.services import MatchCommentService
from models import Match, MatchComment, MatchCommentKind, MatchPlayers, Role, Tournament, UserRole
from tests.factories import make_user, utc


@pytest.fixture
def captured_events():
    seen = []
    token = event_bus.subscribe_sync(seen.append)
    yield seen
    event_bus.unsubscribe(token)


@pytest.fixture
def dms(monkeypatch):
    pending = []
    monkeypatch.setattr(discord_pkg.discord_queue, 'enqueue', pending.append)
    yield pending
    for coro in pending:
        coro.close()


async def _match():
    t = await Tournament.create(name='T')
    m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
    p1 = await make_user(discord_id=8001, username='p1')
    p2 = await make_user(discord_id=8002, username='p2')
    await MatchPlayers.create(match=m, user=p1)
    await MatchPlayers.create(match=m, user=p2)
    return m, p1, p2


async def _with_role(discord_id: int, role: Role):
    user = await make_user(discord_id=discord_id, username=f'{role.value}-{discord_id}')
    await UserRole.create(user=user, role=role, tenant_id=1)
    return user


class TestPlayerComments:
    async def test_a_player_comments_and_staff_read_it(self, db):
        m, p1, _ = await _match()
        staff = await _with_role(9001, Role.STAFF)
        service = MatchCommentService()

        await service.add_player_comment(m.id, p1, "I'll be ten minutes late")

        seen = await service.list_for_viewer(m.id, staff)
        assert [(c['kind'], c['author'], c['body']) for c in seen] == [
            ('player', p1.preferred_name, "I'll be ten minutes late"),
        ]

    async def test_the_opponent_never_sees_it(self, db):
        m, p1, p2 = await _match()
        service = MatchCommentService()

        await service.add_player_comment(m.id, p1, 'Between me and staff')

        assert await service.list_for_viewer(m.id, p2) == []
        mine = await service.list_for_viewer(m.id, p1)
        assert [c['own'] for c in mine] == [True]

    async def test_a_non_player_is_refused(self, db):
        m, _, _ = await _match()
        outsider = await make_user(discord_id=8003, username='nosy')

        with pytest.raises(ValueError, match='players in a match'):
            await MatchCommentService().add_player_comment(m.id, outsider, 'hi')

    async def test_an_empty_comment_is_refused(self, db):
        m, p1, _ = await _match()

        with pytest.raises(ValueError, match='Write something'):
            await MatchCommentService().add_player_comment(m.id, p1, '   ')


class TestStaffComments:
    async def test_a_private_note_stays_with_staff(self, db, dms):
        m, p1, p2 = await _match()
        staff = await _with_role(9001, Role.STAFF)
        service = MatchCommentService()

        await service.add_staff_comment(m.id, staff, 'Watch the controller', to_players=False)

        assert await service.list_for_viewer(m.id, p1) == []
        assert await service.list_for_viewer(m.id, p2) == []
        assert [c['kind'] for c in await service.list_for_viewer(m.id, staff)] == ['staff_private']
        assert dms == []

    async def test_a_message_to_players_reaches_both_and_dms_them(self, db, dms):
        m, p1, p2 = await _match()
        staff = await _with_role(9001, Role.STAFF)
        service = MatchCommentService()

        await service.add_staff_comment(m.id, staff, 'Moved to station 4', to_players=True)

        for player in (p1, p2):
            seen = await service.list_for_viewer(m.id, player)
            assert [(c['kind'], c['can_delete']) for c in seen] == [('staff_to_players', False)]
        assert len(dms) == 1

    async def test_no_dm_when_every_player_switched_it_off(self, db, dms):
        m, p1, p2 = await _match()
        for p in (p1, p2):
            p.dm_match_comments = False
            await p.save()
        staff = await _with_role(9001, Role.STAFF)

        await MatchCommentService().add_staff_comment(m.id, staff, 'Moved', to_players=True)

        assert dms == []

    async def test_a_proctor_may_comment_as_staff(self, db, dms):
        m, _, _ = await _match()
        proctor = await _with_role(9002, Role.PROCTOR)

        await MatchCommentService().add_staff_comment(m.id, proctor, 'Seated', to_players=False)

        assert await MatchComment.filter(match=m, kind=MatchCommentKind.STAFF_PRIVATE).count() == 1

    async def test_a_player_cannot_post_as_staff(self, db, dms):
        m, p1, _ = await _match()

        with pytest.raises(ValueError, match='permission'):
            await MatchCommentService().add_staff_comment(m.id, p1, 'hi', to_players=True)

    async def test_staff_see_every_kind(self, db, dms):
        m, p1, _ = await _match()
        staff = await _with_role(9001, Role.STAFF)
        service = MatchCommentService()
        await service.add_player_comment(m.id, p1, 'a')
        await service.add_staff_comment(m.id, staff, 'b', to_players=False)
        await service.add_staff_comment(m.id, staff, 'c', to_players=True)

        seen = await service.list_for_viewer(m.id, staff)

        assert [c['kind'] for c in seen] == ['player', 'staff_private', 'staff_to_players']


class TestDeleting:
    async def test_an_author_deletes_their_own(self, db):
        m, p1, _ = await _match()
        service = MatchCommentService()
        comment = await service.add_player_comment(m.id, p1, 'oops')

        await service.delete_comment(comment.id, p1)

        assert not await MatchComment.filter(id=comment.id).exists()

    async def test_staff_delete_anyones(self, db):
        m, p1, _ = await _match()
        staff = await _with_role(9001, Role.STAFF)
        service = MatchCommentService()
        comment = await service.add_player_comment(m.id, p1, 'spam')

        await service.delete_comment(comment.id, staff)

        assert not await MatchComment.filter(id=comment.id).exists()

    async def test_a_player_cannot_delete_a_staff_message(self, db, dms):
        m, p1, _ = await _match()
        staff = await _with_role(9001, Role.STAFF)
        service = MatchCommentService()
        comment = await service.add_staff_comment(m.id, staff, 'Moved', to_players=True)

        with pytest.raises(ValueError, match='your own'):
            await service.delete_comment(comment.id, p1)


class TestCountsAndEvents:
    async def test_counts_split_player_and_staff(self, db, dms):
        m, p1, p2 = await _match()
        staff = await _with_role(9001, Role.STAFF)
        service = MatchCommentService()
        await service.add_player_comment(m.id, p1, 'a')
        await service.add_player_comment(m.id, p2, 'b')
        await service.add_staff_comment(m.id, staff, 'c', to_players=False)
        await service.add_staff_comment(m.id, staff, 'd', to_players=True)

        assert await service.counts_by_match([m.id]) == {m.id: {'player': 2, 'staff': 2}}
        assert await service.counts_by_match([]) == {}

    async def test_events_carry_the_kind(self, db, dms, captured_events):
        m, p1, _ = await _match()
        service = MatchCommentService()
        comment = await service.add_player_comment(m.id, p1, 'hello')
        await service.delete_comment(comment.id, p1)

        added = [e for e in captured_events if e.event_type == EventType.MATCH_COMMENT_ADDED]
        deleted = [e for e in captured_events if e.event_type == EventType.MATCH_COMMENT_DELETED]
        assert added[0].payload['kind'] == 'player'
        assert added[0].payload['tournament_id'] == m.tournament_id
        assert 'body' not in added[0].payload
        assert deleted[0].payload['comment_id'] == comment.id

    async def test_only_messages_to_players_carry_their_text(self, db, dms, captured_events):
        m, _, _ = await _match()
        staff = await _with_role(8101, Role.STAFF)
        service = MatchCommentService()
        await service.add_staff_comment(m.id, staff, 'private', to_players=False)
        await service.add_staff_comment(m.id, staff, 'start at 3', to_players=True)

        added = [e.payload for e in captured_events if e.event_type == EventType.MATCH_COMMENT_ADDED]
        assert [(p['kind'], p.get('body')) for p in added] == [
            ('staff_private', None), ('staff_to_players', 'start at 3'),
        ]

    async def test_a_player_is_limited_per_minute_but_staff_are_not(self, db, dms):
        from application.services.match.match_comment_service import PLAYER_COMMENTS_PER_MINUTE

        m, p1, p2 = await _match()
        staff = await _with_role(8102, Role.STAFF)
        service = MatchCommentService()
        for n in range(PLAYER_COMMENTS_PER_MINUTE):
            await service.add_player_comment(m.id, p1, f'spam {n}')
        with pytest.raises(ValueError, match='Slow down'):
            await service.add_player_comment(m.id, p1, 'one more')
        await service.add_player_comment(m.id, p2, 'the opponent is unaffected')
        for n in range(PLAYER_COMMENTS_PER_MINUTE + 1):
            await service.add_staff_comment(m.id, staff, f'note {n}', to_players=False)
