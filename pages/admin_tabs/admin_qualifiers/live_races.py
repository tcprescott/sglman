"""Admin Async Qualifiers — the Live Races tab.

A live race runs one pool permalink synchronously on racetime and captures each
entrant's finish as an approved, par-scored run. It is the one tab backed by a
different service (:class:`AsyncQualifierLiveRaceService`) and the one that talks
to an external system, so it lives apart from the self-paced tabs.

Built as a factory rather than plain functions: the page owns ``state`` and the
tab loaders, and this tab needs to read the former and trigger the latter. The
factory takes those as parameters and returns the refreshable view — the same
closure-over-page-state shape the sibling tabs have inline, just in its own file.
"""

from typing import Any, Awaitable, Callable

from nicegui import ui

from application.services.async_qualifier.async_qualifier_live_race_service import ManualResult
from application.utils.duration import parse_hms
from models import AsyncQualifierRunStatus
from pages.admin_tabs.admin_qualifiers.shared import (
    BOARD_TAB,
    LIVE_TAB,
    RUNS_TAB,
    enum_value,
    live_race_color,
)

# The three outcomes a human may assert, worded as a person would say them rather
# than as the enum spells them.
_FINISHED = 'Finished'
_OUTCOMES = [_FINISHED, 'Forfeited', 'Disqualified']
_OUTCOME_STATUS = {
    _FINISHED: AsyncQualifierRunStatus.FINISHED,
    'Forfeited': AsyncQualifierRunStatus.FORFEIT,
    'Disqualified': AsyncQualifierRunStatus.DISQUALIFIED,
}


