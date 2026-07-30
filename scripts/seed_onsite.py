"""Dev seed for the second on-site (non-racetime) tournament — "Wizzrobe Cup".

Split out of ``seed_dev.py`` for length, the way the volunteer and bracket
fixtures already are.

A venue event distinct from the general-purpose "Wizzrobe Dev Tournament": it
carries its own per-tournament "tournament days" override, and it walks the
proctor's board through the workflow in order — one match per step, plus the two
states the admin's half of the loop needs (a recorded result awaiting review, and
a finished match with no winner recorded). Deliberately never racetime-enabled:
a racetime bot hides check-in, stations, start and finish, which is exactly what
this fixture exists to exercise.
"""

from datetime import date, datetime, timedelta

from models import (
    Match,
    MatchPlayers,
    StreamRoom,
    Tenant,
    Tournament,
    TournamentPlayers,
    User,
)
from scripts.seed_support import backfill

#: What a venue event fills in besides its name. The durations are the pair the
#: schedule's suggestion engine and the reports' expected-average column read
#: (both fall back to a hard-coded 90 minutes when NULL), and a Cup match is
#: shorter than a bracket race — so the two on-site fixtures no longer look
#: identical to anything that reasons about match length.
_ONSITE_META = {
    "tournament_format": "Swiss rounds into a single-elimination top 8",
    "rules_url": "https://example.invalid/wizzrobe/cup/rules",
    "average_match_duration": 75,
    "max_match_duration": 120,
}


async def seed_onsite_for_tenant(
    tenant: Tenant,
    staff: User,
    players: list[User],
    today: date,
    now: datetime,
    stage1: StreamRoom,
    stage3: StreamRoom,
) -> Tournament:
    """Seed the on-site tournament and its matches. Idempotent."""
    onsite, _ = await Tournament.get_or_create(
        name="Wizzrobe Cup", tenant=tenant,
        defaults={
            "description": "On-site fixture — no racetime.gg integration.",
            "seed_generator": "alttpr",
            "is_active": True,
            "players_per_match": 2,
            "staff_administered": False,
            **_ONSITE_META,
            # Per-tournament "tournament days" override: its own event window
            # and per-day hours, distinct from the tenant default.
            "event_start_date": today,
            "event_end_date": today + timedelta(days=3),
            "tournament_hours": {
                today.isoformat(): {"open": "09:00", "close": "23:59"},
                (today + timedelta(days=1)).isoformat(): {"open": "12:00", "close": "23:59"},
            },
        },
    )
    await backfill(onsite, **_ONSITE_META)
    await onsite.admins.add(staff)
    for p in (players[0], players[1]):
        await TournamentPlayers.get_or_create(tournament=onsite, user=p, tenant=tenant)

    async def make_match(
        title: str,
        offset_hours: float,
        *,
        seated: bool = False,
        started: bool = False,
        finished: bool = False,
        winner_rank: bool = True,
        stations: tuple[str, str] | None = None,
        room: StreamRoom | None = None,
    ) -> Match:
        scheduled_at = now + timedelta(hours=offset_hours)
        match, created = await Match.get_or_create(
            title=title, tournament=onsite, tenant=tenant,
            defaults={
                "scheduled_at": scheduled_at,
                "stream_room": room,
                "is_stream_candidate": room is not None,
            },
        )
        if not created:
            return match
        if seated or started or finished:
            match.seated_at = scheduled_at - timedelta(minutes=10)
        if started or finished:
            match.started_at = scheduled_at
        if finished:
            match.finished_at = scheduled_at + timedelta(minutes=45)
        await match.save()
        for rank, player in enumerate([players[0], players[1]], 1):
            await MatchPlayers.get_or_create(
                match=match, user=player, tenant=tenant,
                defaults={
                    "finish_rank": rank if (finished and winner_rank) else None,
                    "assigned_station": stations[rank - 1] if stations else None,
                },
            )
        return match

    # One row per step of the proctor's workflow.
    await make_match("On-Site Scheduled", 2)
    await make_match("On-Site Overdue", -0.5)
    await make_match("On-Site Checked In", 0.25, seated=True, stations=('3', '7'), room=stage1)
    await make_match("On-Site In Progress", -1, seated=True, started=True, stations=('4', '8'), room=stage3)
    # Recorded but not yet confirmed — the admin's review queue.
    await make_match(
        "On-Site Awaiting Review", -2,
        seated=True, started=True, finished=True, stations=('1', '5'), room=stage1,
    )
    # Finished with *no* winner recorded: confirming this must be refused.
    await make_match(
        "On-Site Result Missing", -3,
        seated=True, started=True, finished=True, winner_rank=False, stations=('2', '6'),
    )

    await _seed_archived_season(tenant, staff, players, now)
    return onsite


async def _seed_archived_season(
    tenant: Tenant, staff: User, players: list[User], now: datetime,
) -> Tournament:
    """Last season's event, closed out: ``is_active=False`` with its results kept.

    A community does not delete a finished season — it archives it and starts the
    next one, so at any moment a real database holds both. Every other seeded
    tournament is active, which left the inactive half of every
    ``is_active=True`` filter (the profile page's tournament lists, the
    notification-preference list, the admin selectors) with nothing to exclude,
    and the tournament table's Active column uniform.
    """
    archived, _ = await Tournament.get_or_create(
        name="Wizzrobe Cup — Last Season", tenant=tenant,
        defaults={
            "description": "Closed out. Kept for its results and its triforce texts.",
            "seed_generator": "alttpr",
            "is_active": False,
            "players_per_match": 2,
            "staff_administered": False,
            "tournament_format": "Single elimination, best of 3",
            "average_match_duration": 80,
            "max_match_duration": 130,
        },
    )
    await archived.admins.add(staff)
    for player in players[:2]:
        await TournamentPlayers.get_or_create(
            tournament=archived, user=player, tenant=tenant,
        )
    final, created = await Match.get_or_create(
        title="Last Season — Grand Final", tournament=archived, tenant=tenant,
        defaults={"scheduled_at": now - timedelta(days=60), "is_stream_candidate": True},
    )
    if created:
        final.seated_at = final.scheduled_at - timedelta(minutes=10)
        final.started_at = final.scheduled_at
        final.finished_at = final.scheduled_at + timedelta(minutes=95)
        final.confirmed_at = final.finished_at + timedelta(minutes=5)
        await final.save()
        for rank, player in enumerate(players[:2], 1):
            await MatchPlayers.get_or_create(
                match=final, user=player, tenant=tenant, defaults={"finish_rank": rank},
            )
    return archived
