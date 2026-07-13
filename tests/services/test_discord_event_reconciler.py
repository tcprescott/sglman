"""Tests for the Discord Events reconciler (PR 8).

Exercises idempotent reconciliation against the mock Discord transport: create a
mirrored event for a scheduled match, no-op when unchanged, update on a schedule
change, cancel when the source match finishes/vanishes, and the no-linked-guild
guard. Shared-guild sibling safety has its own isolation test.
"""

from datetime import datetime, timedelta, timezone

from application.services.discord_event_reconciler_service import DiscordEventReconcilerService
from application.services.discord_service import MockDiscordService
from application.utils import mock_discord_data
from models import DiscordEventSource, DiscordScheduledEvent, Match, MatchPlayers, Tenant, Tournament, User

GUILD = 1000000000000000001


def _reconciler() -> DiscordEventReconcilerService:
    mock_discord_data.reset_scheduled_events()
    svc = DiscordEventReconcilerService()
    svc.discord = MockDiscordService()
    return svc


async def _setup(db, *, enabled=True):
    tenant = await Tenant.get(id=1)
    tenant.discord_guild_id = GUILD
    await tenant.save()
    actor = await User.create(discord_id=1, username='sys', is_system=True)
    tourn = await Tournament.create(name='T', discord_events_enabled=enabled)
    return tenant, actor, tourn


async def _match(tourn, *, when, title='R1', players=('Alice', 'Bob')):
    match = await Match.create(tournament=tourn, scheduled_at=when, title=title)
    for name in players:
        user = await User.create(discord_id=None, username=name.lower(), display_name=name,
                                 is_placeholder=True, speedgaming_id=f'sg_{name}')
        await MatchPlayers.create(match=match, user=user)
    return match


async def test_create_mirrors_scheduled_match(db):
    tenant, actor, tourn = await _setup(db)
    when = datetime.now(timezone.utc) + timedelta(days=1)
    match = await _match(tourn, when=when)

    result = await _reconciler().reconcile_tenant(tenant, actor=actor)
    assert (result.created, result.updated, result.cancelled) == (1, 0, 0)

    row = await DiscordScheduledEvent.filter(source_id=match.id).first()
    assert row is not None
    assert row.source_type == DiscordEventSource.MATCH
    assert row.guild_id == GUILD
    assert len(mock_discord_data.scheduled_events_for(GUILD)) == 1


async def test_unchanged_is_noop(db):
    tenant, actor, tourn = await _setup(db)
    when = datetime.now(timezone.utc) + timedelta(days=1)
    await _match(tourn, when=when)
    reconciler = _reconciler()

    await reconciler.reconcile_tenant(tenant, actor=actor)
    result = await reconciler.reconcile_tenant(tenant, actor=actor)
    assert (result.created, result.updated, result.unchanged) == (0, 0, 1)
    assert len(mock_discord_data.scheduled_events_for(GUILD)) == 1


async def test_reschedule_updates_event(db):
    tenant, actor, tourn = await _setup(db)
    when = datetime.now(timezone.utc) + timedelta(days=1)
    match = await _match(tourn, when=when)
    reconciler = _reconciler()

    await reconciler.reconcile_tenant(tenant, actor=actor)
    match.scheduled_at = when + timedelta(hours=3)
    await match.save()

    result = await reconciler.reconcile_tenant(tenant, actor=actor)
    assert (result.created, result.updated) == (0, 1)
    assert len(mock_discord_data.scheduled_events_for(GUILD)) == 1


async def test_finished_match_cancels_event(db):
    tenant, actor, tourn = await _setup(db)
    when = datetime.now(timezone.utc) + timedelta(days=1)
    match = await _match(tourn, when=when)
    reconciler = _reconciler()

    await reconciler.reconcile_tenant(tenant, actor=actor)
    match.finished_at = datetime.now(timezone.utc)
    await match.save()

    result = await reconciler.reconcile_tenant(tenant, actor=actor)
    assert result.cancelled == 1
    assert await DiscordScheduledEvent.filter(source_id=match.id).count() == 0
    assert mock_discord_data.scheduled_events_for(GUILD) == []


async def test_no_linked_guild_is_noop(db):
    tenant, actor, tourn = await _setup(db)
    tenant.discord_guild_id = None
    await tenant.save()
    await _match(tourn, when=datetime.now(timezone.utc) + timedelta(days=1))

    result = await _reconciler().reconcile_tenant(tenant, actor=actor)
    assert (result.created, result.updated, result.cancelled) == (0, 0, 0)
    assert await DiscordScheduledEvent.all().count() == 0


async def test_opt_out_tournament_not_mirrored(db):
    tenant, actor, tourn = await _setup(db, enabled=False)
    await _match(tourn, when=datetime.now(timezone.utc) + timedelta(days=1))

    result = await _reconciler().reconcile_tenant(tenant, actor=actor)
    assert result.created == 0
    assert await DiscordScheduledEvent.all().count() == 0


async def test_out_of_window_match_not_mirrored(db):
    tenant, actor, tourn = await _setup(db)
    # Far in the future, beyond the lookahead window.
    await _match(tourn, when=datetime.now(timezone.utc) + timedelta(days=90))

    result = await _reconciler().reconcile_tenant(tenant, actor=actor)
    assert result.created == 0


async def test_event_deleted_out_of_band_is_recreated(db):
    """A mirrored event gone from Discord (edit → not found) is re-created, not errored."""
    tenant, actor, tourn = await _setup(db)
    when = datetime.now(timezone.utc) + timedelta(days=1)
    match = await _match(tourn, when=when)
    reconciler = _reconciler()

    await reconciler.reconcile_tenant(tenant, actor=actor)
    # Simulate an out-of-band deletion: the Discord event vanishes but the link
    # row survives with a now-stale hash (force the edit branch next pass).
    mock_discord_data.reset_scheduled_events()
    link = await DiscordScheduledEvent.filter(source_id=match.id).first()
    await DiscordScheduledEvent.filter(id=link.id).update(content_hash='stale')

    result = await reconciler.reconcile_tenant(tenant, actor=actor)
    assert result.errors == 0
    assert result.created == 1  # healed via re-create
    assert await DiscordScheduledEvent.filter(source_id=match.id).count() == 1
    assert len(mock_discord_data.scheduled_events_for(GUILD)) == 1


async def test_title_template_rendered(db):
    tenant, actor, tourn = await _setup(db)
    tourn.discord_event_title_template = '{tournament} — {players}'
    await tourn.save()
    when = datetime.now(timezone.utc) + timedelta(days=1)
    match = await _match(tourn, when=when, players=('Alice', 'Bob'))

    await _reconciler().reconcile_tenant(tenant, actor=actor)
    row = await DiscordScheduledEvent.filter(source_id=match.id).first()
    assert row.title == 'T — Alice, Bob'
