"""DB-backed coverage tests for MatchService.

Exercises the large untested regions of ``application/services/match_service.py``
against the in-memory SQLite ``db`` fixture with a *real* ``MatchService`` (real
repositories, real ``MatchScheduleService``). Permission gates are satisfied by
granting real roles / tournament-admin membership rather than monkeypatching, so
the service's own auth branches are exercised end-to-end. Discord fan-out is
captured (never awaited) by the autouse ``stub_discord_queue`` fixture in
``tests/services/conftest.py``.

The happy-path event fan-out for a handful of methods is already covered with
mocks in ``test_match_service.py``; here we focus on the untested method bodies,
error paths, enrollment, and the player/crew sync helpers.
"""

import itertools
import json
from datetime import datetime, timezone

import pytest

from application.events import EventType, event_bus
from application.services.match_service import MatchService
from application.services.system_config_service import KEY_TOURNAMENT_HOURS, KEY_STATION_FORMAT
from models import (
    Commentator,
    Match,
    MatchAcknowledgment,
    MatchPlayers,
    Role,
    StreamRoom,
    SystemConfiguration,
    Tournament,
    TournamentPlayers,
    Tracker,
    User,
    UserRole,
)

UTC = timezone.utc

_discord_ids = itertools.count(9000)


def utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


async def make_user(username="player", display_name=None, roles=None):
    user = await User.create(
        discord_id=next(_discord_ids),
        username=username,
        display_name=display_name if display_name is not None else username,
    )
    for role in roles or []:
        await UserRole.create(user=user, role=role)
    return user


async def make_staff(username="staff"):
    return await make_user(username=username, roles=[Role.STAFF])


async def make_tournament(**overrides):
    fields = dict(name="Test Tournament", players_per_match=2, seed_generator=None)
    fields.update(overrides)
    return await Tournament.create(**fields)


@pytest.fixture
async def service():
    # Constructed inside the running loop: MatchService -> MatchScheduleService ->
    # DiscordService lazily builds a discord.py Bot whose __init__ calls
    # asyncio.get_event_loop(), which needs a live loop on Python 3.13.
    return MatchService()


@pytest.fixture
def captured_events():
    seen = []
    token = event_bus.subscribe_sync(seen.append)
    yield seen
    event_bus.unsubscribe(token)


# ---------------------------------------------------------------------------
# Simple read/query surface
# ---------------------------------------------------------------------------


class TestReadMethods:
    async def test_get_match_by_id_and_get_by_id(self, service, db):
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        assert (await service.get_match_by_id(match.id)).id == match.id
        assert (await service.get_by_id(match.id, prefetch_relations=False)).id == match.id
        assert await service.get_match_by_id(999999) is None

    async def test_get_match_players_and_player_names(self, service, db):
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        alice = await make_user("alice", "Alice")
        bob = await make_user("bob", "Bob")
        await MatchPlayers.create(match=match, user=alice)
        await MatchPlayers.create(match=match, user=bob)

        players = await service.get_match_players(match)
        assert {p.user_id for p in players} == {alice.id, bob.id}

        names = await service.get_player_names(match.id)
        assert "Alice" in names and "Bob" in names

    async def test_get_player_names_empty(self, service, db):
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        assert await service.get_player_names(match.id) == ""

    async def test_list_acknowledgments(self, service, db):
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        user = await make_user()
        await MatchAcknowledgment.create(match=match, user=user)
        acks = await service.list_acknowledgments(match)
        assert len(acks) == 1

    async def test_get_all_matches_for_schedule(self, service, db):
        t = await make_tournament()
        await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        await Match.create(tournament=t, scheduled_at=utc(2025, 1, 16, 18))
        assert len(await service.get_all_matches_for_schedule()) == 2

    async def test_get_matches_for_date_and_grouping(self, service, db):
        t = await make_tournament()
        room = await StreamRoom.create(name="Stage 1")
        await Match.create(tournament=t, stream_room=room, scheduled_at=utc(2025, 1, 15, 18))
        # excluded: no stream room
        await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19))

        matches = await service.get_matches_for_date(datetime(2025, 1, 15).date())
        assert len(matches) == 1

        grouped = await service.group_matches_by_stream_room(matches)
        assert room.id in grouped
        stored_room, room_matches = grouped[room.id]
        assert stored_room.id == room.id and len(room_matches) == 1

    async def test_get_matches_for_player(self, service, db):
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        user = await make_user()
        await MatchPlayers.create(match=match, user=user)
        found = await service.get_matches_for_player(str(user.discord_id))
        assert [m.id for m in found] == [match.id]


