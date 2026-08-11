"""Admin Async Qualifiers — the Reviewers tab.

A qualifier's ``admins`` are its reviewer set: who may work the queue, and who is
blocked from reviewing their own run. `add_admin`, `remove_admin` and
`list_admins` have existed on the service and over REST since PR 9, and no
control anywhere called them — so the one thing that decides who signs off on a
community's qualifying could only be changed with an API token. This is the tab
that changes that.

Built as a factory for the same reason as ``live_races``: the page owns ``state``
and the loaders, and this tab reads the former and triggers the latter.
"""

from typing import Any, Awaitable, Callable

from nicegui import ui

from application.services import UserService
from application.services.async_qualifier.async_qualifier_rules import display_name
from pages.admin_tabs.admin_qualifiers.shared import REVIEWERS_TAB


def build_reviewers_tab(
    *,
    state: dict,
    service: Any,
    current: Callable[[], Awaitable[Any]],
    reload_tabs: Callable[..., Awaitable[None]],
    placeholder: Callable[[str], bool],
    notify_error: Callable[[Exception], None],
) -> Callable[[], None]:
    """Return the refreshable Reviewers view."""

    @ui.refreshable
    def reviewers_view() -> None:
        if state.get('shell') is None or placeholder(REVIEWERS_TAB):
            return
        ui.label(
            'A reviewer may approve or reject any run in this qualifier — except '
            'their own, which the service refuses. Everyone here can also edit this '
            'list.'
        ).classes('text-caption text-grey')
        with ui.row().classes('items-center'):
            ui.button('Add reviewer', icon='person_add', on_click=_open_add_dialog
                      ).props('color=primary')
        reviewers = state['reviewers']
        if not reviewers:
            # Not a broken state: community STAFF can administer every qualifier,
            # so an empty roster is the default rather than a lockout.
            ui.label('No qualifier-specific reviewers. Community staff can still '
                     'review every run here.').classes('text-grey')
            return
        for person in reviewers:
            with ui.card().classes('w-full'):
                with ui.row().classes('items-center full-width'):
                    ui.label(display_name(person)).classes('text-subtitle1')
                    if not person.discord_id:
                        # Review verdicts DM the runner, and the queue notification
                        # DMs the reviewer — neither reaches someone with no Discord.
                        ui.badge('no Discord', color='grey').tooltip(
                            'This reviewer will not receive queue notifications.')
                    ui.space()
                    ui.button('Remove', icon='person_remove',
                              on_click=lambda p=person: _remove(p)
                              ).props('flat color=negative')

    def _open_add_dialog() -> None:
        with ui.dialog() as dialog, ui.card().classes('w-[32rem]'):
            ui.label('Add a reviewer').classes('text-h6')
            picker = ui.select(
                state['reviewer_options'], label='Person', with_input=True,
            ).classes('w-full')
            if not state['reviewer_options']:
                ui.label('Everyone in this community is already a reviewer.').classes(
                    'text-caption text-grey')

            async def submit() -> None:
                if not picker.value:
                    return
                try:
                    await service.add_admin(
                        await current(), state['managing'],
                        await UserService().get_user_by_id(int(picker.value)),
                    )
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Reviewer added', color='positive')
                dialog.close()
                await reload_tabs(REVIEWERS_TAB)

            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                add = ui.button('Add', icon='person_add', on_click=submit).props('color=primary')
                add.bind_enabled_from(picker, 'value', lambda v: v is not None)
        dialog.open()

    async def _remove(person) -> None:
        try:
            await service.remove_admin(await current(), state['managing'], person)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        ui.notify('Reviewer removed', color='positive')
        await reload_tabs(REVIEWERS_TAB)

    return reviewers_view
