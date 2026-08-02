"""Players asking staff to move or call off a match.

Three things carry the design and each has tests here: only a match's own
players may ask, approving *performs* the change through ``MatchService``
rather than blessing it, and deciding needs the same authority that editing the
match needs.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from application.events import EventType, event_bus
from application.services import MatchRescheduleService
from models import (
    Match,
    MatchPlayers,
    MatchRescheduleRequest,
    RescheduleRequestKind,
    RescheduleRequestStatus,
    Role,
    SpeedGamingEpisode,
    Tournament,
    UserRole,
)
from tests.factories import make_user, utc


@pytest.fixture
def captured_events():
    seen = []
    token = event_bus.subscribe_sync(seen.append)
    yield seen
    event_bus.unsubscribe(token)


def _soon(hours: int = 6) -> datetime:
    """A real future instant — the service rejects a proposal in the past."""
    return datetime.now(timezone.utc) + timedelta(hours=hours)


async def _match(*, seated=False, started=False, scheduled=True, sg=False, allow=True):
    t = await Tournament.create(name='T', allow_reschedule_requests=allow)
    m = await Match.create(
        tournament=t,
        scheduled_at=utc(2025, 1, 15, 19, 30) if scheduled else None,
        seated_at=utc(2025, 1, 15, 19, 25) if seated else None,
        started_at=utc(2025, 1, 15, 19, 35) if started else None,
    )
    if sg:
        episode = await SpeedGamingEpisode.create(sg_episode_id='ep-1')
        m.speedgaming_episode_id = episode.id
        await m.save()
    p1 = await make_user(discord_id=9001, username='p1')
    p2 = await make_user(discord_id=9002, username='p2')
    await MatchPlayers.create(match=m, user=p1)
    await MatchPlayers.create(match=m, user=p2)
    # Reloaded so ``match.players`` is prefetched the way the service reads it.
    return m, p1, p2


async def _staff(discord_id=9100):
    user = await make_user(discord_id=discord_id, username='boss')
    await UserRole.create(user=user, role=Role.STAFF)
    return user


async def _submit(match, actor, **kwargs):
    kwargs.setdefault('reason', 'work clash')
    return await MatchRescheduleService().submit(match.id, actor, **kwargs)


class TestSubmitting:
    async def test_a_player_can_ask_for_their_own_match(self, db):
        m, p1, _ = await _match()

        request = await _submit(m, p1, proposed_at=_soon())

        assert request.status is RescheduleRequestStatus.PENDING
        assert request.requested_by_id == p1.id

    async def test_the_original_time_is_snapshotted(self, db):
        """Approving overwrites scheduled_at, so what it moved *from* is captured now."""
        m, p1, _ = await _match()

        request = await _submit(m, p1, proposed_at=_soon())

        assert request.original_scheduled_at == m.scheduled_at

    async def test_a_non_player_is_refused(self, db):
        m, _, _ = await _match()
        outsider = await make_user(discord_id=9003, username='nosy')

        with pytest.raises(PermissionError, match='players in a match'):
            await _submit(m, outsider, proposed_at=_soon())

    async def test_staff_are_refused_too(self, db):
        """Not an oversight: staff already move matches directly."""
        m, _, _ = await _match()
        boss = await _staff()

        with pytest.raises(PermissionError):
            await _submit(m, boss, proposed_at=_soon())

    async def test_a_match_under_way_is_refused(self, db):
        m, p1, _ = await _match(seated=True)

        with pytest.raises(ValueError, match='under way'):
            await _submit(m, p1, proposed_at=_soon())

    async def test_an_unscheduled_match_is_refused(self, db):
        m, p1, _ = await _match(scheduled=False)

        with pytest.raises(ValueError, match="doesn't have a time"):
            await _submit(m, p1, proposed_at=_soon())

    async def test_a_speedgaming_match_is_refused(self, db):
        """Its time belongs to the next sync, so no one here could approve it."""
        m, p1, _ = await _match(sg=True)

        with pytest.raises(ValueError, match='SpeedGaming'):
            await _submit(m, p1, proposed_at=_soon())

    async def test_a_tournament_can_turn_requests_off(self, db):
        m, p1, _ = await _match(allow=False)

        with pytest.raises(PermissionError, match="doesn't take reschedule requests"):
            await _submit(m, p1, proposed_at=_soon())

    async def test_a_reason_is_required(self, db):
        m, p1, _ = await _match()

        with pytest.raises(ValueError, match='Say why'):
            await _submit(m, p1, reason='   ', proposed_at=_soon())

    async def test_a_past_time_is_refused(self, db):
        m, p1, _ = await _match()

        with pytest.raises(ValueError, match='in the future'):
            await _submit(m, p1, proposed_at=utc(2020, 1, 1, 12, 0))

    async def test_only_one_open_request_per_player(self, db):
        m, p1, _ = await _match()
        await _submit(m, p1, proposed_at=_soon())

        with pytest.raises(ValueError, match='already have a request'):
            await _submit(m, p1, proposed_at=_soon(8))

    async def test_the_opponent_may_still_ask_separately(self, db):
        """The cap is per player, not per match — both may have a live ask."""
        m, p1, p2 = await _match()
        await _submit(m, p1, proposed_at=_soon())

        await _submit(m, p2, proposed_at=_soon(9))

        assert await MatchRescheduleRequest.filter(
            match=m, status=RescheduleRequestStatus.PENDING,
        ).count() == 2

    async def test_a_cancellation_proposes_no_time(self, db):
        m, p1, _ = await _match()

        request = await _submit(
            m, p1, kind=RescheduleRequestKind.CANCEL, proposed_at=_soon(),
        )

        assert request.proposed_at is None

    async def test_it_publishes_a_domain_event(self, db, captured_events):
        m, p1, _ = await _match()

        await _submit(m, p1, proposed_at=_soon())

        assert any(
            e.event_type == EventType.MATCH_RESCHEDULE_REQUESTED
            for e in captured_events
        )


class TestOpponentAgreement:
    async def test_the_other_player_can_agree(self, db):
        m, p1, p2 = await _match()
        request = await _submit(m, p1, proposed_at=_soon())

        await MatchRescheduleService().record_opponent_agreement(request.id, p2)

        await request.refresh_from_db()
        assert request.opponent_agreed_at is not None

    async def test_agreement_does_not_decide_anything(self, db):
        """A signal, not a gate: the request is still waiting on staff."""
        m, p1, p2 = await _match()
        request = await _submit(m, p1, proposed_at=_soon())

        await MatchRescheduleService().record_opponent_agreement(request.id, p2)

        await request.refresh_from_db()
        assert request.status is RescheduleRequestStatus.PENDING

    async def test_the_requester_cannot_agree_with_themselves(self, db):
        m, p1, _ = await _match()
        request = await _submit(m, p1, proposed_at=_soon())

        with pytest.raises(PermissionError, match='your own request'):
            await MatchRescheduleService().record_opponent_agreement(request.id, p1)

    async def test_an_outsider_cannot_agree(self, db):
        m, p1, _ = await _match()
        request = await _submit(m, p1, proposed_at=_soon())
        outsider = await make_user(discord_id=9004, username='nosy')

        with pytest.raises(PermissionError, match='other player'):
            await MatchRescheduleService().record_opponent_agreement(request.id, outsider)


class TestWithdrawing:
    async def test_the_requester_can_take_it_back(self, db):
        m, p1, _ = await _match()
        request = await _submit(m, p1, proposed_at=_soon())

        await MatchRescheduleService().withdraw(request.id, p1)

        await request.refresh_from_db()
        assert request.status is RescheduleRequestStatus.WITHDRAWN

    async def test_nobody_else_can(self, db):
        m, p1, p2 = await _match()
        request = await _submit(m, p1, proposed_at=_soon())

        with pytest.raises(PermissionError, match='who asked'):
            await MatchRescheduleService().withdraw(request.id, p2)


class TestApproving:
    async def test_it_moves_the_match(self, db):
        """The core promise: approving performs the change, not just records it."""
        m, p1, _ = await _match()
        boss = await _staff()
        when = _soon()
        request = await _submit(m, p1, proposed_at=when)

        with patch(
            'application.services.match.match_service.MatchService.update_match',
            new_callable=AsyncMock,
        ) as update:
            await MatchRescheduleService().approve(request.id, boss)

        update.assert_awaited_once()
        assert update.await_args.kwargs['scheduled_at'] == when
        assert update.await_args.kwargs['actor'] == boss

    async def test_staff_can_counter_with_a_different_time(self, db):
        m, p1, _ = await _match()
        boss = await _staff()
        request = await _submit(m, p1, proposed_at=_soon())
        theirs = _soon(20)

        with patch(
            'application.services.match.match_service.MatchService.update_match',
            new_callable=AsyncMock,
        ) as update:
            await MatchRescheduleService().approve(request.id, boss, scheduled_at=theirs)

        assert update.await_args.kwargs['scheduled_at'] == theirs

    async def test_a_cancellation_calls_the_match_off(self, db):
        m, p1, _ = await _match()
        boss = await _staff()
        request = await _submit(m, p1, kind=RescheduleRequestKind.CANCEL)

        with patch(
            'application.services.match.match_service.MatchService.cancel_match',
            new_callable=AsyncMock,
        ) as cancel:
            await MatchRescheduleService().approve(request.id, boss)

        cancel.assert_awaited_once()

    async def test_a_request_with_no_time_needs_one(self, db):
        """"You pick" is a valid ask; approving it blind is not a valid answer."""
        m, p1, _ = await _match()
        boss = await _staff()
        request = await _submit(m, p1)

        with pytest.raises(ValueError, match="didn't name a time"):
            await MatchRescheduleService().approve(request.id, boss)

    async def test_a_player_cannot_approve_their_own_request(self, db):
        m, p1, _ = await _match()
        request = await _submit(m, p1, proposed_at=_soon())

        with pytest.raises(PermissionError):
            await MatchRescheduleService().approve(request.id, p1)

    async def test_the_opponent_cannot_approve_it_either(self, db):
        """Agreement is the opponent's whole power — deciding is not theirs."""
        m, p1, p2 = await _match()
        request = await _submit(m, p1, proposed_at=_soon())

        with pytest.raises(PermissionError):
            await MatchRescheduleService().approve(request.id, p2)

    async def test_a_failed_move_leaves_the_request_pending(self, db):
        """Perform-then-record: never 'approved' over a schedule that did not budge."""
        m, p1, _ = await _match()
        boss = await _staff()
        request = await _submit(m, p1, proposed_at=_soon())

        with patch(
            'application.services.match.match_service.MatchService.update_match',
            new_callable=AsyncMock, side_effect=ValueError('outside tournament hours'),
        ):
            with pytest.raises(ValueError, match='outside tournament hours'):
                await MatchRescheduleService().approve(request.id, boss)

        await request.refresh_from_db()
        assert request.status is RescheduleRequestStatus.PENDING

    async def test_the_other_open_request_is_superseded_not_declined(self, db):
        """Staff refused nobody; the match simply stopped being in question."""
        m, p1, p2 = await _match()
        boss = await _staff()
        mine = await _submit(m, p1, proposed_at=_soon())
        theirs = await _submit(m, p2, proposed_at=_soon(9))

        with patch(
            'application.services.match.match_service.MatchService.update_match',
            new_callable=AsyncMock,
        ):
            await MatchRescheduleService().approve(mine.id, boss)

        await theirs.refresh_from_db()
        assert theirs.status is RescheduleRequestStatus.SUPERSEDED

    async def test_deciding_twice_is_refused(self, db):
        m, p1, _ = await _match()
        boss = await _staff()
        request = await _submit(m, p1, proposed_at=_soon())

        with patch(
            'application.services.match.match_service.MatchService.update_match',
            new_callable=AsyncMock,
        ):
            await MatchRescheduleService().approve(request.id, boss)

            with pytest.raises(ValueError, match='already been decided'):
                await MatchRescheduleService().approve(request.id, boss)


