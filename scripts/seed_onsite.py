"""Dev seed for the on-site (non-racetime) tournament.

Split out of ``seed_dev.py`` for length, the way the volunteer and bracket
fixtures already are.

The main dev tournament is racetime-enabled, which hides every proctor control
— check-in, stations, start, finish. Without an on-site tournament the Proctor
Station board has nothing to demonstrate: no ordering to show, no summary counts,
and no recorded result to hand to an admin's review queue. So this seeds one
match per step of the proctor's workflow, plus the two states the admin's half
of the loop needs.
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
    return onsite
