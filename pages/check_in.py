"""The event check-in desk — the page volunteers work from on their phones.

``/checkin`` lists the open check-in events (and goes straight to the one when
there is only one); ``/checkin/{event_id}`` is the desk itself: a search box
pinned to the top, filter chips with counts (one per badge type too), and one
card per person showing the badges they bought and a full-width Check in button.

Built phone-first. Below ``md`` the roster is a card grid; on a desktop it is a
table with the same actions. Search filters in the browser (Quasar's
``filter-method``), so typing a name is instant even on slow venue wifi.

Every desk open on the same event stays in step: the service publishes on
:mod:`application.events.check_in_live` and each desk re-reads its roster,
flashing the card that changed. A desk also re-reads after its socket comes back
from a blip, so a phone that was locked doesn't show stale check-ins.

Presentation only — :class:`CheckInService` decides who may do what. The page
hides what a viewer can't use (walk-ups and removal are staff-only) so nobody
taps a button the service will refuse.
"""

from typing import Dict, List, Optional

from nicegui import app, background_tasks, context, ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from application.events import check_in_live
from application.services import AuthService, CheckInService, TenantService, get_user_from_discord_id
from application.services.check_in_rules import (
    DESK_FILTERS,
    LANYARD_LABELS,
    LANYARDS,
    active_badges,
    comp_label,
    entrant_filters,
    lanyard_for,
)
from application.table_preferences_context import table_prefs_scope
from application.tenant_context import tenant_scope
from application.timezone_context import tz_scope
from application.utils.timezone import format_local_display, format_local_time
from middleware.auth import protected_page
from models import (
    CheckInEntrant,
    CheckInEntrantSource,
    CheckInEvent,
    CheckInEventStatus,
    CheckInLinkMethod,
    FeatureFlag,
    Role,
)
from theme.base import BaseLayout
from theme.connection import REQUIRES_SOCKET_CLASS
from theme.dialog import ConfirmationDialog
from theme.dialog.check_in_dialogs import open_link_dialog, open_walk_up_dialog
from theme.notify import notify_error
from theme.realtime import refresh_on_reconnect, register_view
from theme.tables.admin_crud import capture_render_context
from theme.tables.export import csv_export_button
from theme.tables.preferences import TableKeys, customize_table, search_input
from theme.timer_teardown import PageTimer

DESK_ROLES = [Role.STAFF, Role.CHECK_IN_DESK]

_LINK_LABELS = {
    'matcherino_id': 'seen before',
    'discord_id': 'via Discord',
    'twitch_id': 'via Twitch',
    'matcherino_handle': 'via profile handle',
    'manual': 'linked by staff',
    'walk_up': 'walk-up',
    'comp': 'comped',
}

_FILTER_LABELS = {
    'all': 'All',
    'not_yet': 'Not yet',
    'checked_in': 'Checked in',
    'comped': 'Comped',
    'walk_up': 'Walk-ups',
}
FILTERS = {key: _FILTER_LABELS[key] for key in DESK_FILTERS}

# One colour per lanyard, matching nothing else on the desk so it reads at a glance.
_LANYARD_COLORS = {
    'staff': 'red-8', 'volunteer': 'purple-7', 'vip': 'amber-8', 'base': 'blue-7', 'day_pass': 'teal-7',
}


