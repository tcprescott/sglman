#!/usr/bin/env python3
"""Free bracket game slots stranded by a cancelled or deleted ``Match``.

Run from the project root:
    poetry run python scripts/release_orphaned_bracket_games.py [--apply]

Before ``BracketService.release_game_if_linked`` existed, cancelling or deleting
a ``Match`` left its :class:`BracketMatchGame` row behind: the ``match`` FK is
``SET_NULL``, so the row survived as ``SCHEDULED`` with a null ``match_id`` and a
``game_number`` that stayed consumed. ``_has_free_game_slot`` then reported the
series fully booked, and a best-of-1 matchup became **permanently unschedulable**
— gone from the player dashboard, from ``list_open_matches_for_user``, and from
its own bracket dialog, with nothing surfacing it anywhere.

New cancellations fix themselves. This clears the backlog: it deletes exactly the
rows matching that signature (``match_id IS NULL`` and ``state = SCHEDULED``),
which is what "release" means everywhere else in the bracket code — a cancelled
row would keep the number consumed, so it would free nothing.

Deliberately **cross-tenant and dry-run by default**: it is an operator repair for
a bug that hit every tenant, and it deletes rows, so it prints what it would do
and changes nothing until ``--apply``. Rows whose matchup is already COMPLETE are
left alone — the series is over and its numbering is history.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from tortoise import Tortoise

from migrations.tortoise_config import TORTOISE_ORM
from models import BracketMatchGame, BracketMatchGameState, BracketMatchState


async def find_orphans() -> list:
    """Every game row stranded by the pre-fix bug, newest first — unscoped."""
    rows = await BracketMatchGame.filter(
        match_id__isnull=True,
        state=BracketMatchGameState.SCHEDULED,
    ).prefetch_related('bracket_match__bracket').order_by('-id')
    return [
        g for g in rows
        if g.bracket_match is not None
        and g.bracket_match.state != BracketMatchState.COMPLETE
    ]


async def main(apply: bool) -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        orphans = await find_orphans()
        if not orphans:
            print("No stranded bracket game slots. Nothing to do.")
            return

        print(f"Found {len(orphans)} stranded game slot(s):")
        for game in orphans:
            bracket = game.bracket_match.bracket
            print(
                f"  game {game.id}: tenant {game.tenant_id} · "
                f"bracket {bracket.id} ({bracket.name}) · "
                f"matchup {game.bracket_match_id} · game {game.game_number}"
            )

        if not apply:
            print("\nDry run — re-run with --apply to release these slots.")
            return

        for game in orphans:
            await BracketMatchGame.filter(id=game.id).delete()
        print(f"\nReleased {len(orphans)} slot(s).")
    finally:
        await Tortoise.close_connections()


if __name__ == '__main__':
    asyncio.run(main(apply='--apply' in sys.argv[1:]))
