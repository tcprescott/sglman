"""Tests for the SpeedGaming ETL (PR 7).

Exercises the transform (placeholder resolution + upgrade-in-place), the load
(materialize/refresh Match + players), the lifecycle guards (skip finished /
manual / room-linked; auto-finish >4h past), and the soft-detach of an upstream
cancellation — all against the in-memory schema with the mock SG client.
"""

from datetime import datetime, timedelta, timezone

import pytest

from application.repositories import MatchRepository, UserRepository
from application.services.speedgaming_etl_service import SpeedGamingETLService
from application.utils.clients.speedgaming_client import MockSpeedGamingClient
from models import (
    Match,
    MatchAcknowledgment,
    MatchPlayers,
    RacetimeRoom,
    SpeedGamingEpisode,
    SpeedGamingEventLink,
    SyncStatus,
    Tournament,
    User,
)


def _episode(sg_id, when, players, title='R1'):
    return {
        'id': sg_id,
        'when': when,
        'title': title,
        'match1': {'players': players},
    }


async def _setup(db):
    system = await UserRepository.get_or_create_system_user()
    tourn = await Tournament.create(name='T')
    link = await SpeedGamingEventLink.create(tournament=tourn, event_slug='ev')
    etl = SpeedGamingETLService(client=MockSpeedGamingClient([]))
    return system, tourn, link, etl


async def test_import_creates_match_and_resolves_players(db):
    system, tourn, link, etl = await _setup(db)
    real = await User.create(discord_id=111, username='playerone')
    raw = _episode(42, '2026-07-20T18:00:00+00:00', [
        {'id': 1, 'displayName': 'PlayerOne', 'discordId': '111', 'discordTag': 'playerone'},
        {'id': 2, 'displayName': 'SG Only', 'discordId': None, 'discordTag': 'sgonly'},
    ])

    outcome = await etl.import_episode(link, raw, actor=system)
    assert outcome == 'imported'

    match = await Match.filter(speedgaming_episode__sg_episode_id='42').first()
    assert match is not None
    assert match.tournament_id == tourn.id
    assert match.scheduled_at == datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)

    players = await MatchPlayers.filter(match=match).prefetch_related('user')
    assert len(players) == 2
    by_ph = {p.user.is_placeholder: p.user for p in players}
    assert by_ph[False].id == real.id
    placeholder = by_ph[True]
    assert placeholder.discord_id is None
    assert placeholder.speedgaming_id == '2'
    assert placeholder.username == 'sg_2'


async def test_import_is_idempotent_unchanged(db):
    system, tourn, link, etl = await _setup(db)
    raw = _episode(50, '2026-07-20T18:00:00+00:00', [
        {'id': 9, 'displayName': 'A', 'discordId': None, 'discordTag': 'a'},
    ])
    assert await etl.import_episode(link, raw, actor=system) == 'imported'
    # Same payload again → recognized as unchanged, not re-materialized.
    assert await etl.import_episode(link, raw, actor=system) == 'unchanged'
    assert await Match.filter(speedgaming_episode__sg_episode_id='50').count() == 1


async def test_placeholder_upgraded_in_place_when_discord_id_appears(db):
    system, tourn, link, etl = await _setup(db)
    # First sync: no discord id → placeholder created keyed on sg id 7.
    raw1 = _episode(60, '2026-07-20T18:00:00+00:00', [
        {'id': 7, 'displayName': 'Later', 'discordId': None, 'discordTag': 'later'},
    ])
    await etl.import_episode(link, raw1, actor=system)
    placeholder = await UserRepository.get_placeholder_by_speedgaming_id('7')
    assert placeholder is not None and placeholder.is_placeholder

    # Second sync: same sg id now carries a discord id → upgraded in place.
    raw2 = _episode(60, '2026-07-20T19:00:00+00:00', [
        {'id': 7, 'displayName': 'Later', 'discordId': '777', 'discordTag': 'later'},
    ])
    await etl.import_episode(link, raw2, actor=system)
    upgraded = await User.get(id=placeholder.id)
    assert upgraded.is_placeholder is False
    assert upgraded.discord_id == 777
    # No second user row was forked for the same person.
    assert await User.filter(speedgaming_id='7').count() == 1


