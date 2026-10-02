"""Admin Users Management Page"""

from datetime import datetime, timedelta, timezone

from nicegui import app, context, ui

from application.services import (
    AccommodationService,
    NotFoundError,
    TenantMembershipService,
    UserService,
    get_user_from_discord_id,
)
from application.services.tenant_service import TenantService
from application.tenant_context import require_tenant_id
from application.utils.timezone import format_local_datetime, format_local_display
from models import MembershipSource, Role, User
from pages.admin_tabs.admin_accommodations import render_accommodation_panel
from theme.accommodation_copy import STATUS_LABELS
from theme.dialog import AdminUserDialog
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.notify import notify_error
from theme.tables.admin_crud import refresh_button
from theme.tables.export import csv_export_button
from theme.tables.preferences import TableKeys, preferences_button, search_input
from theme.tables.user import UserTableView

_TA_FILTER = '_tournament_admin'
#: The Users-tab "Joined in the last N days" filter.
RECENT_JOIN_WINDOW = timedelta(days=7)

JOIN_SOURCE_LABELS: dict = {
    MembershipSource.STAFF: 'Added by staff',
    MembershipSource.JOIN_REQUEST: 'Join request',
    MembershipSource.DISCORD_AUTO_JOIN: 'Joined via Discord',
    MembershipSource.ROLE_GRANT: 'Role grant',
    MembershipSource.DISCORD_ROLE: 'Discord role sync',
    MembershipSource.IMPORT: 'SpeedGaming import',
}

_JOINED_VIA_SLOT = '''<q-td :props="props">
    <span v-if="props.row.joined_discord" class="wiz-chip wiz-chip--live" style="white-space: nowrap">
        <q-icon name="forum" size="xs" class="q-mr-xs" />{{ props.value }}
    </span>
    <span v-else-if="props.value">{{ props.value }}</span>
    <span v-else class="text-grey-7">-</span>
</q-td>'''
_CC_FILTER = '_crew_coordinator'

_ROW_ACTIONS = '''
    <q-btn dense flat color="negative" label="Remove"
           @click="$parent.$emit('remove_member', props.row)">
        <q-tooltip>Remove from this community</q-tooltip>
    </q-btn>
'''


async def _in_client(client, coro) -> None:
    """Await ``coro`` inside ``client``'s slot, for a handler run as a background task."""
    with client:
        await coro


async def admin_users_page(accommodations: bool = False, ada_request: int | None = None) -> None:
    """Members table, plus an ADA requests sub-tab when the community has the feature.

    ``ada_request`` is the staff DM's deep link: the ADA sub-tab opens on that
    request's dialog.
    """
    with ui.column().classes('page-container-narrow w-full'):
        with ui.row().classes('header-row'):
            ui.label('User Management').classes('page-title')

        ui.separator().classes('separator-spacing')

        if not accommodations:
            if ada_request is not None:
                # A DM link outlives the feature; say why it opens nothing.
                ui.notify(
                    'ADA requests aren’t turned on for this community, so that '
                    'link has nothing to open.', color='warning',
                )
            await _members_panel(accommodations=False)
            return

        actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        service = AccommodationService()

        # Counts what needs doing, not every open request: an arranged,
        # unchanged request is done, and a count that never reaches zero can't
        # tell staff whether anything is waiting.
        def tab_label(count: int) -> str:
            return f'ADA requests ({count})' if count else 'ADA requests'

        with ui.tabs().props('dense inline-label align=left no-caps').classes('w-full') as sub_tabs:
            members_tab = ui.tab('members', label='Members', icon='group')
            ada_tab = ui.tab('ada', label=tab_label(0), icon='accessible')
        ada_tab.tooltip('New, acknowledged, and changed-since-arranged requests')

        async def recount() -> None:
            try:
                ada_tab.props(f'label="{tab_label(await service.action_needed_count(actor))}"')
            except (ValueError, PermissionError):
                pass

        opener: dict = {}

        async def open_ada(request_id: int) -> None:
            sub_tabs.set_value(ada_tab)
            if opener.get('open'):
                await opener['open'](request_id)

        with ui.tab_panels(sub_tabs, value=members_tab).classes('w-full'):
            with ui.tab_panel(members_tab).classes('q-px-none'):
                await _members_panel(accommodations=True, actor=actor, on_open_ada=open_ada)
            with ui.tab_panel(ada_tab).classes('q-px-none'):
                opener['open'] = await render_accommodation_panel(on_change=recount)
        await recount()
        if ada_request is not None:
            await open_ada(ada_request)


