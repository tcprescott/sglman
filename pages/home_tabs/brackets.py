"""Brackets tab — the browse path into a tournament's bracket.

Home is the surface a signed-out visitor lands on, so this is where the public
bracket pages become reachable without knowing a URL: one card per tournament
that has stages, each stage opening its bracket view. Both targets are
``public_page``, so nothing here requires a login.

Presentation only: one read through :class:`BracketService`, no ORM writes.
Navigation goes through ``ui.navigate.to`` with a bare path, which picks up the
tenant's ``root_path`` under path-mode multitenancy.
"""

from typing import Dict, List, Tuple

from nicegui import app, ui

from application.services import AuthService, BracketService, get_user_from_discord_id
from models import Bracket
from theme.brackets import (
    format_label,
    stage_label,
    state_color,
    state_label,
    visible_stages,
)


def group_by_tournament(
    brackets: List[Bracket],
) -> List[Tuple[int, str, List[Bracket]]]:
    """Stages grouped under their tournament as ``(id, name, stages)``.

    Pure, so the grouping is unit-testable without a page. Relies on dict
    insertion order to preserve the repository's ordering (active tournaments
    first, then name, then stage order).
    """
    stages_by_tournament: Dict[int, List[Bracket]] = {}
    names: Dict[int, str] = {}
    for bracket in brackets:
        stages_by_tournament.setdefault(bracket.tournament_id, []).append(bracket)
        names[bracket.tournament_id] = bracket.tournament.name
    return [
        (tournament_id, names[tournament_id], stages)
        for tournament_id, stages in stages_by_tournament.items()
    ]


def _render_stage(bracket: Bracket) -> None:
    with ui.row().classes('items-center justify-between w-full q-py-xs'):
        with ui.column().classes('gap-0'):
            ui.label(bracket.name).classes('text-body2 text-bold')
            ui.label(
                f'{stage_label(bracket.stage_order)} · {format_label(bracket.format)}'
            ).classes('text-caption')
        with ui.row().classes('items-center gap-2 no-wrap'):
            ui.badge(state_label(bracket.state), color=state_color(bracket.state))
            ui.button(
                'View', icon='visibility',
                on_click=lambda bid=bracket.id: ui.navigate.to(f'/brackets/{bid}'),
            ).props('flat dense')


async def brackets_tab() -> None:
    # DRAFT stages are unpublished (theme/brackets/visibility.py): a staff
    # viewer browses the full list, everyone else only what has started.
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    is_staff = await AuthService.is_staff(user)
    brackets = visible_stages(
        await BracketService().list_all_brackets(), is_staff=is_staff,
    )

    with ui.column().classes('page-container'):
        with ui.row().classes('header-row'):
            ui.label('Brackets').classes('page-title')
        ui.separator().classes('separator-spacing')

        if not brackets:
            ui.label('No brackets have been published yet.').classes('italic-note')
            return

        ui.label(
            'Tournament brackets, standings, and results. No account needed.'
        ).classes('text-muted')

        for tournament_id, name, stages in group_by_tournament(brackets):
            with ui.card().classes('w-full q-pa-md q-mb-sm'):
                with ui.row().classes('items-center justify-between w-full'):
                    ui.label(name).classes('text-subtitle1 text-bold')
                    # Multi-stage tournaments get the stage index too; a
                    # single-stage one is fully described by the row below it.
                    if len(stages) > 1:
                        ui.button(
                            'All stages', icon='list',
                            on_click=lambda tid=tournament_id: ui.navigate.to(
                                f'/tournament/{tid}/brackets'
                            ),
                        ).props('flat dense')
                ui.separator()
                for bracket in stages:
                    _render_stage(bracket)
