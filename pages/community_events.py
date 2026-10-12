"""Community events: what members are running for each other during the event.

``/community-events`` lists the approved events still to come, grouped by day,
with a subscribe toggle on each, the viewer's own submissions underneath, and the
Submit button. ``/community-events/{id}`` is one event, and is where every DM
about it lands: a subscriber's reminder, a host's approval or rejection.

Members only (``protected_page`` runs the membership gate) and behind
``COMMUNITY_EVENTS``. Presentation only: everything goes through
:class:`CommunityEventService`, and descriptions are rendered through the closed
block parser, never as markup.
"""

from itertools import groupby
from typing import Optional

from nicegui import app, ui

from application.content import parse_blocks
from application.services import (
    AuthService,
    CommunityEventService,
    SystemConfigService,
    TenantService,
    get_user_from_discord_id,
)
from middleware.auth import protected_page
from models import CommunityEvent, CommunityEventStatus, FeatureFlag, User
from theme.base import BaseLayout
from theme.community_events import (
    chip,
    day_label,
    disclaimer,
    is_live,
    meta_row,
    status_chip,
    when_line,
)
from theme.dialog.community_event_dialog import CommunityEventDialog
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.empty_state import empty_state
from theme.error_page import render_not_found
from theme.help.render import render_blocks
from theme.notify import notify_error
from theme.page_header import page_header

__all__ = ['create']

INDEX = '/community-events'


async def _viewer() -> Optional[User]:
    return await get_user_from_discord_id(app.storage.user.get('discord_id'))


async def _chrome(user: User, *parts: str) -> None:
    community = await TenantService.current_community_name() or 'Wizzrobe'
    ui.page_title(' — '.join((*parts, community)))
    await BaseLayout(user=user, show_admin=await AuthService.can_view_admin(user)).render()


def _subscribe_button(service: CommunityEventService, user: User, event: CommunityEvent,
                      subscribed: bool, on_change) -> None:
    async def toggle() -> None:
        try:
            if subscribed:
                await service.unsubscribe(user, event.id)
                ui.notify("Unsubscribed. You won't get a reminder.", color='positive')
            else:
                await service.subscribe(user, event.id)
                message = "Subscribed. We'll DM you before it starts."
                if not user.dm_notifications:
                    message += ' Turn DMs back on in your profile to get it.'
                ui.notify(message, color='positive')
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        await on_change()

    if subscribed:
        ui.button('Subscribed', icon='notifications_active', on_click=toggle) \
            .props('outline color=primary').tooltip('Stop the reminder for this event')
    else:
        ui.button('Remind me', icon='notifications_none', on_click=toggle) \
            .props('flat color=primary').tooltip('Get a Discord DM before this event starts')


def _event_card(service, user, event: CommunityEvent, subscribed: bool, count: int, on_change) -> None:
    with ui.card().classes('wiz-community-event full-width'):
        with ui.row().classes('items-start justify-between no-wrap full-width gap-2'):
            with ui.column().classes('gap-1 col min-w-0'):
                ui.link(event.title, f'{INDEX}/{event.id}').classes('wiz-community-event__title')
                with ui.row().classes('items-center gap-2'):
                    if is_live(event):
                        chip('Happening now', 'live')
                    ui.label(when_line(event)).classes('wiz-community-event__meta')
                if event.location:
                    meta_row('place', event.location)
                meta_row('person', f'Hosted by {event.host.preferred_name}')
                if count:
                    meta_row('notifications', f'{count} subscribed')
            _subscribe_button(service, user, event, subscribed, on_change)