# Desktop columns. The mobile card below is bespoke and does not read these.
_COLUMNS: list[dict] = [
    {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
    {'name': 'lanyard', 'label': 'Lanyard', 'field': 'lanyard_rank', 'align': 'left', 'sortable': True},
    {'name': 'account', 'label': 'Wizzrobe account', 'field': 'account', 'align': 'left', 'sortable': True},
    {'name': 'status', 'label': 'Status', 'field': 'status_label', 'align': 'left', 'sortable': True},
    {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
]

# The whole roster export, not just the filtered view.
_EXPORT_COLUMNS: list[dict] = [
    {'name': 'name', 'label': 'Name', 'field': 'name'},
    {'name': 'matcherino_id', 'label': 'Matcherino ID', 'field': 'matcherino_id'},
    {'name': 'lanyard', 'label': 'Lanyard', 'field': 'lanyard_label'},
    {'name': 'badges', 'label': 'Badges', 'field': 'badges_text'},
    {'name': 'codes', 'label': 'Badge codes', 'field': 'codes_text'},
    {'name': 'account', 'label': 'Wizzrobe account', 'field': 'account'},
    {'name': 'linked_via', 'label': 'Linked via', 'field': 'linked_via'},
    {'name': 'source', 'label': 'Source', 'field': 'source'},
    {'name': 'volunteer', 'label': 'Volunteer', 'field': 'volunteer_text'},
    {'name': 'comp', 'label': 'Comp', 'field': 'comp_text'},
    {'name': 'registered', 'label': 'Bought', 'field': 'registered'},
    {'name': 'status', 'label': 'Status', 'field': 'status_label'},
    {'name': 'checked_in', 'label': 'Checked in at', 'field': 'checked_in_when'},
    {'name': 'checked_in_by', 'label': 'Checked in by', 'field': 'checked_in_by'},
]

_FILTER_METHOD = (
    "(rows, terms) => { const t = String(terms || '').toLowerCase().trim();"
    " return t ? rows.filter(r => r.search.includes(t)) : rows; }"
)

_STATUS_BADGES = '''
    <q-badge v-if="props.row.checked_in" color="positive" class="q-mr-xs">
        <q-icon name="check" size="14px" class="q-mr-xs"/>{{ props.row.checked_in_label }}
    </q-badge>
    <q-badge v-if="props.row.withdrawn" :color="props.row.refunded ? 'negative' : 'grey-7'" class="q-mr-xs">
        {{ props.row.withdrawn_label }}</q-badge>
    <q-badge v-if="props.row.walk_up" color="info" class="q-mr-xs">Walk-up</q-badge>
'''

_MENU = f'''
    <q-btn flat round dense icon="more_vert" class="{REQUIRES_SOCKET_CLASS}" aria-label="More actions">
        <q-menu auto-close>
            <q-list style="min-width: 200px">
                <q-item v-if="!props.row.comp_only" clickable @click="$parent.$emit('link', props.row)">
                    <q-item-section avatar><q-icon name="link"/></q-item-section>
                    <q-item-section>{{{{ props.row.account ? 'Change linked account' : 'Link an account' }}}}</q-item-section>
                </q-item>
                <q-item v-if="props.row.account && !props.row.comp_only" clickable
                        @click="$parent.$emit('unlink', props.row)">
                    <q-item-section avatar><q-icon name="link_off"/></q-item-section>
                    <q-item-section>Unlink account</q-item-section>
                </q-item>
                <q-item v-if="props.row.checked_in" clickable @click="$parent.$emit('undo', props.row)">
                    <q-item-section avatar><q-icon name="undo"/></q-item-section>
                    <q-item-section>Undo check-in</q-item-section>
                </q-item>
                <q-item v-if="props.row.can_remove" clickable @click="$parent.$emit('remove', props.row)">
                    <q-item-section avatar><q-icon name="delete" color="negative"/></q-item-section>
                    <q-item-section>Remove walk-up</q-item-section>
                </q-item>
            </q-list>
        </q-menu>
    </q-btn>
'''

_CHECK_IN_BUTTON = f'''
    <q-btn v-if="!props.row.checked_in" unelevated no-caps color="primary" icon="how_to_reg"
           label="Check in" class="{REQUIRES_SOCKET_CLASS} checkin-btn"
           @click="$parent.$emit('checkin', props.row)" />
'''

_STATUS_CELL = f'''<q-td :props="props">
    <span v-if="!props.row.checked_in && !props.row.withdrawn" class="text-grey-7">Not yet</span>
    {_STATUS_BADGES}
</q-td>'''

_ACTIONS_CELL = f'''<q-td :props="props" class="q-gutter-xs">
    {_CHECK_IN_BUTTON}
    {_MENU}
</q-td>'''

# The lanyard is what the desk hands over, so it is the one loud thing on the
# row. A buyer holding more than one badge (often one for a friend) gets a note,
# since the extra badge needs its own lanyard.
_LANYARD_CHIP = '''
    <q-chip v-if="props.row.lanyard" square :color="props.row.lanyard_color" text-color="white"
            icon="badge" class="q-ml-none text-weight-bold checkin-lanyard">{{ props.row.lanyard_label }}</q-chip>
    <span v-if="props.row.extra_badges" class="text-caption text-weight-medium text-warning">
        + {{ props.row.extra_badges }}</span>
'''

_LANYARD_CELL = f'''<q-td :props="props">
    {_LANYARD_CHIP}
    <span v-if="!props.row.lanyard" class="text-grey-7">—</span>
</q-td>'''

_ACCOUNT_CELL = '''<q-td :props="props">
    <span v-if="props.row.account">{{ props.row.account }}</span>
    <span v-else class="text-warning">Not linked</span>
</q-td>'''

# Phone card: name and account up top, the state as badges, one thumb-sized
# Check in button across the bottom. Link/Unlink/Undo/Remove sit behind the ⋮
# menu so none of them is a stray tap away from the primary action.
_GRID_CARD = f'''<div class="q-pa-xs col-12">
<div class="checkin-grid-card q-pa-sm" :class="[props.row.checked_in ? 'checkin-grid-card--in' : '',
                                             props.row._flash ? 'wiz-row-flash' : '']">
    <div class="row no-wrap items-center q-gutter-sm">
        <q-avatar size="40px" color="grey-4" text-color="grey-9">
            <img v-if="props.row.avatar" :src="props.row.avatar" referrerpolicy="no-referrer">
            <span v-else>{{{{ props.row.initial }}}}</span>
        </q-avatar>
        <div class="col" style="min-width: 0">
            <div class="text-subtitle1 text-weight-medium ellipsis">{{{{ props.row.name }}}}</div>
            <div v-if="props.row.account" class="text-caption text-grey-7 ellipsis">
                {{{{ props.row.account }}}} · {{{{ props.row.linked_via }}}}
            </div>
            <div v-else class="text-caption text-warning">Not linked to an account</div>
            <div v-if="props.row.lanyard" class="q-mt-xs">{_LANYARD_CHIP}</div>
            <div class="q-mt-xs">{_STATUS_BADGES}</div>
        </div>
        {_MENU}
    </div>
    <q-btn v-if="!props.row.checked_in" unelevated no-caps color="primary" icon="how_to_reg"
           label="Check in" size="lg" class="full-width q-mt-sm {REQUIRES_SOCKET_CLASS} checkin-btn"
           @click="$parent.$emit('checkin', props.row)" />
</div>
</div>'''


def _row(entrant: CheckInEntrant, can_manage: bool, volunteers: set[int]) -> Dict:
    user = entrant.user
    checked_by = entrant.checked_in_by
    account = user.preferred_name if user else ''
    checked_in = entrant.checked_in_at is not None
    withdrawn = entrant.withdrawn_at is not None
    walk_up = entrant.source == CheckInEntrantSource.WALK_UP
    comp_only = entrant.source == CheckInEntrantSource.COMP
    comp_text = ', '.join(comp_label(reason) for reason in entrant.comp_reasons or [])
    volunteer = entrant.user_id is not None and entrant.user_id in volunteers
    all_badges = list(entrant.passes)
    held = active_badges(all_badges)
    lanyard = lanyard_for(entrant, held, volunteer)
    lanyard_label = LANYARD_LABELS[lanyard] if lanyard else ''
    # A second badge is someone else's (usually a friend the venue doesn't
    # name): list every badge after the highest, which is taken as their own.
    badge_lanyards = sorted((b.tier.lanyard.value for b in held), key=LANYARDS.index)
    extra_badges = ', '.join(f'{LANYARD_LABELS[value]} badge' for value in badge_lanyards[1:])
    refunded = not held and any(b.refunded_at is not None for b in all_badges)
    if comp_only:
        withdrawn_label = 'No longer comped'
    else:
        withdrawn_label = 'Refunded' if refunded else 'No badge'
    if checked_in:
        status_label = 'Checked in'
    elif withdrawn:
        status_label = withdrawn_label
    else:
        status_label = 'Not yet'
    checked_in_label = ''
    if checked_in:
        checked_in_label = format_local_time(entrant.checked_in_at)
        if checked_by is not None:
            checked_in_label += f' by {checked_by.preferred_name}'
    badges = [{'title': b.tier.title, 'code': b.code} for b in held]
    search = ' '.join(filter(None, [
        entrant.display_name, account, user.username if user else '',
        user.twitch_username if user else '', *(b.code for b in held),
    ])).lower()
    return {
        'id': entrant.id,
        'name': entrant.display_name,
        'initial': (entrant.display_name[:1] or '?').upper(),
        'avatar': entrant.avatar_url or '',
        'account': account,
        'linked_via': _LINK_LABELS.get(entrant.link_method.value, '') if entrant.link_method and user else '',
        'source': 'Walk-up' if walk_up else 'Comp' if comp_only else 'Matcherino',
        'comp_text': comp_text,
        'comp_only': comp_only,
        'matcherino_id': entrant.matcherino_user_id or '',
        'lanyard': lanyard or '',
        'lanyard_label': lanyard_label,
        'lanyard_color': _LANYARD_COLORS.get(lanyard or '', 'grey-7'),
        'lanyard_rank': LANYARDS.index(lanyard) if lanyard else len(LANYARDS),
        'extra_badges': extra_badges,
        'badges_text': ', '.join(
            ([f'Comp ({comp_text})'] if comp_text else []) + [b['title'] for b in badges]
        ),
        'codes_text': ', '.join(b['code'] for b in badges),
        'registered': format_local_display(entrant.registered_at) if entrant.registered_at else '',
        'status_label': status_label,
        'checked_in': checked_in,
        'checked_in_label': checked_in_label,
        'checked_in_when': format_local_display(entrant.checked_in_at) if checked_in else '',
        'checked_in_by': checked_by.preferred_name if checked_by else '',
        'withdrawn': withdrawn,
        'withdrawn_label': withdrawn_label,
        'refunded': refunded,
        'walk_up': walk_up,
        'volunteer_text': 'Yes' if volunteer else '',
        'unlinked': user is None,
        # A buyer with no account gets asked for one at check-in. Named walk-ups
        # and rows staff unlinked on purpose were left unlinked deliberately.
        'prompt_link': (
            user is None and entrant.source == CheckInEntrantSource.MATCHERINO
            and entrant.link_method != CheckInLinkMethod.MANUAL
        ),
        'can_remove': walk_up and can_manage,
        'search': search,
        # Everyone is under All, withdrawn rows too, so a search still finds
        # someone whose badge was refunded (and says so).
        'filters': sorted((entrant_filters(entrant) & set(DESK_FILTERS)) | {'all'}),
        '_flash': False,
    }


def _matches(row: Dict, key: str) -> bool:
    return key in row['filters']


def _can_sync(event: CheckInEvent) -> bool:
    return event.matcherino_venue_id is not None or bool(event.comp_roles) or event.comp_volunteers


def _sync_line(event: CheckInEvent) -> tuple[str, str]:
    """The desk's one-line sync status, and the class to show it in."""
    comps = bool(event.comp_roles) or event.comp_volunteers
    if event.matcherino_venue_id is None and not comps:
        return 'Walk-ups only: no Matcherino venue linked.', 'text-grey-7'
    if event.matcherino_venue_id is None:
        if event.last_synced_at is None:
            return 'Comps only: not synced yet.', 'text-grey-7'
        return f'Comps only · updated at {format_local_time(event.last_synced_at)}', 'text-grey-7'
    if event.last_sync_error:
        when = format_local_time(event.updated_at) if event.updated_at else ''
        return (
            f"Couldn't reach Matcherino at {when}, so the roster may be out of date. "
            f'{event.last_sync_error}', 'text-warning',
        )
    if event.last_synced_at is None:
        return 'Not synced with Matcherino yet.', 'text-grey-7'
    return (
        f'Synced with Matcherino at {format_local_time(event.last_synced_at)} · '
        f'{event.last_sync_count or 0} with badges', 'text-grey-7',
    )


async def _desk_page_frame(title_suffix: str):
    community = await TenantService.current_community_name() or 'Wizzrobe'
    ui.page_title(f'{community} — {title_suffix}')
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    await BaseLayout(user=user, show_admin=await AuthService.can_view_admin(user)).render()
    return user


def create() -> None:
    @protected_page('/checkin', roles=DESK_ROLES, feature=FeatureFlag.EVENT_CHECK_IN)
    async def check_in_index(request: Request):
        service = CheckInService()
        open_events = await service.list_open_events()
        if len(open_events) == 1:
            root_path = request.scope.get('root_path', '') or ''
            return RedirectResponse(f'{root_path}/checkin/{open_events[0].id}')

        user = await _desk_page_frame('Check-in')
        with ui.column().classes('page-container-narrow w-full q-pa-md gap-3'):
            ui.label('Check-in').classes('page-title')
            if not open_events:
                ui.label('No event is open for check-in right now.').classes('text-body1')
                if await AuthService.can_manage_check_in(user):
                    ui.label('Open one from Admin → Check-in.').classes('text-caption text-grey-7')
                return
            ui.label('Pick the event you are checking people in for.').classes('text-caption text-grey-7')
            for event in open_events:
                ui.button(event.name, icon='how_to_reg',
                          on_click=lambda _, e=event: ui.navigate.to(f'/checkin/{e.id}')) \
                    .props('unelevated no-caps color=primary size=lg align=left').classes('w-full')

    @protected_page('/checkin/{event_id}', roles=DESK_ROLES, feature=FeatureFlag.EVENT_CHECK_IN)
    async def check_in_desk(event_id: int):
        user = await _desk_page_frame('Check-in desk')
        service = CheckInService()
        event = await service.get_event(event_id)
        if event is None:
            with ui.column().classes('page-container-narrow w-full q-pa-md gap-2'):
                ui.label("That check-in event doesn't exist any more.").classes('text-body1')
                ui.button('See open events', on_click=lambda: ui.navigate.to('/checkin')) \
                    .props('flat no-caps color=primary')
            return
        await _render_desk(service, user, event)


async def _render_desk(service: CheckInService, user, event: CheckInEvent) -> None:
    can_manage = await AuthService.can_manage_check_in(user)
    render_context = capture_render_context()
    client = context.client
    state: Dict = {'event': event, 'rows': [], 'filter': 'all', 'flash': set()}

    with ui.column().classes('page-container-narrow w-full gap-2 q-px-sm'):
        with ui.column().classes('checkin-toolbar w-full gap-1 q-py-sm'):
            with ui.row().classes('w-full items-center no-wrap gap-2'):
                title = ui.label(event.name).classes('text-h6 ellipsis col')
                sync_btn = ui.button(icon='sync').props('flat round color=primary') \
                    .classes(REQUIRES_SOCKET_CLASS).tooltip('Sync badges and comps now')
                if not _can_sync(event):
                    sync_btn.set_visibility(False)
            closed_notice = ui.label('This event is closed. You can still record late check-ins.') \
                .classes('text-caption text-warning')
            box_slot = ui.row().classes('w-full')
            with ui.row().classes('w-full items-center no-wrap gap-2'):
                progress = ui.linear_progress(value=0, show_value=False, size='8px').classes('col') \
                    .props('rounded color=positive')
                counts_label = ui.label().classes('text-caption text-weight-medium')
            # The app's segmented control (.wiz-segmented, as on the Event page).
            chips = ui.toggle(FILTERS, value='all').props('no-caps dense unelevated') \
                .classes('wiz-segmented checkin-filters')
            sync_label = ui.label().classes('text-caption')

        table = ui.table(columns=_COLUMNS, rows=[], row_key='id', pagination=0) \
            .classes('w-full checkin-table').props(':grid="Quasar.Screen.lt.md" flat hide-pagination')
        table._props[':filter-method'] = _FILTER_METHOD
        table.add_slot('body-cell-status', _STATUS_CELL)
        table.add_slot('body-cell-lanyard', _LANYARD_CELL)
        table.add_slot('body-cell-account', _ACCOUNT_CELL)
        table.add_slot('body-cell-actions', _ACTIONS_CELL)
        table.add_slot('item', _GRID_CARD)
        table.add_slot('no-data', '''<div class="full-width text-center text-grey-7 q-pa-lg">
            {{ props.filter ? 'Nobody matches that search.' : 'Nobody here yet.' }}</div>''')
        # After the card slot, never before: the card must not follow a saved layout.
        customize_table(table, _COLUMNS, key=TableKeys.CHECK_IN_DESK, page_size=0)
        with box_slot:
            box = search_input(table, placeholder='Search by name or badge code', width='w-full')
            box.props('autofocus outlined').classes('col')

        # Bottom padding so the last card scrolls clear of the walk-up button.
        with ui.row().classes('w-full items-center gap-2 q-mt-sm checkin-footer'):
            csv_export_button('check-in', lambda: _EXPORT_COLUMNS, lambda: state['rows'], label='Export CSV')

        if can_manage:
            ui.button(icon='person_add', on_click=lambda: background_tasks.create(add_walk_up())) \
                .props('fab color=primary').classes(f'checkin-fab {REQUIRES_SOCKET_CLASS}') \
                .tooltip('Add walk-up')

        undo_bar = ui.row().classes('checkin-undo items-center no-wrap gap-2 q-pa-sm')
        undo_bar.set_visibility(False)

    def paint() -> None:
        current = state['event']
        rows = state['rows']
        counts = {key: sum(1 for r in rows if _matches(r, key)) for key in FILTERS}
        chips.options = {key: f'{label} {counts[key]}' for key, label in FILTERS.items()}
        chips.update()
        visible = [dict(r, _flash=r['id'] in state['flash']) for r in rows if _matches(r, state['filter'])]
        table.rows = visible
        table.update()
        # Withdrawn rows are listed under All but aren't expected at the door.
        total = counts['checked_in'] + counts['not_yet']
        progress.value = (counts['checked_in'] / total) if total else 0
        counts_label.text = f"{counts['checked_in']} of {total} checked in"
        text, cls = _sync_line(current)
        sync_label.text = text
        sync_label.classes(replace=f'text-caption {cls}')
        title.text = current.name
        closed_notice.set_visibility(current.status == CheckInEventStatus.CLOSED)
        sync_btn.set_visibility(_can_sync(current))

    async def reload(flash: Optional[int] = None) -> None:
        current = await service.get_event(state['event'].id)
        if current is None:
            ui.notify('This check-in event was deleted.', color='warning')
            ui.navigate.to('/checkin')
            return
        state['event'] = current
        volunteers = await service.volunteer_user_ids()
        state['rows'] = sorted(
            (_row(e, can_manage, volunteers) for e in await service.roster(current)),
            key=lambda r: r['name'].casefold(),
        )
        if flash is not None:
            state['flash'].add(flash)

            def clear() -> None:
                state['flash'].discard(flash)
                paint()
            PageTimer(1.6, clear, once=True)
        paint()

    def on_filter(e) -> None:
        state['filter'] = e.value or 'all'
        paint()

    chips.on_value_change(on_filter)

    def show_undo(entrant_id: int, name: str, lanyard: str, extra: str) -> None:
        undo_bar.clear()
        with undo_bar:
            with ui.column().classes('col gap-0'):
                ui.label(f'Checked in {name}').classes('ellipsis')
                if lanyard:
                    hand_over = f'Hand over: {lanyard} lanyard'
                    ui.label(f'{hand_over}, plus {extra}' if extra else hand_over) \
                        .classes('text-caption text-weight-bold ellipsis')

            async def undo() -> None:
                undo_bar.set_visibility(False)
                await run(service.undo_check_in(user, entrant_id), f'Undid check-in for {name}.')

            ui.button('Undo', on_click=undo).props('flat no-caps color=yellow-4') \
                .classes(REQUIRES_SOCKET_CLASS)
        undo_bar.set_visibility(True)
        PageTimer(8.0, lambda: undo_bar.set_visibility(False), once=True)

    async def run(coro, success: Optional[str] = None) -> bool:
        try:
            await coro
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return False
        if success:
            ui.notify(success, color='positive')
        await reload()
        return True

    async def check_in_entrant(entrant_id: int) -> None:
        try:
            outcome = await service.check_in(user, entrant_id)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        entrant = outcome.entrant
        await reload()
        if outcome.already:
            by = entrant.checked_in_by.preferred_name if entrant.checked_in_by else 'someone'
            ui.notify(
                f'{entrant.display_name} was already checked in by {by} at '
                f'{format_local_time(entrant.checked_in_at)}.',
                color='info',
            )
            return
        # Read the lanyard after the reload: linking just before can change it.
        row: Dict = next((r for r in state['rows'] if r['id'] == entrant.id), {})
        show_undo(entrant.id, entrant.display_name, row.get('lanyard_label', ''), row.get('extra_badges', ''))

    async def handle_checkin(row) -> None:
        if row.get('prompt_link'):
            entrant = await service.get_entrant(row['id'])
            if entrant is None:
                ui.notify('That person is no longer on the roster.', color='warning')
                await reload()
                return
            # Another desk may have linked or checked them in since this row was drawn.
            if entrant.user_id is None and entrant.checked_in_at is None:
                await open_link_dialog(
                    service, user, entrant, on_done=reload,
                    then_check_in=lambda: check_in_entrant(entrant.id),
                )
                return
        await check_in_entrant(row['id'])

    async def handle_link(row) -> None:
        entrant = await service.get_entrant(row['id'])
        if entrant is None:
            ui.notify('That person is no longer on the roster.', color='warning')
            await reload()
            return
        await open_link_dialog(service, user, entrant, on_done=reload)

    async def handle_unlink(row) -> None:
        await run(service.unlink(user, row['id']), f"Unlinked {row['name']}.")

    async def handle_undo(row) -> None:
        await run(service.undo_check_in(user, row['id']), f"Undid check-in for {row['name']}.")

    async def handle_remove(row) -> None:
        async def confirm() -> None:
            await run(service.remove_entrant(user, row['id']), f"Removed {row['name']}.")

        ConfirmationDialog(
            message=f"Remove walk-up {row['name']}? Their check-in goes with them.",
            on_confirm=confirm, confirm_text='Remove',
        ).open()

    async def add_walk_up() -> None:
        with client, tenant_scope(render_context[0]), tz_scope(render_context[1]), \
                table_prefs_scope(render_context[2]):
            await open_walk_up_dialog(service, user, state['event'], on_done=reload)

    async def sync_now() -> None:
        sync_btn.props('loading')
        try:
            result = await service.sync_event(user, state['event'].id)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            await reload()
            return
        finally:
            sync_btn.props(remove='loading')
        parts = [f'{result.total} with badges']
        if result.added:
            parts.append(f'{result.added} new')
        if result.comped:
            parts.append(f'{result.comped} comped')
        if result.withdrawn:
            parts.append(f'{result.withdrawn} withdrawn')
        if result.auto_linked:
            parts.append(f'{result.auto_linked} linked')
        ui.notify('Synced: ' + ', '.join(parts) + '.', color='positive')
        await reload()

    def bind(event_name: str, handler) -> None:
        async def run_in_context(args) -> None:
            with client, tenant_scope(render_context[0]), tz_scope(render_context[1]), \
                    table_prefs_scope(render_context[2]):
                await handler(args)
        table.on(event_name, lambda e: background_tasks.create(run_in_context(e.args)))

    bind('checkin', handle_checkin)
    bind('link', handle_link)
    bind('unlink', handle_unlink)
    bind('undo', handle_undo)
    bind('remove', handle_remove)
    sync_btn.on_click(sync_now)

    async def on_live_change(event_id: int, entrant_id: Optional[int], change_type: str) -> None:
        if event_id != state['event'].id:
            return
        with tenant_scope(render_context[0]), tz_scope(render_context[1]), \
                table_prefs_scope(render_context[2]):
            await reload(flash=entrant_id if change_type == check_in_live.CHANGED else None)

    register_view(on_live_change, channel=check_in_live)

    async def reread() -> None:
        with tenant_scope(render_context[0]), tz_scope(render_context[1]), \
                table_prefs_scope(render_context[2]):
            await reload()

    refresh_on_reconnect(reread)
    await reload()


__all__: List[str] = ['create']
