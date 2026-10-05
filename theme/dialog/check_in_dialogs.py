"""Dialogs for event check-in: linking a registrant, adding a walk-up, event setup.

Presentation only. Every action goes through :class:`CheckInService`, which
enforces who may do what; these dialogs only decide what to offer. All three
open as full-screen sheets on a phone (``form_dialog``), because the desk runs
on volunteers' phones and the keyboard would otherwise cover half the form.
"""

from typing import Awaitable, Callable, List, Optional

from nicegui import ui

from application.services import CheckInService
from models import CheckInEntrant, CheckInEvent, CheckInEventStatus, User
from theme.connection import REQUIRES_SOCKET_CLASS
from theme.dialog._helpers import dialog_actions, form_dialog, submit_on_enter
from theme.notify import notify_error

OnDone = Callable[[], Awaitable[None]]

_PROVIDER_LABELS = {
    'discord': 'Discord', 'twitch': 'Twitch', 'gplus': 'Google', 'facebook': 'Facebook',
    'twitter': 'Twitter', 'battlenet': 'Battle.net', 'youtube': 'YouTube',
}

_STATUS_OPTIONS = {
    CheckInEventStatus.DRAFT.value: 'Draft (not on the desk yet)',
    CheckInEventStatus.OPEN.value: 'Open (desk live, syncing)',
    CheckInEventStatus.CLOSED.value: 'Closed',
}


def provider_label(provider: Optional[str]) -> str:
    return _PROVIDER_LABELS.get(provider or '', (provider or 'unknown').title())


def _person_line(user: User) -> str:
    extra = [n for n in (user.username if user.display_name else None, user.twitch_username) if n]
    return f"{user.preferred_name} ({', '.join(extra)})" if extra else user.preferred_name


def _member_results(container: ui.column, users: List[User], on_pick: Callable[[User], Awaitable[None]],
                    empty_text: str) -> None:
    container.clear()
    with container:
        if not users:
            ui.label(empty_text).classes('text-caption text-grey-7')
            return
        for user in users:
            ui.button(
                _person_line(user), icon='person',
                on_click=lambda _, u=user: on_pick(u),
            ).props('flat no-caps align=left').classes(f'w-full {REQUIRES_SOCKET_CLASS}')