# ---------------------------------------------------------------------------
# create_match
# ---------------------------------------------------------------------------


class TestCreateMatch:
    async def test_full_create_with_crew_and_stream_candidate(self, service, db, captured_events):
        actor = await make_staff()
        t = await make_tournament()
        room = await StreamRoom.create(name="Stage A")
        alice = await make_user("alice", "Alice")
        bob = await make_user("bob", "Bob")
        commentator = await make_user("carl", "Carl")
        tracker = await make_user("dana", "Dana")

        match = await service.create_match(
            tournament_id=t.id,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[alice.id, bob.id],
            comment="gogo",
            stream_room_id=room.id,
            commentator_ids=[commentator.id],
            tracker_ids=[tracker.id],
            is_stream_candidate=True,
            actor=actor,
        )

        assert match.is_stream_candidate is True
        assert match.comment == "gogo"
        assert match.stream_room_id == room.id

        player_ids = {p.user_id for p in await MatchPlayers.filter(match=match)}
        assert player_ids == {alice.id, bob.id}
        # fresh players are auto-enrolled in the tournament (covers enrollment branch)
        assert await TournamentPlayers.filter(tournament=t, user=alice).exists()

        comms = await Commentator.filter(match=match)
        assert len(comms) == 1 and comms[0].user_id == commentator.id and comms[0].approved is True
        trks = await Tracker.filter(match=match)
        assert len(trks) == 1 and trks[0].user_id == tracker.id and trks[0].approved is True

        # actor is not a player here, so nobody is auto-acked
        acks = await MatchAcknowledgment.filter(match=match)
        assert {a.user_id for a in acks} == {alice.id, bob.id}
        assert all(a.acknowledged_at is None for a in acks)

        assert EventType.MATCH_CREATED in [e.event_type for e in captured_events]

    async def test_actor_who_is_player_is_auto_acked(self, service, db):
        actor = await make_staff("boss")
        t = await make_tournament()
        opponent = await make_user("opp", "Opp")
        match = await service.create_match(
            tournament_id=t.id,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[actor.id, opponent.id],
            actor=actor,
        )
        actor_ack = await MatchAcknowledgment.get(match=match, user=actor)
        opp_ack = await MatchAcknowledgment.get(match=match, user=opponent)
        assert actor_ack.acknowledged_at is not None and actor_ack.auto_acknowledged is True
        assert opp_ack.acknowledged_at is None

    async def test_tournament_admin_may_create_without_staff_role(self, service, db):
        # non-staff actor that is a tournament admin exercises the else/ensure branch
        actor = await make_user("ta")
        t = await make_tournament()
        await t.admins.add(actor)
        player = await make_user()
        match = await service.create_match(
            tournament_id=t.id,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[player.id],
            actor=actor,
        )
        assert match.id is not None

    async def test_non_admin_actor_denied(self, service, db):
        actor = await make_user("nobody")
        t = await make_tournament()
        player = await make_user()
        with pytest.raises(PermissionError):
            await service.create_match(
                tournament_id=t.id,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[player.id],
                actor=actor,
            )

    async def test_missing_player_user_raises(self, service, db):
        actor = await make_staff()
        t = await make_tournament()
        with pytest.raises(ValueError, match="User 424242 not found"):
            await service.create_match(
                tournament_id=t.id,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[424242],
                actor=actor,
            )

    async def test_missing_commentator_user_raises(self, service, db):
        actor = await make_staff()
        t = await make_tournament()
        player = await make_user()
        with pytest.raises(ValueError, match="not found"):
            await service.create_match(
                tournament_id=t.id,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[player.id],
                commentator_ids=[424242],
                actor=actor,
            )

    async def test_missing_tracker_user_raises(self, service, db):
        actor = await make_staff()
        t = await make_tournament()
        player = await make_user()
        with pytest.raises(ValueError, match="not found"):
            await service.create_match(
                tournament_id=t.id,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[player.id],
                tracker_ids=[424242],
                actor=actor,
            )

    async def test_within_configured_hours_succeeds(self, service, db):
        await SystemConfiguration.create(
            name=KEY_TOURNAMENT_HOURS,
            value=json.dumps({"2025-01-15": {"open": "00:00", "close": "23:00"}}),
        )
        actor = await make_staff()
        t = await make_tournament()
        player = await make_user()
        match = await service.create_match(
            tournament_id=t.id,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[player.id],
            actor=actor,
        )
        assert match.id is not None

    async def test_outside_configured_hours_raises(self, service, db):
        await SystemConfiguration.create(
            name=KEY_TOURNAMENT_HOURS,
            value=json.dumps({"2025-01-15": {"open": "20:00", "close": "23:00"}}),
        )
        actor = await make_staff()
        t = await make_tournament()
        player = await make_user()
        with pytest.raises(ValueError, match="can only start between"):
            await service.create_match(
                tournament_id=t.id,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[player.id],
                actor=actor,
            )

    async def test_already_enrolled_player_not_re_enrolled(self, service, db):
        actor = await make_staff()
        t = await make_tournament()
        player = await make_user()
        await TournamentPlayers.create(tournament=t, user=player)
        await service.create_match(
            tournament_id=t.id,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[player.id],
            actor=actor,
        )
        assert await TournamentPlayers.filter(tournament=t, user=player).count() == 1


