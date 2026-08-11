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

from pages.admin_tabs.admin_qualifiers.shared import LIVE_TAB, enum_value, live_race_color


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
                    ui.button(icon='delete',
                              on_click=lambda lid=lr.id: _cancel_live_race(lid)
                              ).props('flat round color=negative').tooltip('Cancel')
                if lr.racetime_slug:
                    ui.label(f'racetime: {lr.racetime_slug}').classes('text-caption text-grey')

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
