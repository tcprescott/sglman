#!/usr/bin/env python3
"""Native-bracket fixtures for the dev seed (split out of seed_dev.py).

Must run inside the target tenant's ``tenant_scope`` — called from
``seed_for_tenant``. Idempotent like the rest of the seed.

B13 grows the original single stage into a set of per-format mid-play states plus
a two-stage group→playoff chain, driving the real :class:`BracketService`
(create → add entrant → enroll → start → report_result → complete_stage →
advance_stage) so every persisted graph is internally consistent — the same code
paths the admin tab, the public page, and the REST endpoints exercise.

Native brackets live on their **own** demo tournaments, never on the
Challonge-mirrored ``tournament`` the rest of the seed builds: the exclusivity
guard (``BracketService._ensure_no_challonge_link``) forbids a native bracket on
a Challonge-linked tournament, and the two integrations never both run one
tournament in production. Each demo tournament is guarded by an
"is stage 0 already built?" check so re-running the seed neither duplicates rows
nor double-reports a result.
"""
from typing import List, Optional, Tuple

from application.services import BracketService
from models import (
    BracketEntrant,
    BracketEntryStatus,
    BracketFormat,
    Tenant,
    Tournament,
    User,
)

# (display_name, user_key | None). ``None`` seeds a placeholder entrant (no linked
# user); a key links the entrant to a seeded ``User`` — every demo carries both.
EntrantSpec = Tuple[str, Optional[str]]


async def _demo_tournament(tenant: Tenant, name: str) -> Tournament:
    tournament, _ = await Tournament.get_or_create(
        name=name, tenant=tenant,
        defaults={
            "description": "Native-bracket demo fixture (no Challonge link).",
            "seed_generator": "alttpr",
            "is_active": True,
            "players_per_match": 2,
            "staff_administered": False,
        },
    )
    return tournament


async def _already_built(service: BracketService, tournament_id: int) -> bool:
    """A demo is fully built once its stage-0 bracket exists (idempotency guard)."""
    return bool(await service.list_brackets(tournament_id))


async def _add_entrants(
    service: BracketService,
    actor: User,
    tournament_id: int,
    users: dict[str, User],
    specs: List[EntrantSpec],
) -> List[BracketEntrant]:
    entrants: List[BracketEntrant] = []
    for display_name, user_key in specs:
        user = users[user_key] if user_key else None
        entrants.append(
            await service.add_entrant(
                actor, tournament_id, display_name,
                user.id if user is not None else None,
            )
        )
    return entrants


async def _enroll_seeded(
    service: BracketService,
    actor: User,
    bracket_id: int,
    entrants: List[BracketEntrant],
) -> None:
    for seed, entrant in enumerate(entrants, start=1):
        await service.enroll(actor, bracket_id, entrant.id, seed=seed)


async def _report_earliest_open_round(
    service: BracketService, actor: User, bracket_id: int
) -> None:
    """Report every OPEN match in the lowest-numbered open round, winner = entry1.

    Leaves later rounds OPEN/PENDING so the stage stays mid-play (deterministic:
    the lower entry-slot always wins).
    """
    open_matches = await service.get_open_matches(bracket_id)
    if not open_matches:
        return
    earliest = min(m.round for m in open_matches)
    for match in [m for m in open_matches if m.round == earliest]:
        await service.report_result(actor, match.id, match.entry1_id)


async def _single_elim(
    service: BracketService, actor: User, tenant: Tenant, users: dict[str, User]
) -> None:
    tournament = await _demo_tournament(tenant, "Bracket Demo — Single Elimination")
    if await _already_built(service, tournament.id):
        return
    bracket = await service.create_bracket(
        actor, tournament.id, "Championship", BracketFormat.SINGLE_ELIM,
    )
    entrants = await _add_entrants(
        service, actor, tournament.id, users,
        [
            ("Player One", "player_one"),
            ("Player Two", "player_two"),
            ("Player Three", "player_three"),
            ("Player Four", "player_four"),
            ("Wildcard Qualifier", None),
            ("Community Pick", None),
        ],
    )
    await _enroll_seeded(service, actor, bracket.id, entrants)
    await service.start_bracket(actor, bracket.id)
    # Round 1 resolved (byes auto-completed on start); quarter/semis open, final
    # still pending — a partially-formed elimination bracket.
    await _report_earliest_open_round(service, actor, bracket.id)


async def _double_elim(
    service: BracketService, actor: User, tenant: Tenant, users: dict[str, User]
) -> None:
    tournament = await _demo_tournament(tenant, "Bracket Demo — Double Elimination")
    if await _already_built(service, tournament.id):
        return
    bracket = await service.create_bracket(
        actor, tournament.id, "Main Event", BracketFormat.DOUBLE_ELIM,
    )
    entrants = await _add_entrants(
        service, actor, tournament.id, users,
        [
            ("Player One", "player_one"),
            ("Player Two", "player_two"),
            ("Player Three", "player_three"),
            ("Bracket Demo Bye", None),
        ],
    )
    await _enroll_seeded(service, actor, bracket.id, entrants)
    await service.start_bracket(actor, bracket.id)
    # Report the winners-bracket first round: both losers drop into the losers
    # bracket, opening a losers-bracket round (and the winners final) mid-play.
    await _report_earliest_open_round(service, actor, bracket.id)


