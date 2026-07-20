"""Shared equipment-table building blocks.

The admin equipment page (`pages/admin_tabs/admin_equipment.py`), the home
Equipment tab (`pages/home_tabs/equipment.py`), and the asset detail page
(`pages/equipment.py`) each hand-rolled the same status labels, status-badge
slot, mobile grid card, action buttons, and checkout/checkin wiring. This module
centralizes those pieces so the pages converge onto one copy (audit §2C.7).

Everything here is presentation-only: status labels, Quasar/Vue slot templates,
and thin handler factories over the already-shared ``open_checkout`` /
``quick_checkin`` flows. No business logic or ORM writes.
"""

from typing import Awaitable, Callable, Iterable, Mapping, Optional

from nicegui import app, background_tasks, context, ui

from application.services import get_user_from_discord_id
from theme.dialog.checkout_dialog import open_checkout, quick_checkin

__all__ = [
    'STATUS_LABELS',
    'status_label',
    'status_badge_color',
    'STATUS_BADGE_SLOT',
    'CHECKOUT_BTN',
    'CHECKIN_BTN',
    'EDIT_BTN',
    'DELETE_BTN',
    'view_btn',
    'actions_slot',
    'grid_field_row',
    'GRID_STATUS_ROW',
    'grid_card',
    'equipment_rows',
    'make_checkout_handler',
    'make_checkin_handler',
    'wire_checkout_checkin',
]

STATUS_LABELS = {
    'available': 'Available',
    'checked_out': 'Checked out',
    'retired': 'Retired',
}


def status_label(status_value: str) -> str:
    """Human label for a raw ``EquipmentStatus`` value."""
    return STATUS_LABELS.get(status_value, status_value)


def status_badge_color(status_value: str) -> str:
    """Quasar badge colour for a status value (positive/warning/grey)."""
    if status_value == 'available':
        return 'positive'
    if status_value == 'checked_out':
        return 'warning'
    return 'grey'


# Server-side rows carry ``status`` (label) and ``status_value`` (raw), so the
# badge colours can be computed client-side without a second data field.
_BADGE = (
    '''<q-badge :color="props.row.status_value === 'available' ? 'positive'
                     : props.row.status_value === 'checked_out' ? 'warning' : 'grey'">
        {{ props.value }}
    </q-badge>'''
)

STATUS_BADGE_SLOT = f'<q-td :props="props">{_BADGE}</q-td>'


# --- Action buttons (single q-btn each; emit an event the page handles) -----

CHECKOUT_BTN = (
    '''<q-btn v-if="props.row.status_value === 'available'" dense flat round icon="logout" color="primary"
           @click="$parent.$emit('checkout', props.row)"><q-tooltip>Check out</q-tooltip></q-btn>'''
)

CHECKIN_BTN = (
    '''<q-btn v-if="props.row.status_value === 'checked_out'" dense flat round icon="login" color="secondary"
           @click="$parent.$emit('checkin', props.row)"><q-tooltip>Check in</q-tooltip></q-btn>'''
)

EDIT_BTN = (
    '''<q-btn dense flat round icon="edit" color="primary"
           @click="$parent.$emit('edit', props.row)"><q-tooltip>Edit</q-tooltip></q-btn>'''
)

DELETE_BTN = (
    '''<q-btn dense flat round icon="delete" color="negative"
           @click="$parent.$emit('remove', props.row)"><q-tooltip>Delete</q-tooltip></q-btn>'''
)


def view_btn(*, icon: str = 'open_in_new', tooltip: str = 'View asset') -> str:
    """The 'open asset page' button. Admin uses ``qr_code_2`` / 'Open asset page';
    home tables use ``open_in_new`` / 'View asset'."""
    return (
        f'''<q-btn dense flat round icon="{icon}" color="primary"
           @click="$parent.$emit('view', props.row)"><q-tooltip>{tooltip}</q-tooltip></q-btn>'''
    )


