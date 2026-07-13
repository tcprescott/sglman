"""Racetime room lifecycle tests (PR 6).

Mock-driven, end to end: room create/open (idempotent), in-progress, finish with
result capture (including forfeit / no-show / one-finisher terminal states and
unlinked-handle reconcile), cancel, the transport→service lifecycle adapter, the
manual-create permission gate, and the auto-open worker's eligibility rules.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from application.services import race_room_worker
from application.services.race_room_service import RaceRoomLifecycle, RaceRoomService
from models import (
    AuditLog,
    Match,
    MatchPlayers,
    RaceRoomStatus,
    RacetimeBot,
    RacetimeRoom,
    Role,
    Tournament,
    User,
    UserRole,
)
from racetimebot.transport import EntrantStatus, RaceEntrant, RaceRoomEvent


async def _bot(category: str = 'alttpr') -> RacetimeBot:
    return await RacetimeBot.create(
        category=category, client_id='c', client_secret='s', name='A',
    )


async def _tournament(bot, *, auto_open=False, lead=30, seed=None) -> Tournament:
    return await Tournament.create(
        name='T', racetime_bot_id=bot.id,
        racetime_auto_create_rooms=auto_open, room_open_minutes_before=lead,
        seed_generator=seed,
    )


_next_discord_id = [500000]


async def _user(name, rtid=None) -> User:
    _next_discord_id[0] += 1
    return await User.create(
        username=name, discord_id=_next_discord_id[0], racetime_user_id=rtid,
    )


async def _match(tournament, *, scheduled_at=None) -> Match:
    return await Match.create(tournament_id=tournament.id, scheduled_at=scheduled_at)


async def _add_player(match, user) -> MatchPlayers:
    return await MatchPlayers.create(match_id=match.id, user_id=user.id)


async def _match_with_players(tournament, users, *, scheduled_at=None) -> Match:
    match = await _match(tournament, scheduled_at=scheduled_at)
    for u in users:
        await _add_player(match, u)
    return await Match.get(id=match.id).prefetch_related('tournament', 'players', 'players__user')


# ---- create / open -------------------------------------------------------

async def test_create_room_is_idempotent(db):
    bot = await _bot()
    tourn = await _tournament(bot)
    match = await _match_with_players(tourn, [await _user('a', 'rt-a')])
    svc = RaceRoomService()

    room1 = await svc.create_room_for_match(match)
    room2 = await svc.create_room_for_match(match)

    assert room1.id == room2.id
    assert room1.status == RaceRoomStatus.OPEN
    assert room1.category == 'alttpr'
    assert room1.slug == f'alttpr/match-{match.id}'
    assert await RacetimeRoom.filter(match_id=match.id).count() == 1


async def test_create_room_requires_bot(db):
    tourn = await Tournament.create(name='NoBot')
    match = await _match_with_players(tourn, [await _user('a', 'rt-a')])
    with pytest.raises(ValueError):
        await RaceRoomService().create_room_for_match(match)


async def test_manual_create_requires_sync_permission(db):
    bot = await _bot()
    tourn = await _tournament(bot)
    match = await _match_with_players(tourn, [await _user('a', 'rt-a')])
    plain = await _user('plain')

    with pytest.raises(PermissionError):
        await RaceRoomService().manual_create_room(plain, match.id)


async def test_manual_create_allows_sync_admin(db):
    bot = await _bot()
    tourn = await _tournament(bot)
    match = await _match_with_players(tourn, [await _user('a', 'rt-a')])
    admin = await _user('admin')
    await UserRole.create(user_id=admin.id, role=Role.SYNC_ADMIN)

    room = await RaceRoomService().manual_create_room(admin, match.id)
    assert room.match_id == match.id


# ---- transitions ---------------------------------------------------------

async def test_mark_in_progress_starts_match(db):
    bot = await _bot()
    tourn = await _tournament(bot)
    match = await _match_with_players(tourn, [await _user('a', 'rt-a')])
    svc = RaceRoomService()
    room = await svc.create_room_for_match(match)

    await svc.mark_in_progress(room)

    room = await RacetimeRoom.get(id=room.id)
    match = await Match.get(id=match.id)
    assert room.status == RaceRoomStatus.IN_PROGRESS
    assert match.started_at is not None


async def test_cancel_room(db):
    bot = await _bot()
    tourn = await _tournament(bot)
    match = await _match_with_players(tourn, [await _user('a', 'rt-a')])
    svc = RaceRoomService()
    room = await svc.create_room_for_match(match)

    await svc.cancel_room(room, reason='called off')

    assert (await RacetimeRoom.get(id=room.id)).status == RaceRoomStatus.CANCELLED


# ---- result capture ------------------------------------------------------

async def test_record_finish_captures_results(db):
    bot = await _bot()
    tourn = await _tournament(bot)
    ua = await _user('a', 'rt-a')
    ub = await _user('b', 'rt-b')
    match = await _match_with_players(tourn, [ua, ub])
    svc = RaceRoomService()
    room = await svc.create_room_for_match(match)

    entrants = [
        RaceEntrant(user_id='rt-a', display_name='a', status=EntrantStatus.DONE, finish_time=3600),
        RaceEntrant(user_id='rt-b', display_name='b', status=EntrantStatus.DONE, finish_time=3720),
    ]
    await svc.record_finish(room, entrants)

    assert (await RacetimeRoom.get(id=room.id)).status == RaceRoomStatus.FINISHED
    assert (await Match.get(id=match.id)).finished_at is not None
    pa = await MatchPlayers.get(match_id=match.id, user_id=ua.id)
    pb = await MatchPlayers.get(match_id=match.id, user_id=ub.id)
    assert (pa.finish_rank, pa.finish_time) == (1, 3600)
    assert (pb.finish_rank, pb.finish_time) == (2, 3720)


async def test_record_finish_forfeit_and_one_finisher(db):
    bot = await _bot()
    tourn = await _tournament(bot)
    ua = await _user('a', 'rt-a')
    ub = await _user('b', 'rt-b')
    match = await _match_with_players(tourn, [ua, ub])
    svc = RaceRoomService()
    room = await svc.create_room_for_match(match)

    entrants = [
        RaceEntrant(user_id='rt-a', display_name='a', status=EntrantStatus.DONE, finish_time=3600),
        RaceEntrant(user_id='rt-b', display_name='b', status=EntrantStatus.DID_NOT_FINISH),
    ]
    await svc.record_finish(room, entrants)

    pa = await MatchPlayers.get(match_id=match.id, user_id=ua.id)
    pb = await MatchPlayers.get(match_id=match.id, user_id=ub.id)
    assert pa.finish_rank == 1
    assert pb.finish_rank is None and pb.finish_time is None  # forfeit


async def test_record_finish_notes_unmatched_handles(db):
    bot = await _bot()
    tourn = await _tournament(bot)
    ua = await _user('a', 'rt-a')
    match = await _match_with_players(tourn, [ua])
    svc = RaceRoomService()
    room = await svc.create_room_for_match(match)

    entrants = [
        RaceEntrant(user_id='rt-a', display_name='a', status=EntrantStatus.DONE, finish_time=3600),
        RaceEntrant(user_id='rt-stranger', display_name='Stranger', status=EntrantStatus.DONE, finish_time=3500),
    ]
    await svc.record_finish(room, entrants)

    log = await AuditLog.filter(action='race_room.result_recorded').order_by('-id').first()
    assert log is not None
    details = log.details if isinstance(log.details, dict) else json.loads(log.details)
    assert 'Stranger' in details.get('unmatched_handles', [])


# ---- lifecycle adapter ---------------------------------------------------

async def test_lifecycle_adapter_routes_events(db):
    bot = await _bot()
    tourn = await _tournament(bot)
    match = await _match_with_players(tourn, [await _user('a', 'rt-a')])
    room = await RaceRoomService().create_room_for_match(match)
    adapter = RaceRoomLifecycle()

    await adapter.handle_event(
        room, RaceRoomEvent(slug=room.slug, category='alttpr', status=RaceRoomStatus.IN_PROGRESS),
    )
    assert (await RacetimeRoom.get(id=room.id)).status == RaceRoomStatus.IN_PROGRESS

    await adapter.handle_event(
        await RacetimeRoom.get(id=room.id),
        RaceRoomEvent(slug=room.slug, category='alttpr', status=RaceRoomStatus.CANCELLED),
    )
    assert (await RacetimeRoom.get(id=room.id)).status == RaceRoomStatus.CANCELLED


# ---- auto-open worker ----------------------------------------------------

async def test_auto_open_creates_room_for_eligible_match(db):
    bot = await _bot()
    tourn = await _tournament(bot, auto_open=True, lead=30)
    soon = datetime.now(timezone.utc) + timedelta(minutes=10)
    await _match_with_players(tourn, [await _user('a', 'rt-a'), await _user('b', 'rt-b')], scheduled_at=soon)

    await race_room_worker._tick()

    assert await RacetimeRoom.all().count() == 1


async def test_auto_open_skips_unlinked_entrant(db):
    bot = await _bot()
    tourn = await _tournament(bot, auto_open=True, lead=30)
    soon = datetime.now(timezone.utc) + timedelta(minutes=10)
    await _match_with_players(
        tourn, [await _user('a', 'rt-a'), await _user('b')],  # b has no racetime link
        scheduled_at=soon,
    )

    await race_room_worker._tick()

    assert await RacetimeRoom.all().count() == 0


async def test_auto_open_skips_outside_lead_window(db):
    bot = await _bot()
    tourn = await _tournament(bot, auto_open=True, lead=30)
    later = datetime.now(timezone.utc) + timedelta(hours=3)  # beyond the 30-min lead
    await _match_with_players(tourn, [await _user('a', 'rt-a')], scheduled_at=later)

    await race_room_worker._tick()

    assert await RacetimeRoom.all().count() == 0


async def test_auto_open_is_idempotent(db):
    bot = await _bot()
    tourn = await _tournament(bot, auto_open=True, lead=30)
    soon = datetime.now(timezone.utc) + timedelta(minutes=10)
    await _match_with_players(tourn, [await _user('a', 'rt-a')], scheduled_at=soon)

    await race_room_worker._tick()
    await race_room_worker._tick()

    assert await RacetimeRoom.all().count() == 1
