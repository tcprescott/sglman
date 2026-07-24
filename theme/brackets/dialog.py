"""Shared match detail + staff-reporting dialog for the bracket views.

Opened by clicking a match card on the public bracket page *or* in the admin
Results dialog's embedded bracket, so both surfaces get the identical visual
report/override flow (docs/bracket-ui-plan.md, U5). Presentation-only: it renders
NiceGUI and calls ``BracketService`` for the write (the sanctioned
presentation → service call), rebinding ``tenant_scope`` because it fires from a
detached client event. The caller supplies the resolved lookups, the tenant id,
the actor, and an ``on_saved`` refresh callback.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Dict, Optional

from nicegui import ui
from tortoise import exceptions as tortoise_exceptions

from application.services import BracketService
from application.tenant_context import tenant_scope
from models import BracketMatch, BracketMatchGameState, BracketMatchState, User
from theme.notify import notify_error


def _games_of(match: BracketMatch) -> list:
    """The series' game rows, or [] when the caller didn't prefetch them.

    ``BracketRepository.list_matches`` prefetches ``games``; a caller that built
    the match another way simply renders no series detail rather than raising.
    """
    related = getattr(match, 'games', None)
    try:
        return list(related) if related is not None else []
    except tortoise_exceptions.NoValuesFetched:
        return []


_GAME_BADGE = {
    BracketMatchGameState.SCHEDULED: 'positive',
    BracketMatchGameState.COMPLETE: 'primary',
    BracketMatchGameState.CANCELLED: 'grey',
}


def _render_games(games: list, entry_name: dict, best_of: int) -> None:
    """The per-game breakdown of a series (nothing at all for a best-of-1).

    A plain row stack rather than a ``ui.table``: three rows don't warrant a
    table, and every table needs a mobile grid (``check_table_grid``). Unscheduled
    games are shown as arithmetic — ``best_of`` minus the rows that exist — since
    game rows are created lazily at schedule time.
    """
    if best_of <= 1:
        if games:
            ui.label('Scheduled to a match room.').classes('text-caption text-grey')
        return

    ui.separator()
    ui.label(f'Best of {best_of}').classes('section-title')
    for game in sorted(games, key=lambda g: g.game_number):
        with ui.row().classes('items-center justify-between w-full q-py-xs'):
            with ui.row().classes('items-center gap-2 no-wrap'):
                ui.label(f'Game {game.game_number}').classes('text-caption')
                winner = entry_name.get(game.winner_entry_id)
                if winner:
                    ui.label(winner).classes('text-bold')
                    if game.forfeit:
                        ui.label('FF').classes('text-bold text-negative')
                elif game.cancelled_reason:
                    ui.label(game.cancelled_reason).classes('text-caption text-grey')
            ui.badge(
                game.state.value.title(),
                color=_GAME_BADGE.get(game.state, 'grey'),
            )
    remaining = best_of - len({g.game_number for g in games})
    if remaining > 0:
        ui.label(
            f'{remaining} game(s) not yet scheduled'
        ).classes('text-caption text-grey')


_STATE_BADGE = {
    BracketMatchState.PENDING: 'grey',
    BracketMatchState.OPEN: 'positive',
    BracketMatchState.COMPLETE: 'primary',
}


def build_match_dialog(
    match: BracketMatch,
    entry_name: Dict[int, str],
    entry_seed: Dict[int, Optional[int]],
    records: Dict[int, tuple],
    number: Optional[int],
    *,
    best_of: int = 1,
    is_staff: bool,
    actor: Optional[User],
    tenant_id: int,
    service: BracketService,
    on_saved: Callable[[], Awaitable[None]],
) -> None:
    """Build and open the match dialog: entrants, scores/FF, state, reporting."""
    completed = match.state == BracketMatchState.COMPLETE

    def name_of(entry_id: Optional[int]) -> str:
        return entry_name.get(entry_id, 'TBD') if entry_id is not None else 'TBD'

    with ui.dialog() as dialog, ui.card().classes('w-[26rem] max-w-full'):
        with ui.row().classes('items-center justify-between w-full'):
            ui.label(f'Match {number}' if number else 'Match').classes('text-h6')
            ui.badge(
                match.state.value.title(),
                color=_STATE_BADGE.get(match.state, 'grey'),
            )

        for slot, entry_id in ((1, match.entry1_id), (2, match.entry2_id)):
            is_winner = (
                completed and match.winner_id is not None and entry_id == match.winner_id
            )
            score = match.entry1_score if slot == 1 else match.entry2_score
            with ui.row().classes('items-center justify-between w-full q-py-xs'):
                with ui.row().classes('items-center gap-2 no-wrap'):
                    seed = entry_seed.get(entry_id) if entry_id is not None else None
                    if seed is not None:
                        ui.label(f'#{seed}').classes('text-caption text-grey')
                    ui.label(name_of(entry_id)).classes('text-bold' if is_winner else '')
                    rec = records.get(entry_id) if entry_id is not None else None
                    if rec is not None and (rec[0] or rec[1]):
                        ui.label(f'({rec[0]}-{rec[1]})').classes('text-caption text-grey')
                if completed and match.forfeit and entry_id is not None and not is_winner:
                    ui.label('FF').classes('text-bold text-negative')
                elif score is not None:
                    ui.label(str(score)).classes('text-bold' if is_winner else '')
                elif is_winner:
                    ui.icon('emoji_events', size='xs').classes('text-primary')

        _render_games(_games_of(match), entry_name, best_of)

        can_report = (
            is_staff
            and match.state in (BracketMatchState.OPEN, BracketMatchState.COMPLETE)
            and match.entry1_id is not None
            and match.entry2_id is not None
        )
        if can_report:
            ui.separator()
            ui.label(
                'Report result' if match.state == BracketMatchState.OPEN
                else 'Override result'
            ).classes('section-title')
            with ui.row().classes('items-center gap-2 w-full'):
                s1 = ui.number(
                    label=name_of(match.entry1_id), value=match.entry1_score, min=0,
                ).props('dense inputmode=numeric').classes('w-32')
                s2 = ui.number(
                    label=name_of(match.entry2_id), value=match.entry2_score, min=0,
                ).props('dense inputmode=numeric').classes('w-32')
            ff = ui.switch('Forfeit', value=match.forfeit)

            async def save(winner_id: int) -> None:
                e1 = int(s1.value) if s1.value is not None else None
                e2 = int(s2.value) if s2.value is not None else None
                with tenant_scope(tenant_id):
                    try:
                        if match.state == BracketMatchState.OPEN:
                            await service.report_result(
                                actor, match.id, winner_id,
                                entry1_score=e1, entry2_score=e2, forfeit=ff.value,
                            )
                        else:
                            await service.override_result(
                                actor, match.id, winner_id,
                                entry1_score=e1, entry2_score=e2, forfeit=ff.value,
                            )
                    except (ValueError, PermissionError) as ex:
                        notify_error(ex)
                        return
                ui.notify('Result saved', color='positive')
                dialog.close()
                await on_saved()

            with ui.row().classes('gap-2 w-full q-mt-xs'):
                ui.button(
                    f'Winner: {name_of(match.entry1_id)}', icon='emoji_events',
                    on_click=lambda _=None, w=match.entry1_id: save(w),
                ).props('dense color=primary')
                ui.button(
                    f'Winner: {name_of(match.entry2_id)}', icon='emoji_events',
                    on_click=lambda _=None, w=match.entry2_id: save(w),
                ).props('dense color=primary')

        with ui.row().classes('justify-end w-full q-mt-sm'):
            ui.button('Close', on_click=dialog.close).props('flat')
    dialog.open()
