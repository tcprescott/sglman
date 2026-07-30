"""Dev-seed fixtures for a staff-run race night: heats of **four** racers.

Split out of ``seed_dev.py`` for length, the way the volunteer, equipment and
on-site fixtures already are: one module per domain, called from inside the
caller's ``tenant_scope``, idempotent and tenant-stamped like every other seeded
row.

Three things about a real community race night have no fixture anywhere else in
the seed, and each one is a code path a developer cannot reach in dev without
hand-building the rows:

* **More than two players in a match.** Every other seeded tournament is 1v1, so
  ``players_per_match`` has only ever been 2 in dev — while the roster editor,
  the "A vs B" labels, the DM copy and ``ReportsService``'s player-count maths
  all read it. A four-racer heat is where a two-name assumption shows.
* **A staff-administered tournament.** ``UserService.get_active_tournaments_categorized``
  splits the profile page's tournaments into staff-run and player-run lists, and
  with every fixture ``staff_administered=False`` the staff list is empty in dev.
  Race nights are exactly the case the flag is for: staff post the heats,
  players do not request them (``allow_player_match_requests=False``).
* **A match with no title, and a match with no roster.** Both are ordinary in
  production — a heat is labelled by who is in it, and a slot is posted before
  the entrants are known — and both have fallbacks in the code
  (``match.title or players_str``, the reconciler's ``'TBD'``) that nothing in
  dev exercises.
"""

from datetime import datetime, timedelta

from models import Match, MatchPlayers, Tenant, Tournament, TournamentPlayers, User
from scripts.seed_support import backfill

RACE_NIGHT_NAME = "Wizzrobe Race Night"

#: Finish times (seconds) for the three racers who finished heat 1, in placing
#: order. The fourth racer forfeited, which is why the list is one short of the
#: roster: a forfeit keeps its seat but records neither a rank nor a time.
_HEAT_FINISH_TIMES = (5325, 5480, 5902)


async def seed_community_race_for_tenant(
    tenant: Tenant,
    staff: User,
    players: list[User],
    now: datetime,
) -> Tournament:
    """Seed the race-night tournament and its three heats. Idempotent."""
    race_night, _ = await Tournament.get_or_create(
        name=RACE_NIGHT_NAME, tenant=tenant,
        defaults={
            "description": "Weekly open race night — staff post the heats, four racers each.",
            "seed_generator": "alttpr",
            "is_active": True,
            "players_per_match": 4,
            "staff_administered": True,
            "allow_player_match_requests": False,
            "tournament_format": "Open heats of four; fastest two advance",
            "rules_url": "https://example.invalid/wizzrobe/race-night/rules",
            "average_match_duration": 100,
            "max_match_duration": 180,
        },
    )
    # Older dev databases created this tournament before it carried the
    # scheduling metadata the reports and suggestion engine read.
    await backfill(
        race_night,
        tournament_format="Open heats of four; fastest two advance",
        rules_url="https://example.invalid/wizzrobe/race-night/rules",
        average_match_duration=100,
        max_match_duration=180,
    )
    await race_night.admins.add(staff)
    for player in players:
        await TournamentPlayers.get_or_create(
            tournament=race_night, user=player, tenant=tenant,
        )

    # Heat 1 — run and confirmed. Three finishers plus a forfeit: the racer keeps
    # their seat in the roster with neither a rank nor a finish time, which is
    # how every non-finish (forfeit / no-show / DQ) is recorded.
    finished = await _make_heat(
        tenant, race_night, "Race Night — Heat 1", now - timedelta(hours=4),
    )
    if finished is not None:
        finished.started_at = finished.scheduled_at
        finished.finished_at = finished.scheduled_at + timedelta(minutes=99)
        finished.confirmed_at = finished.finished_at + timedelta(minutes=8)
        await finished.save()
        for rank, (player, seconds) in enumerate(zip(players, _HEAT_FINISH_TIMES), 1):
            await MatchPlayers.get_or_create(
                match=finished, user=player, tenant=tenant,
                defaults={"finish_rank": rank, "finish_time": seconds},
            )
        await MatchPlayers.get_or_create(
            match=finished, user=players[3], tenant=tenant,
        )

    # Heat 2 — **no title**. A heat is named by who is racing it, so the schedule,
    # the crew card and the Discord embed all have to fall back to the roster.
    untitled = await _make_heat(tenant, race_night, None, now + timedelta(hours=1.5))
    if untitled is not None:
        untitled.is_stream_candidate = True
        await untitled.save()
        for player in players:
            await MatchPlayers.get_or_create(
                match=untitled, user=player, tenant=tenant,
            )

    # Heat 3 — posted, **roster empty**. Signups close on the night; until then
    # every player-facing surface has to render a match with nobody in it.
    await _make_heat(
        tenant, race_night, "Race Night — Heat 3 (signups open)", now + timedelta(hours=3),
    )

    print(
        f"    [{tenant.slug}] race night ok "
        f"(staff-administered, 4 racers/heat, one untitled heat, one with no roster)"
    )
    return race_night


async def _make_heat(
    tenant: Tenant, tournament: Tournament, title: str | None, scheduled_at: datetime,
) -> Match | None:
    """Create one heat, or return ``None`` when it already exists.

    Returning ``None`` on the second run is what keeps the callers' roster and
    timestamp writes create-only, exactly like the other seed modules'
    ``make_match``. ``title=None`` is a usable natural key here because this
    tournament has only one untitled heat.
    """
    match, created = await Match.get_or_create(
        title=title, tournament=tournament, tenant=tenant,
        defaults={"scheduled_at": scheduled_at, "is_stream_candidate": False},
    )
    return match if created else None
