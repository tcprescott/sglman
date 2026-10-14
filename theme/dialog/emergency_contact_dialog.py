"""The staff view of one member's emergency contact, opened from their ⋮ on Users.

Opening it is the logged act: the service writes the audit row before it hands
the contact back, so the dialog says so rather than asking first.
"""

import re

from nicegui import ui

from application.services import EmergencyContactService
from application.utils.timezone import format_local_time
from models import User
from theme.clipboard import copy_to_clipboard
from theme.dialog._helpers import dialog_actions, form_dialog
from theme.notify import notify_error

__all__ = ['open_emergency_contact_dialog', 'tel_href']


def tel_href(phone: str) -> str:
    """A ``tel:`` link for a stored number: its digits, keeping a leading ``+``."""
    digits = re.sub(r'\D', '', phone)
    return f"tel:{'+' if phone.lstrip().startswith('+') else ''}{digits}"


async def open_emergency_contact_dialog(actor: User, member: User) -> None:
    try:
        contact = await EmergencyContactService().open_for(actor, member)
    except (ValueError, PermissionError) as e:
        notify_error(e)
        return

    who = member.preferred_name
    with form_dialog('Emergency contact', card_classes='dialog-card dialog-card--sm') as dialog:
        with ui.column().classes('q-pa-md gap-3 full-width'):
            with ui.row().classes('gap-1 items-baseline'):
                ui.label('For').classes('text-muted')
                ui.label(who).classes('text-weight-bold')
            if contact is None:
                ui.label(f"{who} hasn't added an emergency contact.")
                ui.label("This look is still in the audit log.").classes('text-caption text-muted')
            else:
                with ui.element('div').classes('wiz-emergency-contact'):
                    ui.label('Name').classes('text-muted')
                    ui.label(contact.name).classes('text-weight-bold')
                    if contact.relationship:
                        ui.label('Relationship').classes('text-muted')
                        ui.label(contact.relationship)
                    ui.label('Phone').classes('text-muted')
                    ui.link(contact.phone, tel_href(contact.phone)) \
                        .classes('text-weight-bold text-subtitle1')
                ui.label(
                    f"You opened this at {format_local_time(contact.last_viewed_at)}. "
                    "It's in the audit log."
                ).classes('text-caption text-muted')
        if contact is not None:
            with dialog_actions().classes('justify-end'):
                ui.button(
                    'Copy number',
                    on_click=lambda: copy_to_clipboard(contact.phone, 'Phone number'),
                ).props('flat')
                ui.button('Call', icon='call').props(f'color=primary href="{tel_href(contact.phone)}"')
    dialog.open()
