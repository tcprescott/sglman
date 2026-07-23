#!/usr/bin/env python3
"""Native-bracket fixtures for the dev seed (split out of seed_dev.py).

Must run inside the target tenant's ``tenant_scope`` — called from
``seed_for_tenant``. Idempotent like the rest of the seed.

B0 seeds one minimal, coherent single-elimination stage so every bracket model
has a representative row from day one (the seed-coverage ratchet demands it).
B13 grows this into per-format mid-states plus a two-stage chain.
"""
from models import (
    Bracket,
    BracketEntrant,
    BracketEntry,
    BracketFormat,
    BracketMatch,
    BracketMatchState,
    Tenant,
    Tournament,
    User,
)


async def seed_brackets_for_tenant(
    tenant: Tenant,
    tournament: Tournament,
    users: dict[str, User],
) -> None:
    # One single-elimination stage on the tenant's tournament (stage 0). DRAFT
    # so it stays independent of the Challonge mirror seeded on the same
    # tournament — the two never both run a tournament in production, but as
    # inert fixtures they coexist fine for rendering the admin surfaces.
    bracket, _ = await Bracket.get_or_create(
        tournament=tournament, stage_order=0, tenant=tenant,
        defaults={"name": "Main Bracket", "format": BracketFormat.SINGLE_ELIM},
    )

    # One linked entrant and one placeholder (seed now, link later).
    linked, _ = await BracketEntrant.get_or_create(
        tournament=tournament, display_name="Player One", tenant=tenant,
        defaults={"user": users["player_one"]},
    )
    placeholder, _ = await BracketEntrant.get_or_create(
        tournament=tournament, display_name="TBD Qualifier", tenant=tenant,
        defaults={"user": None},
    )

    entry1, _ = await BracketEntry.get_or_create(
        bracket=bracket, entrant=linked, tenant=tenant, defaults={"seed": 1},
    )
    entry2, _ = await BracketEntry.get_or_create(
        bracket=bracket, entrant=placeholder, tenant=tenant, defaults={"seed": 2},
    )

    await BracketMatch.get_or_create(
        bracket=bracket, round=1, position=1, tenant=tenant,
        defaults={
            "entry1": entry1, "entry2": entry2, "state": BracketMatchState.OPEN,
        },
    )
    print(f"    [{tenant.slug}] brackets ok")
