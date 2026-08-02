"""A player offering their own match for stream.

The two rules that make it advisory rather than a booking: only the match's own
players may offer, and the offer never touches ``is_stream_candidate``.
"""

import pytest

from application.events import EventType, event_bus
from application.services import MatchStreamVolunteerService
from models import Match, MatchPlayers, MatchStreamVolunteer, Tournament
from tests.factories import make_user, utc


@pytest.fixture
def captured_events():
    """Subscribe to the event bus for the test and collect published events."""
    seen = []
    token = event_bus.subscribe_sync(seen.append)
    yield seen
    event_bus.unsubscribe(token)


async def _match(*, started=False):
    t = await Tournament.create(name='T')
    m = await Match.create(
        tournament=t,
        scheduled_at=utc(2025, 1, 15, 19, 30),
        started_at=utc(2025, 1, 15, 19, 35) if started else None,
    )
    p1 = await make_user(discord_id=8001, username='p1')
    p2 = await make_user(discord_id=8002, username='p2')
    await MatchPlayers.create(match=m, user=p1)
    await MatchPlayers.create(match=m, user=p2)
    return m, p1, p2


class TestOffering:
    async def test_a_player_can_offer_their_own_match(self, db):
        m, p1, _ = await _match()

        await MatchStreamVolunteerService().volunteer(m.id, p1)

        assert await MatchStreamVolunteer.filter(match=m, user=p1).exists()

    async def test_offering_does_not_make_it_a_stream_candidate(self, db):
        """The whole point: a player's offer must not write staff's decision."""
        m, p1, _ = await _match()

        await MatchStreamVolunteerService().volunteer(m.id, p1)

        await m.refresh_from_db()
        assert m.is_stream_candidate is False

    async def test_a_non_player_is_refused(self, db):
        m, _, _ = await _match()
        outsider = await make_user(discord_id=8003, username='nosy')

        with pytest.raises(ValueError, match='players in a match'):
            await MatchStreamVolunteerService().volunteer(m.id, outsider)

    async def test_offering_twice_is_idempotent(self, db):
        m, p1, _ = await _match()
        service = MatchStreamVolunteerService()

        await service.volunteer(m.id, p1)
        await service.volunteer(m.id, p1)

        assert await MatchStreamVolunteer.filter(match=m, user=p1).count() == 1

    async def test_a_started_match_is_refused(self, db):
        """Nothing left for staff to schedule once it is under way."""
        m, p1, _ = await _match(started=True)

        with pytest.raises(ValueError, match='already started'):
            await MatchStreamVolunteerService().volunteer(m.id, p1)

    async def test_offering_publishes_the_event(self, db, captured_events):
        m, p1, _ = await _match()

        await MatchStreamVolunteerService().volunteer(m.id, p1)

        offered = [e for e in captured_events
                   if e.event_type == EventType.MATCH_STREAM_VOLUNTEERED]
        assert len(offered) == 1
        assert offered[0].payload['match_id'] == m.id
        assert offered[0].payload['tournament_id'] == m.tournament_id


class TestWithdrawing:
    async def test_a_player_can_take_the_offer_back(self, db):
        m, p1, _ = await _match()
        service = MatchStreamVolunteerService()
        await service.volunteer(m.id, p1)

        assert await service.withdraw(m.id, p1) is True
        assert not await MatchStreamVolunteer.filter(match=m, user=p1).exists()

    async def test_withdrawing_works_after_the_match_starts(self, db):
        """A player who changes their mind must not be stuck with the offer."""
        m, p1, _ = await _match()
        service = MatchStreamVolunteerService()
        await service.volunteer(m.id, p1)
        m.started_at = utc(2025, 1, 15, 19, 35)
        await m.save()

        assert await service.withdraw(m.id, p1) is True

    async def test_withdrawing_what_was_never_offered_is_a_no_op(self, db):
        m, p1, _ = await _match()

        assert await MatchStreamVolunteerService().withdraw(m.id, p1) is False


class TestReading:
    async def test_names_are_returned_per_match(self, db):
        m, p1, p2 = await _match()
        service = MatchStreamVolunteerService()
        await service.volunteer(m.id, p1)
        await service.volunteer(m.id, p2)

        assert sorted(await service.names_for_match(m)) == ['p1', 'p2']
        assert sorted((await service.names_by_match([m.id]))[m.id]) == ['p1', 'p2']

    async def test_the_viewers_own_offers_are_listed(self, db):
        m, p1, p2 = await _match()
        service = MatchStreamVolunteerService()
        await service.volunteer(m.id, p1)

        assert await service.list_volunteered_match_ids(p1) == [m.id]
        assert await service.list_volunteered_match_ids(p2) == []
        assert await service.has_volunteered(m.id, p1) is True
        assert await service.has_volunteered(m.id, p2) is False

    async def test_an_empty_id_list_costs_no_query(self, db):
        assert await MatchStreamVolunteerService().names_by_match([]) == {}
