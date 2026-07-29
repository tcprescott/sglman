"""Results dialog — report and correct match results for a started stage.

Elimination stages get the real bracket renderer embedded (click a card to open
the shared match dialog); every format keeps the flat open/completed lists as the
reliable fallback.
"""

from typing import Optional

from nicegui import ui

from application.tenant_context import tenant_scope
from models import BracketFormat
from theme.brackets import (
    assign_match_numbers,
    build_context,
    build_match_dialog,
    entry_records,
    match_nodes,
    render_elimination,
    render_elimination_mobile,
)
from theme.dialog._helpers import dialog_actions, form_dialog
from theme.notify import notify_error
from theme.tables.admin_crud import current_actor

from .shared import ELIM_FORMATS, entry_name_map


async def open_results(row, client, *, service, tenant_id, tournament_id, on_change) -> None:
    """Open the results dialog for one stage. ``on_change`` refreshes the table."""
    bracket_id = row['id']
    tid = tournament_id
    with client:
        actor = await current_actor()
        with form_dialog(f"Results — {row['name']}") as dialog:

            @ui.refreshable
            async def body() -> None:
                with tenant_scope(tenant_id):
                    bracket = await service.get_bracket(bracket_id)
                    matches = await service.list_matches(bracket_id)
                    entries = await service.list_entries(bracket_id)
                    names = await entry_name_map(service, bracket_id, tid)
                    live_state = await service.matchup_live_state(matches)

                def slot_label(entry_id: Optional[int]) -> str:
                    if entry_id is None:
                        return '—'
                    return names.get(entry_id, f'Entry {entry_id}')

                async def report(match_id: int, winner_entry_id: int) -> None:
                    with tenant_scope(tenant_id):
                        try:
                            await service.report_result(actor, match_id, winner_entry_id)
                        except (ValueError, PermissionError) as ex:
                            notify_error(ex)
                            return
                    ui.notify('Result recorded', color='positive')
                    await body.refresh()
                    await on_change()

                async def override(match_id: int, winner_entry_id: int) -> None:
                    m = next((x for x in matches if x.id == match_id), None)
                    score1, score2 = (m.entry1_score, m.entry2_score) if m else (None, None)
                    # Carry the recorded scoreline and forfeit flag through the
                    # correction rather than nulling them. When the correction
                    # flips which slot won, the scores flip with it — otherwise a
                    # 2-1 kept as-is would fail the winner-holds-the-higher-score
                    # rule the service enforces.
                    if m is not None and m.winner_id is not None and winner_entry_id != m.winner_id:
                        score1, score2 = score2, score1
                    with tenant_scope(tenant_id):
                        try:
                            await service.override_result(
                                actor, match_id, winner_entry_id,
                                entry1_score=score1, entry2_score=score2,
                                forfeit=bool(m.forfeit) if m else False,
                            )
                        except (ValueError, PermissionError) as ex:
                            notify_error(ex)
                            return
                    ui.notify('Result overridden', color='positive')
                    await body.refresh()
                    await on_change()

                async def _after_write() -> None:
                    await body.refresh()
                    await on_change()

                # Visual bracket embed (compact): staff click a match card to
                # report/override via the shared dialog. Supplements the flat
                # lists below (they stay as a reliable fallback).
                embedded = (
                    bracket is not None
                    and bracket.format in ELIM_FORMATS
                    and bool(matches)
                )
                if embedded:
                    def on_card(match_id: int) -> None:
                        m = next((x for x in matches if x.id == match_id), None)
                        if m is None:
                            return
                        records = entry_records([e.id for e in entries], matches)
                        number = assign_match_numbers(match_nodes(matches)).get(match_id)
                        entry_seed = {e.id: e.seed for e in entries}
                        build_match_dialog(
                            m, names, entry_seed, records, number,
                            best_of=service.resolve_best_of(bracket, m),
                            is_staff=True, actor=actor, tenant_id=tenant_id,
                            service=service, on_saved=_after_write,
                            live=live_state.get(match_id),
                        )

                    ctx = build_context(
                        bracket.config, entries, matches, names,
                        on_card_click=on_card, live_state=live_state,
                    )
                    ui.label('Bracket — click a match to report a result') \
                        .classes('section-title')
                    double = bracket.format == BracketFormat.DOUBLE_ELIM
                    with ui.element('div').classes('bracket-embed-scroll'):
                        with ui.element('div').classes('bracket-2d w-full'):
                            render_elimination(matches, ctx, double=double)
                        # The 2-D bracket is unusable in a phone-width dialog (a
                        # ~1200px canvas in a ~300px box), so staff get the same
                        # accordion as the public page.
                        with ui.element('div').classes('bracket-mobile-list w-full'):
                            render_elimination_mobile(matches, ctx, double=double)
                    ui.separator()

                open_matches = [m for m in matches if m.state.value == 'open']
                complete_matches = [
                    m for m in matches
                    if m.state.value == 'complete'
                    and m.entry1_id is not None and m.entry2_id is not None
                ]

                def result_row(m, *, action, icon, color) -> None:
                    """One match: its summary, then a winner button each.

                    Stacked rather than a single flex row — the buttons carry full
                    entrant names (up to ~257px), so at phone width the row
                    wrapped into a ragged three lines.
                    """
                    summary = (
                        f'R{m.round} #{m.position}: '
                        f'{slot_label(m.entry1_id)} vs {slot_label(m.entry2_id)}'
                    )
                    if m.winner_id is not None:
                        summary += f' → {slot_label(m.winner_id)}'
                    if m.entry1_score is not None and m.entry2_score is not None:
                        summary += f' ({m.entry1_score}-{m.entry2_score})'
                    if m.forfeit:
                        summary += ' [forfeit]'
                    with ui.column().classes('gap-0 w-full q-py-xs'):
                        ui.label(summary).classes('text-caption ellipsis w-full')
                        with ui.row().classes('items-center gap-1 w-full'):
                            for eid in (m.entry1_id, m.entry2_id):
                                if eid is None:
                                    continue
                                ui.button(
                                    slot_label(eid), icon=icon,
                                    on_click=lambda _=None, mid=m.id, w=eid: action(mid, w),
                                ).props(f'flat dense color={color}')

                def open_list() -> None:
                    if not open_matches:
                        ui.label('No open matches.').classes('text-muted')
                    for m in open_matches:
                        result_row(m, action=report, icon='emoji_events', color='primary')

                def complete_list() -> None:
                    if not complete_matches:
                        ui.label('No completed matches.').classes('text-muted')
                    for m in complete_matches:
                        result_row(
                            m, action=override,
                            icon='published_with_changes', color='secondary',
                        )

                # Where the visual bracket is present these lists are the
                # fallback, not the primary surface: collapsed, they stop a
                # 32-match stage from burying the dialog's own actions under
                # ~3000px of scroll. Swiss / round robin have no embed, so there
                # they stay open — they are the only surface.
                if embedded:
                    with ui.expansion(f'Open matches ({len(open_matches)})').classes('w-full'):
                        open_list()
                    with ui.expansion(
                        f'Completed matches — override ({len(complete_matches)})',
                    ).classes('w-full'):
                        complete_list()
                else:
                    ui.label('Open matches').classes('section-title')
                    open_list()
                    ui.separator()
                    ui.label('Completed matches — override').classes('section-title')
                    complete_list()

                with dialog_actions().classes('justify-end'):
                    ui.button('Close', on_click=dialog.close).props('flat')

            await body()
        dialog.open()
