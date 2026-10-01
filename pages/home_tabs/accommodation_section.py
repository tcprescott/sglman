"""The ADA accommodation card on a member's profile.

A checkbox and, once it is ticked, an optional details box and the status staff
have given the request. Per community: the card reads and writes the request
for the community being viewed, never another one's.

The checkbox commits at once; the details box saves on blur and after a short
pause in typing, the same autosave shape as the personal-info fields above it.
Staff notes are never shown here.

Presentation only: service calls, no ORM.
"""

import asyncio

from nicegui import ui

from application.services import AccommodationService, TenantService
from application.services.accommodation_service import DETAILS_MAX_LENGTH
from models import AccommodationRequest, AccommodationStatus, User
from theme.accommodation_copy import STATUS_CHIP, STATUS_LABELS, privacy_disclaimer


def _is_open(request: AccommodationRequest | None) -> bool:
    return request is not None and request.status is not AccommodationStatus.WITHDRAWN


async def render_accommodation_section(user: User) -> None:
    service = AccommodationService()
    try:
        current = {'request': await service.get_mine(user)}
    except ValueError:
        return
    community = await TenantService.current_community_name()
    typing = {'n': 0, 'dirty': False}

    async def save() -> None:
        typing['dirty'] = False
        try:
            current['request'] = await service.set_my_request(
                user, requested_box.value, details_input.value,
            )
        except ValueError as e:
            ui.notify(str(e), color='warning')
            return
        ui.notify('Saved', color='positive', position='bottom', timeout=1200)
        status_row.refresh()

    async def on_toggle() -> None:
        typing['n'] += 1
        if not requested_box.value:
            details_input.value = ''
        await save()
        details_block.set_visibility(requested_box.value)

    async def on_typing() -> None:
        typing['dirty'] = True
        typing['n'] += 1
        mine = typing['n']
        await asyncio.sleep(1.2)
        if mine == typing['n'] and typing['dirty']:
            await save()

    async def on_blur() -> None:
        if typing['dirty']:
            typing['n'] += 1
            await save()

    with ui.card().classes('card-full-width'):
        ui.label('ADA accommodation').classes('section-title')
        ui.label(
            "Let staff know you'd like an accommodation at this community's events."
        ).classes('text-muted text-caption')

        requested_box = ui.checkbox(
            "I'd like to request an ADA accommodation",
            value=_is_open(current['request']),
            on_change=on_toggle,
        )

        with ui.column().classes('w-full gap-2 q-mt-xs') as details_block:
            details_input = ui.textarea(
                'Details (optional)',
                value=(current['request'].details or '') if _is_open(current['request']) else '',
                placeholder='e.g. step-free access to the stage, a seat near an exit, '
                            'extra time between matches',
                on_change=on_typing,
            ).props(f'outlined autogrow stack-label counter maxlength={DETAILS_MAX_LENGTH}') \
                .classes('input-full-width')
            details_input.on('blur', on_blur)

            with ui.row().classes('items-start gap-2 no-wrap'):
                ui.icon('privacy_tip', size='sm').classes('text-warning')
                ui.label(privacy_disclaimer(community)).classes('text-caption text-warning col')

            @ui.refreshable
            def status_row() -> None:
                request = current['request']
                if not _is_open(request):
                    return
                with ui.row().classes('items-center gap-2'):
                    ui.label('Staff status:').classes('text-caption text-muted')
                    with ui.element('span').classes(f'wiz-chip {STATUS_CHIP[request.status]}'):
                        ui.label(STATUS_LABELS[request.status])

            status_row()
        details_block.set_visibility(requested_box.value)