async def _members_panel(
    accommodations: bool, actor: User | None = None, on_open_ada=None,
) -> None:
    with ui.column().classes('w-full gap-4'):
        ui.label(
            'Everyone in this community and the roles they hold. Identity is '
            'shared across communities; membership is not — Add Member brings an '
            'existing account in, Add User creates a brand-new one. Click a '
            'username to edit it; filter by role to narrow the list.'
        ).classes('text-caption text-grey')

        # Pending join requests, above the member table. The queue carries its
        # own buttons on purpose: discovery and action on different pages is the
        # mistake that makes a report nobody acts on.
        @ui.refreshable
        async def join_queue() -> None:
            service = TenantMembershipService()
            try:
                pending = await service.list_pending()
            except (ValueError, PermissionError):
                return
            if not pending:
                return
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))

            async def decide(request_id: int, approve: bool) -> None:
                try:
                    if approve:
                        await service.approve_request(actor, request_id)
                    else:
                        await service.deny_request(actor, request_id)
                except (ValueError, PermissionError, NotFoundError) as e:
                    ui.notify(str(e), color='warning')
                    return
                ui.notify('Approved.' if approve else 'Declined.', color='positive')

                # Through the view's _bg: refreshing the queue deletes the button
                # whose handler this is, and the task that outlives it has lost
                # the tenant unless it's rebound.
                async def after_decision() -> None:
                    await join_queue.refresh()
                    await table_view.refresh()
                table_view._bg(after_decision())

            with ui.card().classes('w-full'):
                ui.label(f'{len(pending)} pending join request'
                         f"{'s' if len(pending) != 1 else ''}").classes('text-bold')
                for request in pending:
                    person = request.user
                    # Wraps on a phone: beside the two buttons the name and the
                    # message were squeezed to a word a line.
                    with ui.row().classes('items-start justify-between w-full gap-2'):
                        with ui.column().classes('gap-0').style('flex: 1 1 12rem; min-width: 0'):
                            ui.label(person.display_name or person.username) \
                                .style('overflow-wrap: anywhere')
                            ui.label(f'Asked {format_local_display(request.updated_at)}') \
                                .classes('text-caption text-grey')
                            if request.message:
                                # Plain text, never markup — the requester writes it.
                                ui.label(request.message).classes('text-caption text-grey')
                        with ui.row().classes('no-wrap gap-1'):
                            ui.button(
                                'Approve', icon='check',
                                on_click=lambda _=None, r=request.id: decide(r, True),
                            ).props('flat dense color=positive')
                            ui.button(
                                'Decline', icon='close',
                                on_click=lambda _=None, r=request.id: decide(r, False),
                            ).props('flat dense color=negative')

        await join_queue()

        selected = {'value': []}
        ada_only = {'value': False}
        recent_only = {'value': False}
        ada_ids: set[int] = set()
        ada_requests: dict = {}
        memberships: dict = {}
        recent_ids: set[int] = set()

        async def load_row_data() -> None:
            fresh_members = await TenantMembershipService().memberships_by_user()
            memberships.clear()
            memberships.update(fresh_members)
            cutoff = datetime.now(timezone.utc) - RECENT_JOIN_WINDOW
            recent_ids.clear()
            recent_ids.update(
                uid for uid, m in fresh_members.items()
                if m.created_at and m.created_at >= cutoff
            )
            if not accommodations:
                return
            try:
                fresh = await AccommodationService().open_requests_by_user(actor)
            except (ValueError, PermissionError):
                fresh = {}
            ada_requests.clear()
            ada_requests.update(fresh)
            ada_ids.clear()
            ada_ids.update(fresh)

        def decorate(row: dict) -> None:
            membership = memberships.get(row['id'])
            row['joined'] = format_local_datetime(membership.created_at) if membership else ''
            source = membership.source if membership else None
            row['joined_via'] = JOIN_SOURCE_LABELS.get(source, '') if source else ''
            row['joined_discord'] = source is MembershipSource.DISCORD_AUTO_JOIN
            if accommodations:
                mark_ada(row)

        # The request's own status, so New and Arranged don't read the same.
        def mark_ada(row: dict) -> None:
            request = ada_requests.get(row['id'])
            if request is None:
                row['ada'] = ''
                return
            row['ada'] = STATUS_LABELS[request.status] + (
                ', changed' if request.changed_since_arranged else ''
            )
            row['ada_request_id'] = request.id

        columns: list[dict] = [
            {'name': 'username', 'label': 'Username', 'field': 'username', 'sortable': True},
            {'name': 'preferred_name', 'label': 'Display Name', 'field': 'preferred_name',
             'sortable': True},
            {'name': 'pronouns', 'label': 'Pronouns', 'field': 'pronouns', 'sortable': True},
            {'name': 'challonge', 'label': 'Challonge', 'field': 'challonge', 'sortable': True},
            *([{'name': 'ada', 'label': 'ADA', 'field': 'ada', 'sortable': True}]
              if accommodations else []),
            # Not sortable: a comma-joined list of role labels sorts on the
            # string, which orders by whoever happens to hold 'Commentator'.
            {'name': 'roles', 'label': 'Roles', 'field': 'roles'},
            # When and how they got in: Discord auto-join tells nobody, so this
            # is where staff see it.
            {'name': 'joined', 'label': 'Joined', 'field': 'joined', 'sortable': True},
            {'name': 'joined_via', 'label': 'Via', 'field': 'joined_via', 'sortable': True},
            {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
        ]

        def get_query():
            # Members of this community, not every account on the platform.
            # UserTableView wants a queryset rather than a coroutine, so this
            # hand-scopes; UserService.get_community_people is the canonical
            # version and every other caller uses it.
            sel_list = selected.get('value') or []
            tid = require_tenant_id()
            qs = User.filter(tenant_memberships__tenant_id=tid).exclude(is_system=True)
            if ada_only['value']:
                qs = qs.filter(id__in=list(ada_ids))
            if recent_only['value']:
                qs = qs.filter(id__in=list(recent_ids))
            if not sel_list:
                return qs.distinct()
            global_roles = [v for v in sel_list if v in {r.value for r in Role}]
            if global_roles:
                qs = qs.filter(roles__role__in=global_roles, roles__tenant_id=tid)
            if _TA_FILTER in sel_list:
                qs = qs.filter(admin_tournaments__tenant_id=tid)
            if _CC_FILTER in sel_list:
                qs = qs.filter(crew_coordinated_tournaments__tenant_id=tid)
            return qs.distinct()

        async def add_user():
            async def after_submit(_):
                await table_view.refresh()
            dialog = AdminUserDialog(on_submit=after_submit)
            await dialog.open()

        async def add_member():
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            candidates = await TenantMembershipService().addable_users()

            with ui.dialog() as dialog, ui.card().classes('w-96 gap-2'):
                ui.label('Add a member').classes('text-lg font-semibold')
                ui.label(
                    'Bring an existing account into this community. Their profile '
                    'is shared across communities; only the membership is added '
                    'here.'
                ).classes('text-caption text-grey')
                if not candidates:
                    ui.label('Every account is already a member.').classes('text-caption')
                select = ui.select(
                    options={u.id: (u.display_name or u.username) for u in candidates},
                    label='Account', with_input=True,
                ).classes('w-full')

                async def submit():
                    if not select.value:
                        ui.notify('Choose an account first', color='warning')
                        return
                    user = await UserService().get_user_by_id(select.value)
                    if user is None:
                        ui.notify('That account no longer exists', color='negative')
                        return
                    try:
                        await TenantMembershipService().add_member(actor, user)
                    except (ValueError, PermissionError) as e:
                        ui.notify(str(e), color='warning')
                        return
                    ui.notify(f'{user.display_name or user.username} is now a member',
                              color='positive')
                    dialog.close()
                    await table_view.refresh()

                with ui.row().classes('w-full justify-end'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')
                    ui.button('Add', on_click=submit, color='primary')
            dialog.open()

        community = await TenantService.current_community_name()

        async def remove_member(row, client) -> None:
            with client:
                user = await UserService().get_user_by_id(row['id'])
                if user is None:
                    ui.notify('That account no longer exists', color='negative')
                    return
                name = user.display_name or user.username
                # With auto-join on, being in the Discord server is the rule:
                # removal only lasts until they next open the community.
                auto_join = await TenantMembershipService.auto_join_active(require_tenant_id())
                consequence = (
                    'They get a Discord message saying so. This community lets '
                    'members of its Discord server in automatically, so while '
                    'they\'re in the server they\'ll be let back in the next time '
                    'they open it. Remove them from the server too if you want '
                    'them out.'
                    if auto_join else
                    'They lose access straight away and get a Discord message '
                    'saying so. You can add them back later.'
                )

                async def confirmed() -> None:
                    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                    try:
                        await TenantMembershipService().remove_member(actor, user)
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                        return
                    ui.notify(f'{name} removed from this community', color='positive')
                    await table_view.refresh()

                ConfirmationDialog(
                    title=f'Remove {name} from {community}?',
                    message=(
                        f'{consequence}\n\nAn open ADA request of theirs is '
                        'withdrawn and its details cleared.'
                    ),
                    confirm_text='Remove',
                    on_confirm=lambda: table_view._bg(_in_client(client, confirmed())),
                ).open()

        # Toolbar row — rendered before filter and table for correct visual order
        with ui.row().classes('full-width'):
            ui.button('Add Member', icon='person_add', on_click=add_member).props('color=primary')
            ui.button('Add User', icon='add', on_click=add_user).props('flat color=primary')
            ui.space()
            # Placeholder filled after the table exists — the toolbar is built
            # first for visual order, and the gear needs a live table to read.
            gear_slot = ui.row().classes('items-center')
            # Lambda, not a direct reference: the toolbar is built before
            # table_view exists.
            refresh_button(lambda: table_view.refresh())

        # Below 1024px the CSS collapses .match-filters-card until it carries
        # .wiz-filters-open, so phones need this toggle (hidden on desktop) or
        # the filters are unreachable — the match board's pattern.
        filters_open = {'value': False}

        def toggle_filters() -> None:
            filters_open['value'] = not filters_open['value']
            if filters_open['value']:
                filters_card.classes(add='wiz-filters-open')
            else:
                filters_card.classes(remove='wiz-filters-open')

        def update_filter_badge() -> None:
            count = (
                len(selected.get('value') or [])
                + (1 if ada_only['value'] else 0)
                + (1 if recent_only['value'] else 0)
            )
            filter_badge.set_text(str(count))
            filter_badge.set_visibility(count > 0)

        with ui.row().classes('wiz-filter-toggle full-width items-center'):
            ui.button('Filters', icon='filter_list', on_click=toggle_filters).props('flat color=primary')
            filter_badge = ui.badge('0').props('color=primary')
            filter_badge.set_visibility(False)

        # Filter card — between toolbar and table, matching match-filters-card pattern
        with ui.card().classes('match-filters-card') as filters_card:
            with ui.row().classes('match-filter-row'):
                with ui.column().classes('match-filter-column'):
                    ui.label('Filter by Role').classes('match-filter-label')
                    role_options = {r.value: r.name.replace('_', ' ').title() for r in Role}
                    role_options[_TA_FILTER] = 'Tournament Admin'
                    role_options[_CC_FILTER] = 'Crew Coordinator'
                    role_select = (
                        ui.select(options=role_options, value=[], multiple=True, label='Roles')
                        .props('outlined dense use-chips clearable')
                    )
                    role_select.bind_value(selected, 'value')
                with ui.column().classes('match-filter-column'):
                    ui.label('Recently joined').classes('match-filter-label')
                    recent_checkbox = ui.checkbox(
                        f'Joined in the last {RECENT_JOIN_WINDOW.days} days',
                    ).bind_value(recent_only, 'value')
                if accommodations:
                    with ui.column().classes('match-filter-column'):
                        ui.label('Accessibility').classes('match-filter-label')
                        ada_checkbox = ui.checkbox(
                            'Needs ADA accommodation',
                        ).bind_value(ada_only, 'value')

        # Table — toolbar suppressed since we rendered it above
        table_view = UserTableView(
            columns=columns, get_query=get_query, show_toolbar=False,
            row_actions=_ROW_ACTIONS, table_key=TableKeys.ADMIN_USERS,
            before_refresh=load_row_data,
            decorate_row=decorate,
            extra_slots={'body-cell-joined_via': _JOINED_VIA_SLOT},
            empty_message=(
                'Nobody is a member of this community yet. Add Member brings an '
                'existing account in; granting someone a role makes them a member too.'
            ),
        )
        table_view.table.on(
            'remove_member',
            lambda e: table_view._bg(remove_member(e.args, context.client)),
        )
        if on_open_ada is not None:
            async def open_ada(e) -> None:
                row = e.args.get('row', e.args) if isinstance(e.args, dict) else {}
                if row.get('ada_request_id'):
                    await on_open_ada(row['ada_request_id'])
            table_view.table.on('open_ada', open_ada)
        with gear_slot:
            search_input(table_view.table, placeholder='Search people…')
            # The plan's columns, not the shipped list: the export matches what
            # the person is looking at, hidden columns and all.
            csv_export_button(
                'community-people',
                lambda: table_view._plan.columns if table_view._plan else columns,
                lambda: table_view.table.rows,
            )
            preferences_button(table_view.table)

        # Same rebind as the tab-switch below: an 'update:model-value' handler
        # is a client event, so a bare background task loses the tenant.
        role_select.on('update:model-value', lambda *_: table_view._bg(table_view.refresh()))
        role_select.on_value_change(lambda _: update_filter_badge())
        recent_checkbox.on('update:model-value', lambda *_: table_view._bg(table_view.refresh()))
        recent_checkbox.on_value_change(lambda _: update_filter_badge())
        if accommodations:
            ada_checkbox.on('update:model-value', lambda *_: table_view._bg(table_view.refresh()))
            ada_checkbox.on_value_change(lambda _: update_filter_badge())

        # Route through the view's _bg so refresh rebinds the tenant captured at
        # build — the selected_tab handler runs detached, and _format_user_row
        # relies on that tenant to keep the roles column scoped.
        def on_tab_selected():
            table_view._bg(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Users' else None)