class TestDeclining:
    async def test_it_records_staffs_words(self, db):
        m, p1, _ = await _match()
        boss = await _staff()
        request = await _submit(m, p1, proposed_at=_soon())

        await MatchRescheduleService().decline(request.id, boss, 'restream is locked in')

        await request.refresh_from_db()
        assert request.status is RescheduleRequestStatus.DECLINED
        assert request.decision_note == 'restream is locked in'
        assert request.decided_by_id == boss.id

    async def test_a_bare_no_is_refused(self, db):
        """A refusal with no reason is what this feature exists to replace."""
        m, p1, _ = await _match()
        boss = await _staff()
        request = await _submit(m, p1, proposed_at=_soon())

        with pytest.raises(ValueError, match='Say why'):
            await MatchRescheduleService().decline(request.id, boss, '   ')

    async def test_declining_leaves_the_match_alone(self, db):
        m, p1, _ = await _match()
        boss = await _staff()
        before = m.scheduled_at
        request = await _submit(m, p1, proposed_at=_soon())

        await MatchRescheduleService().decline(request.id, boss, 'no room')

        await m.refresh_from_db()
        assert m.scheduled_at == before

    async def test_a_player_cannot_decline(self, db):
        m, p1, p2 = await _match()
        request = await _submit(m, p1, proposed_at=_soon())

        with pytest.raises(PermissionError):
            await MatchRescheduleService().decline(request.id, p2, 'nope')