def build_live_tab(
    *,
    state: dict,
    service: Any,
    current: Callable[[], Awaitable[Any]],
    reload_tabs: Callable[..., Awaitable[None]],
    placeholder: Callable[[str], bool],
    notify_error: Callable[[Exception], None],
) -> Callable[[], None]:
    """Return the refreshable Live Races view, wired to the page's state and loaders."""

    @ui.refreshable
    def live_view() -> None:
        if state.get('shell') is None or placeholder(LIVE_TAB):
            return
        pools = state['pools']
        with ui.row().classes('items-center'):
            ui.button('New Live Race', icon='add',
                      on_click=lambda: _open_live_race_dialog(pools)
                      ).props('color=primary')
        ui.label(
            'A live race runs a pool permalink synchronously on racetime; each '
            'entrant\'s result is captured as an approved, par-scored run.'
        ).classes('text-caption text-grey')
        if not pools:
            ui.label('Add a pool first, then schedule a live race for it.').classes('text-grey')
            return
        if not state['live_races']:
            ui.label("No live races scheduled. Start one when you're ready.").classes('text-grey')
        for lr in state['live_races']:
            with ui.card().classes('w-full'):
                with ui.row().classes('items-center full-width'):
                    ui.label(lr.match_title).classes('text-subtitle1')
                    ui.badge(enum_value(lr.status), color=live_race_color(lr.status))
                    ui.badge(f'pool: {lr.pool.name}', color='grey')
                    ui.space()
                    # A cancelled race is over: offering to open a room for it invites
                    # a click that only produces a refusal.
                    if not lr.racetime_slug and enum_value(lr.status) != 'cancelled':
                        ui.button('Open room', icon='meeting_room',
                                  on_click=lambda lid=lr.id: _open_room(lid)
                                  ).props('flat color=primary')
                    # Offered on a finished race too: re-recording is idempotent, and
                    # a race whose results came in with someone unmatched is exactly
                    # the case that needs recording again.
                    if enum_value(lr.status) != 'cancelled':
                        ui.button('Record results', icon='edit_note',
                                  on_click=lambda race=lr: _open_record_dialog(race)
                                  ).props('flat color=primary')
                    ui.button(icon='delete',
                              on_click=lambda lid=lr.id: _cancel_live_race(lid)
                              ).props('flat round color=negative').tooltip('Cancel')
                if lr.racetime_slug:
                    ui.label(f'racetime: {lr.racetime_slug}').classes('text-caption text-grey')
                # The to-do the audit log used to keep to itself: whoever raced under
                # these handles has no local account linked, so their result was
                # dropped and nothing said so.
                if lr.unmatched_handles:
                    with ui.column().classes('gap-0'):
                        with ui.row().classes('items-center text-caption text-orange'):
                            ui.icon('person_off')
                            ui.label(f'{len(lr.unmatched_handles)} racetime account(s) matched '
                                     'nobody here: ' + ', '.join(lr.unmatched_handles))
                        ui.label('Their results were not recorded. Link the account on '
                                 'Admin → Users, then record this race again.'
                                 ).classes('text-caption text-grey')

    def _open_live_race_dialog(pools) -> None:
        with ui.dialog() as dialog, ui.card().classes('w-[32rem]'):
            ui.label('New Live Race').classes('text-h6')
            title_in = ui.input('Race title').classes('w-full')
            pool_options = {p.id: p.name for p in pools}
            pool_in = ui.select(pool_options, label='Pool',
                                value=pools[0].id if pools else None).classes('w-full')
            permalink_options = {None: '(assign later)'}
            for p in pools:
                for pl in p.permalinks:
                    permalink_options[pl.id] = f'{p.name}: {pl.url[:48]}'
            permalink_in = ui.select(permalink_options, label='Permalink (optional)',
                                     value=None).classes('w-full')

            async def submit():
                try:
                    await service.create_live_race(
                        await current(), int(pool_in.value),
                        match_title=title_in.value, permalink_id=permalink_in.value,
                    )
                    ui.notify('Live race scheduled', color='positive')
                    dialog.close()
                    await reload_tabs(LIVE_TAB)
                except (ValueError, PermissionError) as e:
                    notify_error(e)

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Create', icon='add', on_click=submit).props('color=primary')
        dialog.open()

    def _open_record_dialog(race) -> None:
        """Type in a race's results, when racetime never told us them.

        One row per racer: who, what happened, and — for a finisher — their time.
        Deliberately the same three outcomes racetime reports, so a hand-recorded
        race is indistinguishable downstream from one the room delivered.
        """
        rows: list = []

        with ui.dialog() as dialog, ui.card().classes('w-[40rem]'):
            ui.label(f'Record results — {race.match_title}').classes('text-h6')
            ui.label('For when the racetime event never arrived. Each racer is recorded '
                     'as an approved run, par-scored exactly as the room’s own results '
                     'would have been.').classes('text-caption text-grey')
            if race.unmatched_handles:
                ui.label('Racers whose racetime account is not linked here cannot be '
                         'recorded — link it on Admin → Users first.'
                         ).classes('text-caption text-orange')
            holder = ui.column().classes('w-full gap-1')

            def add_row() -> None:
                with holder:
                    with ui.row().classes('items-center w-full') as row:
                        person = ui.select(state['racer_options'], label='Racer',
                                           with_input=True).classes('grow')
                        outcome = ui.select(_OUTCOMES, label='Outcome',
                                            value=_FINISHED).classes('w-40')
                        time_in = ui.input('Finish time', placeholder='1:23:45').classes('w-40')
                        # A forfeit or a DQ has no time; hiding the field is clearer
                        # than accepting a value the service will discard.
                        time_in.bind_visibility_from(outcome, 'value',
                                                     lambda v: v == _FINISHED)
                        ui.button(icon='close', on_click=lambda r=row: _drop(r)
                                  ).props('flat round dense color=grey')
                rows.append({'row': row, 'person': person,
                             'outcome': outcome, 'time': time_in})

            def _drop(row) -> None:
                for entry in list(rows):
                    if entry['row'] is row:
                        rows.remove(entry)
                row.delete()

            add_row()
            with ui.row().classes('items-center'):
                ui.button('Add racer', icon='person_add', on_click=add_row).props('flat')

            async def submit():
                results = []
                for entry in rows:
                    if not entry['person'].value:
                        continue
                    finished = entry['outcome'].value == _FINISHED
                    seconds = None
                    if finished:
                        try:
                            seconds = parse_hms(entry['time'].value)
                        except ValueError as e:
                            notify_error(ValueError(f'Finish time: {e}'))
                            return
                    results.append(ManualResult(
                        user_id=int(entry['person'].value),
                        status=_OUTCOME_STATUS[entry['outcome'].value],
                        elapsed_seconds=seconds,
                    ))
                if not results:
                    notify_error(ValueError('Pick at least one racer.'))
                    return
                try:
                    captured = await service.record_manual_finish(
                        await current(), race.id, results)
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify(f'Recorded {len(captured)} run(s)', color='positive')
                dialog.close()
                # The runs are new rows and the board's totals move with them.
                await reload_tabs(LIVE_TAB, RUNS_TAB, BOARD_TAB)

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Record', icon='save', on_click=submit).props('color=primary')
        dialog.open()

    async def _open_room(live_race_id: int) -> None:
        try:
            await service.open_room(await current(), live_race_id)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify('Room opened', color='positive')
        await reload_tabs(LIVE_TAB)

    async def _cancel_live_race(live_race_id: int) -> None:
        try:
            await service.cancel_live_race(await current(), live_race_id)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify('Live race cancelled', color='positive')
        await reload_tabs(LIVE_TAB)

    return live_view