async def test_resolves_by_discord_username(db):
    system, tourn, link, etl = await _setup(db)
    existing = await User.create(discord_id=222, username='byname')
    raw = _episode(70, '2026-07-20T18:00:00+00:00', [
        {'id': 8, 'displayName': 'By Name', 'discordId': None, 'discordTag': 'byname'},
    ])
    await etl.import_episode(link, raw, actor=system)
    match = await Match.filter(speedgaming_episode__sg_episode_id='70').first()
    players = await MatchPlayers.filter(match=match).prefetch_related('user')
    assert [p.user_id for p in players] == [existing.id]


@pytest.mark.parametrize('field', ['finished_at', 'seated_at', 'started_at', 'confirmed_at'])
async def test_resync_skips_manually_progressed_match(db, field):
    system, tourn, link, etl = await _setup(db)
    raw = _episode(80, '2026-07-20T18:00:00+00:00', [
        {'id': 3, 'discordId': None, 'discordTag': 'p'},
    ])
    await etl.import_episode(link, raw, actor=system)
    match = await Match.filter(speedgaming_episode__sg_episode_id='80').first()
    await MatchRepository.update(match, **{field: datetime.now(timezone.utc)})

    changed = _episode(80, '2026-07-22T18:00:00+00:00', [
        {'id': 3, 'discordId': None, 'discordTag': 'p'},
    ])
    assert await etl.import_episode(link, changed, actor=system) == 'skipped'

    refreshed = await Match.get(id=match.id)
    assert refreshed.scheduled_at == datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)
    episode = await SpeedGamingEpisode.get(sg_episode_id='80')
    assert episode.sync_status == SyncStatus.SKIPPED


async def test_resync_skips_room_linked_match(db):
    system, tourn, link, etl = await _setup(db)
    raw = _episode(90, '2026-07-20T18:00:00+00:00', [
        {'id': 4, 'discordId': None, 'discordTag': 'q'},
    ])
    await etl.import_episode(link, raw, actor=system)
    match = await Match.filter(speedgaming_episode__sg_episode_id='90').first()
    await RacetimeRoom.create(slug='alttpr/room-x', category='alttpr', match=match)

    changed = _episode(90, '2026-07-25T18:00:00+00:00', [
        {'id': 4, 'discordId': None, 'discordTag': 'q'},
    ])
    assert await etl.import_episode(link, changed, actor=system) == 'skipped'


async def test_sync_event_link_cancels_vanished_episode(db):
    system, tourn, link, etl = await _setup(db)
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    two = [
        _episode(101, '2026-07-20T18:00:00+00:00', [{'id': 11, 'discordTag': 'a'}]),
        _episode(102, '2026-07-21T18:00:00+00:00', [{'id': 12, 'discordTag': 'b'}]),
    ]
    etl.client = MockSpeedGamingClient(two)
    result = await etl.sync_event_link(link, actor=system, now=now)
    assert result.imported == 2

    # Next poll: 102 vanished upstream → soft-detached (Match survives).
    etl.client = MockSpeedGamingClient([two[0]])
    result2 = await etl.sync_event_link(link, actor=system, now=now + timedelta(minutes=30))
    assert result2.cancelled == 1
    ep = await SpeedGamingEpisode.get(sg_episode_id='102')
    assert ep.sync_status == SyncStatus.CANCELLED
    assert await Match.filter(speedgaming_episode__sg_episode_id='102').count() == 1