class TestReads:
    async def test_a_player_sees_their_own_requests(self, db):
        m, p1, p2 = await _match()
        mine = await _submit(m, p1, proposed_at=_soon())
        await _submit(m, p2, proposed_at=_soon(9))

        rows = await MatchRescheduleService().list_mine(p1)

        assert [r.id for r in rows] == [mine.id]

    async def test_the_queue_holds_only_pending_ones(self, db):
        m, p1, p2 = await _match()
        boss = await _staff()
        await _submit(m, p1, proposed_at=_soon())
        decided = await _submit(m, p2, proposed_at=_soon(9))
        await MatchRescheduleService().decline(decided.id, boss, 'no')

        assert await MatchRescheduleService().pending_count() == 1

    async def test_can_request_is_false_once_one_is_open(self, db):
        """What hides the button, so it is never shown only to be refused."""
        m, p1, _ = await _match()
        service = MatchRescheduleService()
        assert await service.can_request(m, p1) is True

        await _submit(m, p1, proposed_at=_soon())

        assert await service.can_request(m, p1) is False

    async def test_can_request_is_false_for_a_non_player(self, db):
        m, _, _ = await _match()
        outsider = await make_user(discord_id=9005, username='nosy')

        assert await MatchRescheduleService().can_request(m, outsider) is False

    async def test_can_request_is_false_when_signed_out(self, db):
        m, _, _ = await _match()

        assert await MatchRescheduleService().can_request(m, None) is False
