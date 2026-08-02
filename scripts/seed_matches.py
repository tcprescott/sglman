"""Dev-seed fixtures for the general-purpose tournament's matches.

Split out of ``seed_dev.py`` for length, following the one-module-per-domain
convention the volunteer, equipment, on-site and race-night fixtures already
use: called from inside the caller's ``tenant_scope``, idempotent, and
tenant-stamped like every other seeded row.

This is the lifecycle fixture set — one match per state a proctor or admin can
meet (scheduled / checked-in / in-progress / finished / disputed / off-stream /
undated) — plus everything that hangs off those matches: station seating, the
rolled seeds, the dispute flag, acknowledgments in each of their states,
watchers, stream volunteers, and the tournament notification preference.

Returns the matches by key because the rest of the seed builds on them: crew
signs up for them, the Challonge mirror points at the finished one, the audit
fixtures cite them.
"""

import json
from datetime import datetime, timedelta

from models import (
    GeneratedSeeds,
    Match,
    MatchAcknowledgment,
    MatchNotificationLevel,
    MatchPlayers,
    MatchStreamVolunteer,
    MatchWatcher,
    Stage,
    Tenant,
    Tournament,
    TournamentNotificationPreference,
    User,
)


async def seed_matches_for_tenant(
    tenant: Tenant,
    tournament: Tournament,
    staff: User,
    players: list[User],
    stages: dict[str, Stage],
    now: datetime,
) -> dict[str, Match | GeneratedSeeds]:
    """Seed the lifecycle matches and their extras; return them by key."""
    stage1, stage2, stage3 = stages["stage1"], stages["stage2"], stages["stage3"]

    async def make_match(
        title: str,
        offset_hours: float | None,
        *,
        seated: bool = False,
        started: bool = False,
        finished: bool = False,
        confirmed: bool = True,
        p1: User | None = None,
        p2: User | None = None,
        stage: Stage | None = None,
        stream_candidate: bool = True,
        comment: str | None = None,
    ) -> Match:
        scheduled_at = now + timedelta(hours=offset_hours) if offset_hours is not None else None
        match, created = await Match.get_or_create(
            title=title,
            tournament=tournament,
            tenant=tenant,
            defaults={
                "scheduled_at": scheduled_at,
                "stage": stage,
                "is_stream_candidate": stream_candidate,
                "comment": comment,
            },
        )
        if not created:
            return match
        anchor = scheduled_at or now
        if seated or started or finished:
            match.seated_at = anchor - timedelta(minutes=10)
        if started or finished:
            match.started_at = anchor
        if finished:
            match.finished_at = anchor + timedelta(hours=1)
            if confirmed:
                match.confirmed_at = anchor + timedelta(hours=1, minutes=5)
        await match.save()
        for rank, player in enumerate([p1, p2], 1):
            if player:
                await MatchPlayers.get_or_create(
                    match=match,
                    user=player,
                    tenant=tenant,
                    defaults={"finish_rank": rank if finished else None},
                )
        return match

    scheduled_match = await make_match("Scheduled Match",   2,   p1=players[0], p2=players[1])
    checked_in_match = await make_match("Checked-In Match",  0,   seated=True,  p1=players[0], p2=players[1], stage=stage1)
    in_progress_match = await make_match("In-Progress Match", -1,  seated=True, started=True,  p1=players[2], p2=players[3], stage=stage2)
    finished_match = await make_match("Finished Match",    -3,  seated=True, started=True, finished=True, p1=players[0], p2=players[2], stage=stage1)
    stage3_match = await make_match(
        "Stage 3 Rematch", 3, seated=True, p1=players[1], p2=players[3], stage=stage3,
        comment="Requested a rematch after a disconnect last round.",
    )
    await make_match(
        "Off-Stream Match", 4, p1=players[2], p2=players[0], stream_candidate=False,
    )
    future_match = await make_match(
        "Grand Finals", 30, p1=players[3], p2=players[1], stage=stage1,
        comment="Best of 3, winner takes the trophy.",
    )
    disputed_match = await make_match(
        "Disputed Match", -5, seated=True, started=True, finished=True, confirmed=False,
        p1=players[1], p2=players[2], stage=stage2,
        comment="Result under review — desync reported by both players.",
    )
    await make_match(
        "TBD Match", None, p1=players[3], p2=players[0], stream_candidate=False,
    )
    # Exactly one match with **no title**. Most matches carry a round label, but a
    # blank one happens, and when it does every surface falls back to the roster
    # (``match.title or players_str`` in the crew service, the reconciler's own
    # label, the race-stage name). One fixture, because one is how often it occurs
    # — and because ``title=None`` is only a usable natural key while it is unique
    # within the tournament.
    await make_match(None, 6, p1=players[1], p2=players[2], stage=stage2)
    # Seat the two matches that are checked in but not finished at real
    # stations, so the schedule shows stations out of the box and the
    # occupancy check has something to trip on: 1/2/5/6 read as in use when
    # a proctor opens the picker on any other match.
    for seated_match, labels in (
        (checked_in_match, ("1", "5")),
        (in_progress_match, ("2", "6")),
    ):
        seated_players = await MatchPlayers.filter(
            match=seated_match, tenant=tenant,
        ).order_by("id")
        for seated_player, label in zip(seated_players, labels, strict=False):
            if seated_player.assigned_station is None and tenant.slug == "default":
                seated_player.assigned_station = label
                await seated_player.save()

    print(f"    [{tenant.slug}] matches ok")

    # Generated seeds, attached to matches that have already been rolled.
    # Both carry provenance, because that is what the seed card renders: which
    # randomizer, the settings as rolled, and what the roll cost.
    seed, _ = await GeneratedSeeds.get_or_create(
        seed_url="https://alttpr.com/en/h/DevSeed0",
        tenant=tenant,
        defaults={
            "seed_info": json.dumps({"logic": "NoGlitches", "spoilers": "off"}),
            "randomizer": "alttpr",
            "settings_snapshot": {"glitches": "none", "mode": "open", "goal": "ganon"},
            "provider_meta": {
                "provider": "alttpr", "operation": "generate_seed",
                "attempts": 1, "latency_ms": 4210, "surface": "match",
            },
        },
    )
    if finished_match.generated_seed_id is None:
        finished_match.generated_seed = seed
        await finished_match.save()

    disputed_seed, _ = await GeneratedSeeds.get_or_create(
        seed_url="https://alttpr.com/en/h/DevSeed1",
        tenant=tenant,
        defaults={
            "seed_info": json.dumps({"logic": "Glitched", "spoilers": "mystery"}),
            "randomizer": "alttpr",
            "settings_snapshot": {"glitches": "overworld_glitches", "mode": "open"},
            # Two attempts: the shape a roll that survived a transient upstream
            # failure leaves behind, which is exactly what a dispute wants to see.
            "provider_meta": {
                "provider": "alttpr", "operation": "generate_seed",
                "attempts": 2, "latency_ms": 11840, "surface": "match",
            },
        },
    )
    if disputed_match.generated_seed_id is None:
        disputed_match.generated_seed = disputed_seed
        await disputed_match.save()

    # The dispute flag itself, so the admin's review queue has a contested
    # row out of the box — this match has claimed to be disputed since the
    # first seed script and only now actually is.
    if not disputed_match.needs_review:
        disputed_match.needs_review = True
        await disputed_match.save()

    # Match acknowledgments — the checked-in match's players have both confirmed.
    for player in (players[0], players[1]):
        await MatchAcknowledgment.get_or_create(
            match=checked_in_match, user=player, tenant=tenant,
            defaults={"acknowledged_at": now, "auto_acknowledged": False},
        )
    # The scheduled match still has one un-acknowledged and one pending player.
    await MatchAcknowledgment.get_or_create(
        match=scheduled_match, user=players[0], tenant=tenant,
        defaults={"acknowledged_at": now, "auto_acknowledged": False},
    )
    await MatchAcknowledgment.get_or_create(
        match=scheduled_match, user=players[1], tenant=tenant,
        defaults={"acknowledged_at": None, "auto_acknowledged": False},
    )
    # Grand Finals — one player auto-acknowledged, the other hasn't responded.
    await MatchAcknowledgment.get_or_create(
        match=future_match, user=players[3], tenant=tenant,
        defaults={"acknowledged_at": now, "auto_acknowledged": True},
    )
    await MatchAcknowledgment.get_or_create(
        match=future_match, user=players[1], tenant=tenant,
        defaults={"acknowledged_at": None, "auto_acknowledged": False},
    )

    # Match watchers — staff keeps an eye on the scheduled, in-progress, and disputed matches.
    for m in (scheduled_match, in_progress_match, disputed_match):
        await MatchWatcher.get_or_create(user=staff, match=m, tenant=tenant)

    # Stream volunteers — both halves of the signal, because "one player asked"
    # and "both players asked" read differently to whoever builds the stream
    # schedule. The scheduled match has both; the future one has a single player
    # waiting on their opponent.
    for m, volunteers in (
        (scheduled_match, (players[0], players[1])),
        (future_match, (players[3],)),
    ):
        for volunteer in volunteers:
            await MatchStreamVolunteer.get_or_create(user=volunteer, match=m, tenant=tenant)

    # Notification preferences — one person per level, because the level is what
    # the fan-out reads: a fixture set where everyone is on ALL cannot show that
    # the narrower choices actually narrow anything.
    notification_specs = [
        (staff, MatchNotificationLevel.ALL),
        (players[0], MatchNotificationLevel.STREAMED),
        (players[1], MatchNotificationLevel.STREAMED_AND_CANDIDATES),
        # Explicitly off, which is not the same as never having chosen: the row
        # exists and says "none".
        (players[2], MatchNotificationLevel.NONE),
    ]
    for user, level in notification_specs:
        await TournamentNotificationPreference.get_or_create(
            user=user, tournament=tournament, tenant=tenant,
            defaults={"match_notifications": level},
        )
    print(f"    [{tenant.slug}] match extras ok")

    return {
        "scheduled": scheduled_match,
        "checked_in": checked_in_match,
        "in_progress": in_progress_match,
        "finished": finished_match,
        "stage3": stage3_match,
        "future": future_match,
        "disputed": disputed_match,
        "seed": seed,
    }