# ---------------------------------------------------------------------------
# update_match
# ---------------------------------------------------------------------------


async def _seed_match(service, actor, tournament, player_ids, **kwargs):
    return await service.create_match(
        tournament_id=tournament.id,
        scheduled_date="2025-01-15",
        scheduled_time="14:30",
        player_ids=player_ids,
        actor=actor,
        **kwargs,
    )


class TestUpdateMatch:
    async def test_not_found_raises(self, service, db):
        actor = await make_staff()
        with pytest.raises(ValueError, match="Match 999999 not found"):
            await service.update_match(match_id=999999, comment="x", actor=actor)

    async def test_reschedule_with_player_and_crew_resync(self, service, db, captured_events):
        actor = await make_staff()
        t = await make_tournament()
        alice = await make_user("alice", "Alice")
        bob = await make_user("bob", "Bob")
        carol = await make_user("carol", "Carol")
        commentator = await make_user("comm", "Comm")
        tracker = await make_user("trk", "Trk")

        match = await _seed_match(service, actor, t, [alice.id, bob.id])
        captured_events.clear()

        updated = await service.update_match(
            match_id=match.id,
            scheduled_date="2025-01-16",
            scheduled_time="16:00",
            player_ids=[alice.id, carol.id],  # drop bob, add carol
            commentator_ids=[commentator.id],
            tracker_ids=[tracker.id],
            comment="updated",
            actor=actor,
        )

        assert updated.comment == "updated"
        player_ids = {p.user_id for p in await MatchPlayers.filter(match=match)}
        assert player_ids == {alice.id, carol.id}
        assert not await MatchPlayers.filter(match=match, user=bob).exists()
        assert await Commentator.filter(match=match, user=commentator).exists()
        assert await Tracker.filter(match=match, user=tracker).exists()
        assert await TournamentPlayers.filter(tournament=t, user=carol).exists()

        assert EventType.MATCH_RESCHEDULED in [e.event_type for e in captured_events]

    async def test_players_only_change_emits_update_event(self, service, db, captured_events):
        actor = await make_staff()
        t = await make_tournament()
        alice = await make_user("alice", "Alice")
        bob = await make_user("bob", "Bob")
        carol = await make_user("carol", "Carol")
        match = await _seed_match(service, actor, t, [alice.id, bob.id])
        captured_events.clear()

        await service.update_match(match_id=match.id, player_ids=[alice.id, carol.id], actor=actor)

        types = [e.event_type for e in captured_events]
        assert EventType.MATCH_UPDATED in types
        assert EventType.MATCH_RESCHEDULED not in types

    async def test_clear_timestamps_and_seed(self, service, db):
        actor = await make_staff()
        t = await make_tournament()
        player = await make_user()
        match = await _seed_match(service, actor, t, [player.id])
        # stamp lifecycle fields directly so the clear_* flags have something to clear
        match.seated_at = utc(2025, 1, 15, 18)
        match.started_at = utc(2025, 1, 15, 18, 5)
        match.finished_at = utc(2025, 1, 15, 18, 30)
        match.confirmed_at = utc(2025, 1, 15, 18, 35)
        await match.save()

        await service.update_match(
            match_id=match.id,
            clear_seated=True,
            clear_started=True,
            clear_finished=True,
            clear_confirmed=True,
            clear_seed=True,
            actor=actor,
        )

        refreshed = await Match.get(id=match.id)
        assert refreshed.seated_at is None
        assert refreshed.started_at is None
        assert refreshed.finished_at is None
        assert refreshed.confirmed_at is None
        assert refreshed.generated_seed_id is None

    async def test_crew_removed_when_cleared(self, service, db):
        actor = await make_staff()
        t = await make_tournament()
        player = await make_user()
        commentator = await make_user("comm", "Comm")
        match = await _seed_match(service, actor, t, [player.id], commentator_ids=[commentator.id])
        assert await Commentator.filter(match=match).count() == 1

        await service.update_match(match_id=match.id, commentator_ids=[], actor=actor)
        assert await Commentator.filter(match=match).count() == 0

    async def test_reassign_tournament(self, service, db):
        actor = await make_staff()
        t = await make_tournament(name="Old")
        other = await make_tournament(name="New")
        player = await make_user()
        match = await _seed_match(service, actor, t, [player.id])

        await service.update_match(match_id=match.id, tournament_id=other.id, actor=actor)
        assert (await Match.get(id=match.id)).tournament_id == other.id

    async def test_reassign_tournament_rejected_without_target_admin(self, service, db):
        # A non-staff TA of the SOURCE tournament must not be able to move a
        # match into a tournament they do not administer.
        source = await make_tournament(name="Source")
        target = await make_tournament(name="Target")
        ta = await make_user("srcadmin")
        await source.admins.add(ta)
        player = await make_user()
        match = await _seed_match(service, await make_staff(), source, [player.id])
        with pytest.raises(PermissionError, match="cannot move match into tournament"):
            await service.update_match(match_id=match.id, tournament_id=target.id, actor=ta)
        # The reassignment was rejected before any write.
        assert (await Match.get(id=match.id)).tournament_id == source.id

    async def test_reassign_tournament_allowed_for_admin_of_both(self, service, db):
        source = await make_tournament(name="Source")
        target = await make_tournament(name="Target")
        ta = await make_user("bothadmin")
        await source.admins.add(ta)
        await target.admins.add(ta)
        player = await make_user()
        match = await _seed_match(service, await make_staff(), source, [player.id])
        await service.update_match(match_id=match.id, tournament_id=target.id, actor=ta)
        assert (await Match.get(id=match.id)).tournament_id == target.id

    async def test_sync_players_missing_user_raises(self, service, db):
        actor = await make_staff()
        t = await make_tournament()
        player = await make_user()
        match = await _seed_match(service, actor, t, [player.id])
        with pytest.raises(ValueError, match="User 424242 not found"):
            await service.update_match(match_id=match.id, player_ids=[player.id, 424242], actor=actor)

    async def test_sync_crew_missing_user_raises(self, service, db):
        actor = await make_staff()
        t = await make_tournament()
        player = await make_user()
        match = await _seed_match(service, actor, t, [player.id])
        with pytest.raises(ValueError, match="User 424242 not found"):
            await service.update_match(match_id=match.id, commentator_ids=[424242], actor=actor)