async def open_link_dialog(
    service: CheckInService, actor: User, entrant: CheckInEntrant, on_done: OnDone,
) -> None:
    """Pick the Wizzrobe account a registrant belongs to."""
    suggestions = await service.suggest_users(entrant)

    with form_dialog(f'Link {entrant.display_name}') as dialog:
        async def pick(user: User) -> None:
            try:
                await service.link(actor, entrant.id, user.id)
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            dialog.close()
            ui.notify(f'Linked to {user.preferred_name}.', color='positive')
            await on_done()

        with ui.column().classes('q-pa-md gap-3 full-width'):
            if entrant.matcherino_user_id:
                ui.label(
                    f'Matcherino: {entrant.display_name} · signed in with '
                    f'{provider_label(entrant.auth_provider)}'
                ).classes('text-caption text-grey-7')
            ui.label('Suggestions').classes('text-subtitle2')
            suggested = ui.column().classes('w-full gap-0')
            _member_results(suggested, suggestions, pick, 'No one in this community looks like a match.')

            ui.label('Search members').classes('text-subtitle2 q-mt-sm')
            results = ui.column().classes('w-full gap-0')

            async def search(e) -> None:
                users = await service.search_members(entrant.event, e.value or '')
                _member_results(
                    results, users, pick,
                    'Type at least two letters.' if len(e.value or '') < 2 else 'No members match.',
                )

            box = ui.input(placeholder='Name, username or Twitch').props(
                'outlined dense clearable debounce=300 autofocus').classes('w-full')
            with box.add_slot('prepend'):
                ui.icon('search')
            box.on_value_change(search)
        with dialog_actions().classes('justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
    dialog.open()


async def open_walk_up_dialog(
    service: CheckInService, actor: User, event: CheckInEvent, on_done: OnDone,
) -> None:
    """Add someone who isn't registered on Matcherino. Staff only."""
    chosen: dict = {'user': None}

    with form_dialog('Add walk-up') as dialog:
        with ui.column().classes('q-pa-md gap-3 full-width'):
            mode = ui.toggle({'member': 'A member', 'name': 'Just a name'}, value='member') \
                .props('no-caps spread').classes('w-full')
            member_box = ui.column().classes('w-full gap-1')
            with member_box:
                picked = ui.label('No member picked yet.').classes('text-caption text-grey-7')
                results = ui.column().classes('w-full gap-0')

                async def pick(user: User) -> None:
                    chosen['user'] = user
                    picked.text = f'Picked: {user.preferred_name}'
                    picked.classes(replace='text-body2 text-positive')

                async def search(e) -> None:
                    users = await service.search_members(event, e.value or '')
                    _member_results(
                        results, users, pick,
                        'Type at least two letters.' if len(e.value or '') < 2 else 'No members match.',
                    )

                box = ui.input(placeholder='Search members').props(
                    'outlined dense clearable debounce=300').classes('w-full')
                with box.add_slot('prepend'):
                    ui.icon('search')
                box.on_value_change(search)
            name_input = ui.input('Their name').props('outlined dense').classes('w-full')
            name_input.bind_visibility_from(mode, 'value', backward=lambda v: v == 'name')
            member_box.bind_visibility_from(mode, 'value', backward=lambda v: v == 'member')
            check_now = ui.checkbox('Check them in now', value=True)

        async def submit() -> None:
            try:
                if mode.value == 'member':
                    if chosen['user'] is None:
                        ui.notify('Pick a member first.', color='warning')
                        return
                    entrant = await service.add_walk_up(
                        actor, event.id, user_id=chosen['user'].id, check_in=check_now.value)
                else:
                    entrant = await service.add_walk_up(
                        actor, event.id, name=name_input.value, check_in=check_now.value)
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            dialog.close()
            ui.notify(
                f'{entrant.display_name} added' + (' and checked in.' if check_now.value else '.'),
                color='positive',
            )
            await on_done()

        with dialog_actions().classes('justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Add', icon='person_add', on_click=submit).props('color=primary') \
                .classes(REQUIRES_SOCKET_CLASS)
        submit_on_enter(dialog, submit)
    dialog.open()


async def open_event_dialog(
    service: CheckInService, actor: User, on_done: OnDone, event: Optional[CheckInEvent] = None,
) -> None:
    """Create or edit a check-in event. Staff only."""
    title = 'Edit check-in event' if event else 'New check-in event'
    with form_dialog(title) as dialog:
        with ui.column().classes('q-pa-md gap-3 full-width'):
            name = ui.input('Event name', value=event.name if event else '').props('outlined dense') \
                .classes('w-full')
            with ui.row().classes('w-full items-start no-wrap gap-2'):
                bounty = ui.number(
                    'Matcherino bounty ID',
                    value=event.matcherino_bounty_id if event else None,
                    format='%d', min=1,
                ).props('outlined dense clearable').classes('col')
                lookup_btn = ui.button('Look up', icon='travel_explore').props('flat no-caps') \
                    .classes(REQUIRES_SOCKET_CLASS)
            found = ui.label(
                "The number at the end of the event's Matcherino link. "
                'Leave it empty for a walk-up-only event.'
            ).classes('text-caption text-grey-7')

            async def look_up() -> None:
                if not bounty.value:
                    ui.notify('Enter a bounty ID first.', color='warning')
                    return
                try:
                    found_bounty = await service.preview_bounty(actor, int(bounty.value))
                except (ValueError, PermissionError) as e:
                    found.text = str(e)
                    found.classes(replace='text-caption text-warning')
                    return
                found.text = f'Found: {found_bounty.title}'
                found.classes(replace='text-caption text-positive')
                if not (name.value or '').strip():
                    name.value = found_bounty.title

            lookup_btn.on_click(look_up)
            status = ui.select(
                _STATUS_OPTIONS, label='Status',
                value=(event.status.value if event else CheckInEventStatus.DRAFT.value),
            ).props('outlined dense').classes('w-full')
            interval = ui.number(
                'Sync with Matcherino every (minutes)',
                value=event.sync_interval_minutes if event else 5, min=1, max=120, format='%d',
            ).props('outlined dense').classes('w-full')

        async def submit() -> None:
            bounty_id = int(bounty.value) if bounty.value else None
            try:
                if event is None:
                    await service.create_event(
                        actor, name.value, bounty_id=bounty_id,
                        status=CheckInEventStatus(status.value),
                        sync_interval_minutes=int(interval.value or 5),
                    )
                else:
                    await service.update_event(
                        actor, event.id, name.value, bounty_id,
                        CheckInEventStatus(status.value), int(interval.value or 5),
                    )
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            dialog.close()
            ui.notify('Saved.', color='positive')
            await on_done()

        with dialog_actions().classes('justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save', icon='save', on_click=submit).props('color=primary') \
                .classes(REQUIRES_SOCKET_CLASS)
        submit_on_enter(dialog, submit)
    dialog.open()