def create() -> None:
    @protected_page('/community-events', feature=FeatureFlag.COMMUNITY_EVENTS)
    async def community_events_index() -> None:
        user = await _viewer()
        if user is None:
            ui.label('Your account could not be found.').classes('text-error')
            return
        await _chrome(user, 'Community Events')
        service = CommunityEventService()
        is_staff = await AuthService.is_staff(user)
        needs_review = await SystemConfigService.community_events_require_approval()

        with ui.column().classes('page-container-narrow w-full gap-3'):
            page_header('Community Events', 'Meetups, panels and side events members are running.')
            disclaimer()

            @ui.refreshable
            async def upcoming() -> None:
                events = await service.list_upcoming(user)
                if not events:
                    empty_state('Nothing is listed yet. Running something? Submit it.')
                    return
                mine, counts = await service.subscription_state(user, [e.id for e in events])
                for day, group in groupby(events, key=day_label):
                    ui.label(day).classes('wiz-community-event__day')
                    for event in group:
                        _event_card(service, user, event, event.id in mine, counts.get(event.id, 0),
                                    refresh_all)

            @ui.refreshable
            async def submissions() -> None:
                events = await service.list_mine(user)
                if not events:
                    return
                ui.label('Your events').classes('wiz-community-event__day')
                for event in events:
                    with ui.card().classes('wiz-community-event full-width'):
                        with ui.row().classes('items-center gap-2'):
                            ui.link(event.title, f'{INDEX}/{event.id}').classes('wiz-community-event__title')
                            status_chip(event)
                        ui.label(when_line(event, with_day=True)).classes('wiz-community-event__meta')
                        if event.status is CommunityEventStatus.REJECTED and event.review_note:
                            meta_row('feedback', f'Staff said: {event.review_note}')

            async def refresh_all(_saved=None) -> None:
                upcoming.refresh()
                submissions.refresh()

            ui.button(
                'Submit an event', icon='add',
                on_click=lambda: CommunityEventDialog(
                    user, is_staff=is_staff, needs_review=needs_review, on_saved=refresh_all,
                ).open(),
            ).props('color=primary').classes('self-start')

            await upcoming()
            await submissions()

    @protected_page('/community-events/{event_id}', feature=FeatureFlag.COMMUNITY_EVENTS)
    async def community_event_detail(event_id: int) -> None:
        user = await _viewer()
        if user is None:
            ui.label('Your account could not be found.').classes('text-error')
            return
        service = CommunityEventService()
        try:
            event = await service.get_event(user, event_id)
        except ValueError:
            await render_not_found(
                user=user,
                message="We couldn't find that event. It may have been cancelled or taken down.",
                actions=[('All community events', 'event', INDEX)],
            )
            return

        await _chrome(user, event.title, 'Community Events')
        can_manage = event.host_id == user.id or await AuthService.is_staff(user)
        is_staff = await AuthService.is_staff(user)

        @ui.refreshable
        async def body() -> None:
            current = await service.get_event(user, event_id)
            with ui.column().classes('page-container-narrow w-full gap-3'):
                ui.link('← All community events', INDEX).classes('text-caption')
                page_header(current.title)
                disclaimer()
                with ui.row().classes('items-center gap-2'):
                    if current.status is not CommunityEventStatus.APPROVED:
                        status_chip(current)
                    elif is_live(current):
                        chip('Happening now', 'live')
                if current.status is CommunityEventStatus.REJECTED and current.review_note:
                    meta_row('feedback', f'Staff said: {current.review_note}')
                meta_row('schedule', when_line(current, with_day=True))
                if current.location:
                    meta_row('place', current.location)
                meta_row('person', f'Hosted by {current.host.preferred_name}')

                with ui.row().classes('items-center gap-2 wrap'):
                    if current.status is CommunityEventStatus.APPROVED:
                        mine, counts = await service.subscription_state(user, [current.id])
                        _subscribe_button(service, user, current, current.id in mine, body.refresh)
                        if counts.get(current.id):
                            ui.label(f'{counts[current.id]} subscribed').classes('text-muted')
                    if can_manage and current.status is not CommunityEventStatus.CANCELLED:
                        ui.button(
                            'Edit', icon='edit',
                            on_click=lambda: CommunityEventDialog(
                                user, current, is_staff=is_staff, on_saved=_after_save,
                            ).open(),
                        ).props('flat')
                        ui.button('Cancel event', icon='event_busy', on_click=lambda: _confirm_cancel(current)) \
                            .props('flat color=negative')

                if current.description:
                    with ui.column().classes('wiz-community-event__body gap-0 full-width'):
                        render_blocks(parse_blocks(current.description))

        async def _after_save(_saved) -> None:
            body.refresh()

        def _confirm_cancel(current: CommunityEvent) -> None:
            async def cancel() -> None:
                try:
                    await service.cancel(user, current.id)
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Event cancelled. Anyone subscribed has been told.', color='positive')
                body.refresh()

            ConfirmationDialog(
                f'Cancel {current.title}? It comes off the listing, and anyone subscribed gets a DM.',
                on_confirm=cancel, confirm_text='Cancel event', cancel_text='Keep it',
                title='Cancel this event?',
            ).open()

        await body()

