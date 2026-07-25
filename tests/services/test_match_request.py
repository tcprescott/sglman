"""DB-backed tests for player-initiated match creation.

Covers ``MatchRequestMixin.submit_match_request``
(``application/services/match/match_request.py``) against the in-memory SQLite
``db`` fixture with a *real* ``MatchService``, matching the conventions in
``test_match_service_coverage.py`` — real roles rather than monkeypatched gates,
Discord fan-out captured by the autouse ``stub_discord_queue`` fixture.

Split out of that module when it outgrew the file-length guideline, alongside the
service split that produced ``match_request.py``.
"""

import itertools

import pytest

from application.events import EventType, event_bus
from application.services.match.match_service import MatchService
from models import (
    MatchAcknowledgment,
    MatchPlayers,
    Tournament,
    TournamentPlayers,
    User,
    UserRole,
)

_discord_ids = itertools.count(31000)


async def make_user(username="player", display_name=None, roles=None):
    user = await User.create(
        discord_id=next(_discord_ids),
        username=username,
        display_name=display_name if display_name is not None else username,
    )
    for role in roles or []:
        await UserRole.create(user=user, role=role)
    return user


async def make_tournament(**overrides):
    fields = dict(name="Test Tournament", players_per_match=2, seed_generator=None)
    fields.update(overrides)
    return await Tournament.create(**fields)


@pytest.fixture
async def service():
    return MatchService()


@pytest.fixture
def captured_events():
    seen = []
    token = event_bus.subscribe_sync(seen.append)
    yield seen
    event_bus.unsubscribe(token)


class TestSubmitMatchRequest:
    async def test_requires_login(self, service, db):
        with pytest.raises(PermissionError, match="Login required"):
            await service.submit_match_request(
                tournament_id=1,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[1],
                actor=None,
            )

    async def test_actor_must_be_a_player(self, service, db):
        t = await make_tournament()
        actor = await make_user("selfless")
        other = await make_user("other")
        with pytest.raises(PermissionError, match="only submit match requests where you are a player"):
            await service.submit_match_request(
                tournament_id=t.id,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[other.id],
                actor=actor,
            )

    async def test_invalid_datetime_raises(self, service, db):
        t = await make_tournament()
        actor = await make_user("p")
        with pytest.raises(ValueError, match="Invalid date/time format"):
            await service.submit_match_request(
                tournament_id=t.id,
                scheduled_date="nope",
                scheduled_time="14:30",
                player_ids=[actor.id],
                actor=actor,
            )

    async def test_missing_opponent_user_raises(self, service, db):
        t = await make_tournament()
        actor = await make_user("p")
        with pytest.raises(ValueError, match="not found"):
            await service.submit_match_request(
                tournament_id=t.id,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[actor.id, 424242],
                actor=actor,
            )

    async def test_bracket_run_tournament_refuses_requests(self, service, db):
        """The enforcement behind the dialog's filtered dropdown."""
        t = await make_tournament()
        t.allow_player_match_requests = False
        await t.save()
        actor = await make_user("p1", "P1")
        opponent = await make_user("p2", "P2")
        with pytest.raises(PermissionError, match="scheduled from its bracket"):
            await service.submit_match_request(
                tournament_id=t.id,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[actor.id, opponent.id],
                actor=actor,
            )

    async def test_from_bracket_bypasses_the_toggle(self, service, db):
        """Scheduling *through* the bracket is the path the toggle forces."""
        t = await make_tournament()
        t.allow_player_match_requests = False
        await t.save()
        actor = await make_user("p1", "P1")
        opponent = await make_user("p2", "P2")
        match = await service.submit_match_request(
            tournament_id=t.id,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[actor.id, opponent.id],
            actor=actor,
            from_bracket=True,
        )
        assert match.tournament_id == t.id

    async def test_title_is_stored(self, service, db):
        t = await make_tournament()
        actor = await make_user("p1", "P1")
        opponent = await make_user("p2", "P2")
        match = await service.submit_match_request(
            tournament_id=t.id,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[actor.id, opponent.id],
            actor=actor,
            title="Cup: P1 vs P2 — Game 2 of 3",
            from_bracket=True,
        )
        assert match.title == "Cup: P1 vs P2 — Game 2 of 3"

    async def test_happy_path_creates_and_enrolls(self, service, db, captured_events):
        t = await make_tournament()
        actor = await make_user("p1", "P1")
        opponent = await make_user("p2", "P2")
        match = await service.submit_match_request(
            tournament_id=t.id,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[actor.id, opponent.id],
            actor=actor,
            comment="req",
        )
        assert match.comment == "req"
        assert {p.user_id for p in await MatchPlayers.filter(match=match)} == {actor.id, opponent.id}
        assert await TournamentPlayers.filter(tournament=t, user=opponent).exists()
        # actor auto-acked, opponent pending
        assert (await MatchAcknowledgment.get(match=match, user=actor)).acknowledged_at is not None
        assert (await MatchAcknowledgment.get(match=match, user=opponent)).acknowledged_at is None
        assert EventType.MATCH_CREATED in [e.event_type for e in captured_events]