# ---------------------------------------------------------------------------
# submit_match_request
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# set_stream_candidate
# ---------------------------------------------------------------------------


class TestSetStreamCandidate:
    async def test_not_found_raises(self, service, db):
        actor = await make_staff()
        with pytest.raises(ValueError, match="Match 999999 not found"):
            await service.set_stream_candidate(match_id=999999, flag=True, actor=actor)

    async def test_set_true_emits_event_and_persists(self, service, db, captured_events):
        actor = await make_staff()
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        result = await service.set_stream_candidate(match_id=match.id, flag=True, actor=actor)
        assert result.is_stream_candidate is True
        assert (await Match.get(id=match.id)).is_stream_candidate is True
        assert EventType.MATCH_STREAM_CANDIDATE_SET in [e.event_type for e in captured_events]

    async def test_set_false_emits_cleared_event(self, service, db, captured_events):
        actor = await make_staff()
        t = await make_tournament()
        match = await Match.create(
            tournament=t, scheduled_at=utc(2025, 1, 15, 18), is_stream_candidate=True
        )
        await service.set_stream_candidate(match_id=match.id, flag=False, actor=actor)
        assert (await Match.get(id=match.id)).is_stream_candidate is False
        assert EventType.MATCH_STREAM_CANDIDATE_CLEARED in [e.event_type for e in captured_events]

    async def test_set_true_when_already_candidate_skips_notify(self, service, db, captured_events):
        # already a candidate: the `flag and not was_candidate` branch is False, so no
        # stream-candidate notify fan-out happens, but the event still fires.
        actor = await make_staff()
        t = await make_tournament()
        match = await Match.create(
            tournament=t, scheduled_at=utc(2025, 1, 15, 18), is_stream_candidate=True
        )
        await service.set_stream_candidate(match_id=match.id, flag=True, actor=actor)
        assert (await Match.get(id=match.id)).is_stream_candidate is True
        assert EventType.MATCH_STREAM_CANDIDATE_SET in [e.event_type for e in captured_events]


