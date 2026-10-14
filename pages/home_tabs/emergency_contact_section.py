"""The Emergency contact card on a member's profile.

Name, relationship and phone for the person this community's staff should call.
Per community: the card reads and writes the contact for the community being
viewed, never another one's.

Saves on blur and after a short pause in typing, like the personal-info fields,
once both the name and the phone are filled in; a half-typed contact isn't an
error until it's saved. Removing it asks first, because it deletes the contact.
The member also sees when staff last opened it, and who.

Presentation only: service calls, no ORM.
"""

import asyncio

from nicegui import ui

from application.services import EmergencyContactService, TenantService
from application.services.emergency_contact_service import (
    NAME_MAX_LENGTH,
    PHONE_MAX_LENGTH,
    RELATIONSHIP_MAX_LENGTH,
)
from application.utils.timezone import format_local_datetime
from models import EmergencyContact, User
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.help import help_icon
from theme.notify import notify_error


def _last_opened(contact: EmergencyContact | None) -> str:
    if contact is None or contact.last_viewed_at is None:
        return ''
    when = format_local_datetime(contact.last_viewed_at, '%a %d %b %H:%M')
    by = contact.last_viewed_by.preferred_name if contact.last_viewed_by else 'a former staff member'
    return f'Staff last opened this {when} ({by}).'


async def render_emergency_contact_section(user: User) -> None:
    service = EmergencyContactService()
    try:
        current = {'contact': await service.get_mine(user)}
    except ValueError:
        return
    community = await TenantService.current_community_name()
    typing = {'n': 0, 'dirty': False}

    def field_values() -> tuple[str, str, str]:
        return name_input.value or '', relationship_input.value or '', phone_input.value or ''

    async def save() -> None:
        typing['dirty'] = False
        name, relationship, phone = field_values()
        if not name.strip() or not phone.strip():
            return
        try:
            current['contact'] = await service.save_mine(user, name, relationship, phone)
        except ValueError as e:
            phone_input.props(f'error error-message="{e!s}"')
            return
        phone_input.props(remove='error error-message')
        ui.notify('Saved', color='positive', timeout=1200)
        footer.refresh()

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

    async def remove() -> None:
        try:
            await service.remove_mine(user)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        current['contact'] = None
        typing['n'] += 1
        typing['dirty'] = False
        for field in (name_input, relationship_input, phone_input):
            field.value = ''
        phone_input.props(remove='error error-message')
        ui.notify('Emergency contact removed', color='positive')
        footer.refresh()

    def confirm_remove() -> None:
        ConfirmationDialog(
            title='Remove your emergency contact?',
            message="It's deleted straight away. Staff won't have anyone to call for "
                    'you until you add one again.',
            confirm_text='Remove',
            on_confirm=remove,
        ).open()

    contact = current['contact']
    with ui.card().classes('card-full-width'):
        with ui.row().classes('items-center gap-1 no-wrap wiz-help-row'):
            ui.label('Emergency contact').classes('section-title')
            await help_icon('emergency-contact', user=user)
        ui.label(
            f'Who should {community} staff call if something happens to you at an event?'
        ).classes('text-muted text-caption')

        def text_field(label: str, value: str, limit: int, **props: str) -> ui.input:
            field = ui.input(label, value=value, on_change=on_typing) \
                .props(f'outlined stack-label maxlength={limit}').classes('input-full-width')
            for key, val in props.items():
                field.props[key] = val
            field.on('blur', on_blur)
            return field

        name_input = text_field('Name', contact.name if contact else '', NAME_MAX_LENGTH,
                                autocomplete='off')
        with ui.element('div').classes('wiz-emergency-contact-fields w-full'):
            relationship_input = text_field(
                'Relationship (optional)', (contact.relationship or '') if contact else '',
                RELATIONSHIP_MAX_LENGTH, autocomplete='off',
            )
            phone_input = text_field('Phone', contact.phone if contact else '', PHONE_MAX_LENGTH,
                                     type='tel', autocomplete='off')

        with ui.row().classes('items-start gap-2 no-wrap'):
            ui.icon('privacy_tip', size='sm').classes('text-warning')
            ui.label(
                f'Only {community} staff can see this, and every time they open it is '
                'logged. Other communities never see it.'
            ).classes('text-caption text-warning col')

        @ui.refreshable
        def footer() -> None:
            contact = current['contact']
            if contact is None:
                return
            with ui.row().classes('w-full items-center justify-between gap-2'):
                ui.label(_last_opened(contact)).classes('text-caption text-muted')
                ui.button('Remove contact', on_click=confirm_remove).classes('q-ml-auto') \
                    .props('flat no-caps color=negative')

        footer()
