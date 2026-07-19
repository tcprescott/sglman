#!/usr/bin/env python3
"""Challonge mirror fixtures for the dev seed (split out of seed_dev.py).

Must run inside the target tenant's ``tenant_scope`` — called from
``seed_for_tenant``. Idempotent like the rest of the seed.
"""
from datetime import date, datetime, timedelta

from models import (
    ChallongeApiUsage, ChallongeConnection, ChallongeMatch, ChallongeMatchState,
    ChallongeParticipant, Match, Tenant, Tournament, User,
)


async def seed_challonge_for_tenant(
    tenant: Tenant,
    users: dict[str, User],
    tournament: Tournament,
    staff: User,
    finished_match: Match,
    now_utc: datetime,
    today: date,
) -> None:
    # Player identity is global (one-time capture); the connection/bracket
    # mirror is per tenant.
    for uname, challonge_uid, challonge_name in [
        ("player_one", "cu_1001", "playerone"),
        ("player_two", "cu_1002", "playertwo"),
    ]:
        u = users[uname]
        if u.challonge_user_id is None:
            u.challonge_user_id = challonge_uid
            u.challonge_username = challonge_name
            u.challonge_linked_at = now_utc
            await u.save()

    if not tournament.challonge_tournament_id:
        tournament.challonge_tournament_id = f"cht_dev_{tenant.slug}"
        tournament.challonge_tournament_url = f"https://challonge.com/wizzrobe_{tenant.slug}"
        tournament.challonge_last_synced_at = now_utc
        await tournament.save()

    # A near-expiry token so the service-health board / tenant subset (PR 5)
    # has a live credential-warning to render. Heal older rows that predate the
    # expiry column too, so a re-seed against an existing dev DB still shows it.
    challonge_expiry = now_utc + timedelta(days=2)
    conn, _ = await ChallongeConnection.get_or_create(
        challonge_username="wizzrobe_service", tenant=tenant,
        defaults={
            "access_token": "dev-access-token-not-real",
            "refresh_token": "dev-refresh-token-not-real",
            "scopes": "me tournaments:read tournaments:write",
            "token_expires_at": challonge_expiry,
            "connected_by": staff,
        },
    )
    if conn.token_expires_at is None:
        conn.token_expires_at = challonge_expiry
        await conn.save()

    participants: dict[str, ChallongeParticipant] = {}
    participant_specs = [
        ("cp_1", "Player One", "cu_1001", users["player_one"]),
        ("cp_2", "Player Two", "cu_1002", users["player_two"]),
        ("cp_3", "Player Three", None, users["player_three"]),
        ("cp_4", "Player Four", None, users["player_four"]),
    ]
    for cp_id, name, challonge_uid, user in participant_specs:
        part, _ = await ChallongeParticipant.get_or_create(
            tournament=tournament, challonge_participant_id=cp_id, tenant=tenant,
            defaults={"name": name, "challonge_user_id": challonge_uid, "user": user},
        )
        participants[cp_id] = part

    await ChallongeMatch.get_or_create(
        tournament=tournament, challonge_match_id="cm_1", tenant=tenant,
        defaults={
            "round": 1, "state": ChallongeMatchState.COMPLETE,
            "participant1": participants["cp_1"], "participant2": participants["cp_3"],
            "winner_participant": participants["cp_1"], "match": finished_match,
        },
    )
    await ChallongeMatch.get_or_create(
        tournament=tournament, challonge_match_id="cm_2", tenant=tenant,
        defaults={
            "round": 1, "state": ChallongeMatchState.OPEN,
            "participant1": participants["cp_2"], "participant2": participants["cp_4"],
        },
    )

    usage_period = today.strftime("%Y-%m")
    await ChallongeApiUsage.get_or_create(
        period=usage_period, tenant=tenant, defaults={"request_count": 42},
    )
    print(f"    [{tenant.slug}] challonge ok")