# ---------------------------------------------------------------------------
# assign_stage
# ---------------------------------------------------------------------------


class TestAssignStage:
    async def test_not_found_raises(self, service, db):
        actor = await make_staff()
        with pytest.raises(ValueError, match="Match 999999 not found"):
            await service.assign_stage(match_id=999999, stream_room_id=1, actor=actor)

    async def test_assign_then_clear_persists(self, service, db):
        actor = await make_staff()
        t = await make_tournament()
        room = await StreamRoom.create(name="Stage Z")
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))

        await service.assign_stage(match_id=match.id, stream_room_id=room.id, actor=actor)
        assert (await Match.get(id=match.id)).stream_room_id == room.id

        await service.assign_stage(match_id=match.id, stream_room_id=None, actor=actor)
        assert (await Match.get(id=match.id)).stream_room_id is None


# ---------------------------------------------------------------------------
# assign_stations
# ---------------------------------------------------------------------------


class TestAssignStations:
    async def test_not_found_raises(self, service, db):
        actor = await make_staff()
        with pytest.raises(ValueError, match="Match 999999 not found"):
            await service.assign_stations(match_id=999999, assignments={}, actor=actor)

    async def test_invalid_format_raises(self, service, db):
        await SystemConfiguration.create(name=KEY_STATION_FORMAT, value="numeric")
        actor = await make_staff()
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        player = await make_user()
        mp = await MatchPlayers.create(match=match, user=player)
        with pytest.raises(ValueError, match="does not match the required format"):
            await service.assign_stations(match_id=match.id, assignments={mp.id: "abc"}, actor=actor)

    async def test_valid_assignment_persists(self, service, db, captured_events):
        await SystemConfiguration.create(name=KEY_STATION_FORMAT, value="numeric")
        actor = await make_staff()
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        p1 = await make_user("a", "A")
        p2 = await make_user("b", "B")
        mp1 = await MatchPlayers.create(match=match, user=p1)
        mp2 = await MatchPlayers.create(match=match, user=p2)

        # only mp1 is assigned; mp2 stays untouched
        await service.assign_stations(match_id=match.id, assignments={mp1.id: "5"}, actor=actor)

        assert (await MatchPlayers.get(id=mp1.id)).assigned_station == "5"
        assert (await MatchPlayers.get(id=mp2.id)).assigned_station is None
        assert EventType.MATCH_STATIONS_ASSIGNED in [e.event_type for e in captured_events]