def actions_slot(*buttons: str) -> str:
    """Wrap action-button HTML in a ``body-cell-actions`` table slot. Falsy button
    strings (e.g. a role-gated button the user can't use) are dropped."""
    return '<q-td :props="props">' + ''.join(b for b in buttons if b) + '</q-td>'


# --- Mobile grid card (``item`` slot) ---------------------------------------

def grid_field_row(label: str, value_expr: str) -> str:
    """A label/value row for the mobile grid card. ``value_expr`` is raw cell
    HTML (typically ``{{ props.row.<field> }}``)."""
    return (
        '<div class="row items-center q-mb-xs">'
        f'<div class="col-4 text-grey-7">{label}:</div>'
        f'<div class="col-8">{value_expr}</div>'
        '</div>'
    )


GRID_STATUS_ROW = (
    '<div class="row items-center q-mb-xs">'
    '<div class="col-4 text-grey-7">Status:</div>'
    f'<div class="col-8">{_BADGE.replace("{{ props.value }}", "{{ props.row.status }}")}</div>'
    '</div>'
)


def grid_card(field_rows: Iterable[str], *buttons: str,
              actions_class: str = 'justify-end q-gutter-xs') -> str:
    """Assemble the mobile grid ``item`` card from field rows + action buttons."""
    fields = ''.join(field_rows)
    actions = ''.join(b for b in buttons if b)
    return (
        '<div class="q-pa-sm q-mb-sm equipment-grid-card" style="width: 100%; box-sizing: border-box;">'
        f'{fields}'
        f'<div class="row items-center {actions_class}">{actions}</div>'
        '</div>'
    )


# --- Row shaping ------------------------------------------------------------

def equipment_rows(assets, open_loans: Mapping, *, include_owner: bool = False,
                   community_name: str = '') -> list[dict]:
    """Build table row dicts from equipment assets + a
    ``{equipment_id: Loan}`` open-loan map. ``include_owner`` adds the owner
    column (admin table only); ``community_name`` is the owning community's name
    shown for un-owned assets (``TenantService.current_community_name()``)."""
    rows = []
    for a in assets:
        row = {
            'id': a.id,
            'asset_number': a.asset_number,
            'name': a.name,
            'status': status_label(a.status.value),
            'status_value': a.status.value,
            'holder': (
                open_loans[a.id].borrower.preferred_name
                if a.id in open_loans else '-'
            ),
        }
        if include_owner:
            row['owner'] = a.owner_label(community_name)
        rows.append(row)
    return rows


# --- Checkout / check-in handler wiring -------------------------------------

RefreshFn = Callable[[], Awaitable[None]]


def make_checkout_handler(refresh: RefreshFn, *, can_manage: bool):
    """Return the ``(row, client)`` checkout handler used behind the checkout
    event. Restores the captured client for background UI (NiceGUI rule)."""
    async def handle(row, client) -> None:
        with client:
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            await open_checkout(actor, row['id'], can_manage=can_manage, on_done=refresh)
    return handle


def make_checkin_handler(refresh: RefreshFn):
    """Return the ``(row, client)`` check-in handler used behind the checkin event."""
    async def handle(row, client) -> None:
        with client:
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            await quick_checkin(actor, row['id'], on_done=refresh)
    return handle


def wire_checkout_checkin(table, *, refresh: RefreshFn, can_manage: bool,
                          on_view: Optional[Callable] = None) -> None:
    """Wire checkout/checkin (and optional view) events on an equipment table.

    Captures ``context.client`` per NiceGUI's background-task rule. ``on_view``
    defaults to navigating to the asset detail page."""
    checkout = make_checkout_handler(refresh, can_manage=can_manage)
    checkin = make_checkin_handler(refresh)
    table.on('checkout', lambda e: background_tasks.create(checkout(e.args, context.client)))
    table.on('checkin', lambda e: background_tasks.create(checkin(e.args, context.client)))
    if on_view is None:
        table.on('view', lambda e: ui.navigate.to(f"/equipment/{e.args['id']}"))
    else:
        table.on('view', on_view)