async def _swiss(
    service: BracketService, actor: User, tenant: Tenant, users: dict[str, User]
) -> None:
    tournament = await _demo_tournament(tenant, "Bracket Demo — Swiss")
    if await _already_built(service, tournament.id):
        return
    bracket = await service.create_bracket(
        actor, tournament.id, "Swiss Qualifier", BracketFormat.SWISS,
        config={"swiss_rounds": 3},
    )
    entrants = await _add_entrants(
        service, actor, tournament.id, users,
        [
            ("Player One", "player_one"),
            ("Player Two", "player_two"),
            ("Player Three", "player_three"),
            ("Player Four", "player_four"),
            ("Late Registrant", None),
        ],
    )
    await _enroll_seeded(service, actor, bracket.id, entrants)
    await service.start_bracket(actor, bracket.id)

    # Report exactly one round-1 pairing (leave the other open so no next round is
    # generated) — a mid-round state.
    matches = await service.list_matches(bracket.id)
    contests = [
        m for m in matches
        if m.state.value == 'open' and m.entry1_id and m.entry2_id
    ]
    if contests:
        first = min(contests, key=lambda m: m.position)
        await service.report_result(actor, first.id, first.entry1_id)

    # Drop one entrant mid-event: the bye recipient (its round-1 match is already
    # complete, so the still-open pairing is untouched). Drop at both the roster
    # level (BracketEntrantStatus) and the stage-participation level
    # (BracketEntryStatus) so Swiss re-pairing would exclude them.
    bye = next(
        (m for m in matches if m.entry2_id is None and m.entry1_id is not None),
        None,
    )
    if bye is not None:
        entries = {e.id: e for e in await service.list_entries(bracket.id)}
        entry = entries.get(bye.entry1_id)
        if entry is not None and entry.status == BracketEntryStatus.ACTIVE:
            await service.drop_entrant(actor, entry.entrant_id)
            entry.status = BracketEntryStatus.DROPPED
            await entry.save()


async def _round_robin(
    service: BracketService, actor: User, tenant: Tenant, users: dict[str, User]
) -> None:
    tournament = await _demo_tournament(tenant, "Bracket Demo — Round Robin")
    if await _already_built(service, tournament.id):
        return
    bracket = await service.create_bracket(
        actor, tournament.id, "Group Stage", BracketFormat.ROUND_ROBIN,
        config={"group_count": 2},
    )
    entrants = await _add_entrants(
        service, actor, tournament.id, users,
        [
            ("Player One", "player_one"),
            ("Player Two", "player_two"),
            ("Player Three", "player_three"),
            ("Player Four", "player_four"),
            ("Open Qualifier A", None),
            ("Open Qualifier B", None),
        ],
    )
    await _enroll_seeded(service, actor, bracket.id, entrants)
    await service.start_bracket(actor, bracket.id)
    # Report one match per group so both groups are partway through with a
    # partially-formed standings table (the rest stay open).
    matches = await service.list_matches(bracket.id)
    reported_groups: set = set()
    for match in sorted(matches, key=lambda m: (m.group_number or 0, m.round, m.position)):
        if match.state.value != 'open' or match.group_number in reported_groups:
            continue
        await service.report_result(actor, match.id, match.entry1_id)
        reported_groups.add(match.group_number)


async def _two_stage(
    service: BracketService, actor: User, tenant: Tenant, users: dict[str, User]
) -> None:
    tournament = await _demo_tournament(tenant, "Bracket Demo — Groups to Playoff")
    if await _already_built(service, tournament.id):
        return

    # Stage 0 — round-robin groups, run to completion so final_rank is written.
    groups = await service.create_bracket(
        actor, tournament.id, "Group Stage", BracketFormat.ROUND_ROBIN,
        stage_order=0, config={"group_count": 2},
    )
    entrants = await _add_entrants(
        service, actor, tournament.id, users,
        [
            ("Player One", "player_one"),
            ("Player Two", "player_two"),
            ("Player Three", "player_three"),
            ("Player Four", "player_four"),
        ],
    )
    await _enroll_seeded(service, actor, groups.id, entrants)
    await service.start_bracket(actor, groups.id)
    for match in await service.get_open_matches(groups.id):
        await service.report_result(actor, match.id, match.entry1_id)
    await service.complete_stage(actor, groups.id)

    # Stage 1 — single-elimination playoff seeded from the group winners.
    playoff = await service.create_bracket(
        actor, tournament.id, "Playoff", BracketFormat.SINGLE_ELIM,
        stage_order=1,
        config={"advancement": {"count": 1, "per_group": True, "seeding": "snake"}},
    )
    await service.advance_stage(actor, tournament.id, from_stage_order=0)
    await service.start_bracket(actor, playoff.id)


async def seed_brackets_for_tenant(
    tenant: Tenant,
    tournament: Tournament,
    users: dict[str, User],
) -> None:
    """Seed one bracket per format in a mid-play state plus a two-stage chain.

    ``tournament`` is the tenant's Challonge-mirrored tournament and is left
    untouched (native brackets get their own demo tournaments — see module
    docstring). Runs inside the caller's ``tenant_scope``.
    """
    service = BracketService()
    actor = users["staff_user"]

    await _single_elim(service, actor, tenant, users)
    await _double_elim(service, actor, tenant, users)
    await _swiss(service, actor, tenant, users)
    await _round_robin(service, actor, tenant, users)
    await _two_stage(service, actor, tenant, users)
    print(f"    [{tenant.slug}] brackets ok")