# ---------------------------------------------------------------------------
# delete_match
# ---------------------------------------------------------------------------


class TestDeleteMatch:
    async def test_not_found_raises(self, service, db):
        actor = await make_staff()
        with pytest.raises(ValueError, match="Match 999999 not found"):
            await service.delete_match(match_id=999999, actor=actor)

    async def test_delete_removes_row_and_emits_event(self, service, db, captured_events):
        actor = await make_staff()
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        await service.delete_match(match_id=match.id, actor=actor)
        assert await Match.filter(id=match.id).exists() is False
        assert EventType.MATCH_DELETED in [e.event_type for e in captured_events]


# ---------------------------------------------------------------------------
# record_match_result
# ---------------------------------------------------------------------------


class TestRecordMatchResult:
    async def test_not_found_raises(self, service, db):
        actor = await make_staff()
        with pytest.raises(ValueError, match="Match 999999 not found"):
            await service.record_match_result(match_id=999999, winner_id=1, actor=actor)

    async def test_no_players_raises(self, service, db):
        actor = await make_staff()
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        with pytest.raises(ValueError, match="no players"):
            await service.record_match_result(match_id=match.id, winner_id=1, actor=actor)

    async def test_winner_not_a_player_raises(self, service, db):
        actor = await make_staff()
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        p1 = await make_user("a", "A")
        await MatchPlayers.create(match=match, user=p1)
        with pytest.raises(ValueError, match="not a player"):
            await service.record_match_result(match_id=match.id, winner_id=424242, actor=actor)

    async def test_records_ranks(self, service, db, captured_events):
        actor = await make_staff()
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        p1 = await make_user("a", "A")
        p2 = await make_user("b", "B")
        mp1 = await MatchPlayers.create(match=match, user=p1)
        mp2 = await MatchPlayers.create(match=match, user=p2)

        await service.record_match_result(match_id=match.id, winner_id=mp1.id, actor=actor)

        assert (await MatchPlayers.get(id=mp1.id)).finish_rank == 1
        assert (await MatchPlayers.get(id=mp2.id)).finish_rank == 2
        assert EventType.MATCH_RESULT_RECORDED in [e.event_type for e in captured_events]


# ---------------------------------------------------------------------------
# ensure_players_enrolled & _seed_acknowledgments edge cases
# ---------------------------------------------------------------------------


class TestEnrollmentAndSeedHelpers:
    async def test_ensure_players_enrolled_enrolls_and_skips(self, service, db):
        t = await make_tournament()
        already = await make_user("already")
        fresh = await make_user("fresh")
        await TournamentPlayers.create(tournament=t, user=already)

        await service.ensure_players_enrolled(t.id, [already.id, fresh.id])

        assert await TournamentPlayers.filter(tournament=t, user=already).count() == 1
        assert await TournamentPlayers.filter(tournament=t, user=fresh).exists()

    async def test_ensure_players_enrolled_missing_user_raises(self, service, db):
        t = await make_tournament()
        with pytest.raises(ValueError, match="User 424242 not found"):
            await service.ensure_players_enrolled(t.id, [424242])

    async def test_seed_acknowledgments_skips_missing_user(self, service, db):
        t = await make_tournament()
        match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 18))
        # id 424242 has no User row -> the loop `continue`s and no ack is created
        await service._seed_acknowledgments(match, [424242], None)
        assert await MatchAcknowledgment.filter(match=match).count() == 0