async def test_auto_finishes_stale_match(db):
    system, tourn, link, etl = await _setup(db)
    now = datetime(2026, 7, 20, 23, 0, tzinfo=timezone.utc)
    # Episode scheduled >4h before ``now`` and never progressed.
    stale = [_episode(110, '2026-07-20T18:00:00+00:00', [{'id': 13, 'discordTag': 'c'}])]
    etl.client = MockSpeedGamingClient(stale)
    result = await etl.sync_event_link(link, actor=system, now=now)
    assert result.auto_finished == 1
    match = await Match.filter(speedgaming_episode__sg_episode_id='110').first()
    assert match.finished_at is not None


# --- Acknowledgment rows on a sourced match --------------------------------
#
# The ETL used to sync players and no acknowledgment rows, which made a synced
# match's players invisible to the entire acknowledgment surface: no confirmed
# or pending icon in the board's players cell, no Acknowledge button for the
# player (it is gated on the row existing), and an admin dialog that reported
# "No players assigned." for a match with two of them.

async def test_import_gives_every_synced_player_an_acknowledgment_row(db):
    system, _tourn, link, etl = await _setup(db)
    await User.create(discord_id=111, username='playerone')
    raw = _episode(60, '2026-07-20T18:00:00+00:00', [
        {'id': 1, 'displayName': 'PlayerOne', 'discordId': '111', 'discordTag': 'playerone'},
        {'id': 2, 'displayName': 'SG Only', 'discordId': None, 'discordTag': 'sgonly'},
    ])

    await etl.import_episode(link, raw, actor=system)

    match = await Match.filter(speedgaming_episode__sg_episode_id='60').first()
    acks = await MatchAcknowledgment.filter(match=match)
    assert len(acks) == 2
    # Created un-answered: the sync assigns people, it does not speak for them.
    assert all(a.acknowledged_at is None for a in acks)
    assert all(a.auto_acknowledged is False for a in acks)


async def test_a_resync_does_not_discard_an_answer_a_player_already_gave(db):
    """The reason this reconciles rather than re-seeds.

    ``seed_acknowledgments`` deletes every row first, so calling it from a poll
    that runs every few minutes would erase each confirmation moments after it
    arrived.
    """
    system, _tourn, link, etl = await _setup(db)
    await User.create(discord_id=111, username='playerone')
    raw = _episode(61, '2026-07-20T18:00:00+00:00', [
        {'id': 1, 'displayName': 'PlayerOne', 'discordId': '111', 'discordTag': 'playerone'},
    ])
    await etl.import_episode(link, raw, actor=system)
    match = await Match.filter(speedgaming_episode__sg_episode_id='61').first()

    ack = await MatchAcknowledgment.filter(match=match).first()
    answered = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    ack.acknowledged_at = answered
    await ack.save()

    await etl.import_episode(link, raw, actor=system)

    rows = await MatchAcknowledgment.filter(match=match)
    assert len(rows) == 1
    assert rows[0].acknowledged_at == answered


async def test_a_player_dropped_upstream_loses_their_acknowledgment_row(db):
    """The roster is a full replace, so a stale row would outlive its player."""
    system, _tourn, link, etl = await _setup(db)
    await User.create(discord_id=111, username='playerone')
    two = _episode(62, '2026-07-20T18:00:00+00:00', [
        {'id': 1, 'displayName': 'PlayerOne', 'discordId': '111', 'discordTag': 'playerone'},
        {'id': 2, 'displayName': 'SG Only', 'discordId': None, 'discordTag': 'sgonly'},
    ])
    await etl.import_episode(link, two, actor=system)
    match = await Match.filter(speedgaming_episode__sg_episode_id='62').first()
    assert await MatchAcknowledgment.filter(match=match).count() == 2

    one = _episode(62, '2026-07-20T18:00:00+00:00', [
        {'id': 1, 'displayName': 'PlayerOne', 'discordId': '111', 'discordTag': 'playerone'},
    ])
    await etl.import_episode(link, one, actor=system)

    assert await MatchPlayers.filter(match=match).count() == 1
    assert await MatchAcknowledgment.filter(match=match).count() == 1
