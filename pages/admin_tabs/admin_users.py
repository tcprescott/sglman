"""Admin Users Management Page"""


from nicegui import app, background_tasks, context, ui

from application.services import (
    NotFoundError,
    TenantMembershipService,
    UserService,
    get_user_from_discord_id,
)
from application.tenant_context import require_tenant_id
from models import Role, User
from theme.dialog import AdminUserDialog
from theme.tables.admin_crud import refresh_button
from theme.tables.user import UserTableView

_TA_FILTER = '_tournament_admin'
_CC_FILTER = '_crew_coordinator'

_ROW_ACTIONS = '''
    <q-btn dense flat color="negative" label="Remove"
           @click="$parent.$emit('remove_member', props.row)">
        <q-tooltip>Remove from this community</q-tooltip>
    </q-btn>
'''


async def admin_users_page() -> None:
    with ui.column().classes('page-container-narrow w-full'):
        with ui.row().classes('header-row'):
            ui.label('User Management').classes('page-title')

        ui.separator().classes('separator-spacing')

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
                join_queue.refresh()
                await table_view.refresh()

            with ui.card().classes('w-full'):
                ui.label(f'{len(pending)} pending join request'
                         f"{'s' if len(pending) != 1 else ''}").classes('text-bold')
                for request in pending:
                    person = request.user
                    with ui.row().classes('items-start justify-between no-wrap w-full gap-2'):
                        with ui.column().classes('gap-0'):
                            ui.label(person.display_name or person.username)
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

        columns = [
            {'name': 'username', 'label': 'Username', 'field': 'username'},
            {'name': 'preferred_name', 'label': 'Display Name', 'field': 'preferred_name'},
            {'name': 'pronouns', 'label': 'Pronouns', 'field': 'pronouns'},
            {'name': 'challonge', 'label': 'Challonge', 'field': 'challonge'},
            {'name': 'roles', 'label': 'Roles', 'field': 'roles'},
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

        async def remove_member(row, client) -> None:
            with client:
                actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                user = await UserService().get_user_by_id(row['id'])
                if user is None:
                    ui.notify('That account no longer exists', color='negative')
                    return
                try:
                    await TenantMembershipService().remove_member(actor, user)
                except (ValueError, PermissionError) as e:
                    ui.notify(str(e), color='warning')
                    return
                ui.notify(f'{user.display_name or user.username} removed from this community',
                          color='positive')
                await table_view.refresh()

        # Toolbar row — rendered before filter and table for correct visual order
        with ui.row().classes('full-width'):
            ui.button('Add Member', icon='person_add', on_click=add_member).props('color=primary')
            ui.button('Add User', icon='add', on_click=add_user).props('flat color=primary')
            ui.space()
            # Lambda, not a direct reference: the toolbar is built before
            # table_view exists.
            refresh_button(lambda: table_view.refresh())

        # Filter card — between toolbar and table, matching match-filters-card pattern
        with ui.card().classes('match-filters-card'):
            with ui.row().classes('match-filter-row'):
                with ui.column().classes('match-filter-column'):
                    ui.label('Filter by Role').classes('match-filter-label')
                    role_options = {r.value: r.name.replace('_', ' ').title() for r in Role}
                    role_options[_TA_FILTER] = 'Tournament Admin'
                    role_options[_CC_FILTER] = 'Crew Coordinator'
                    role_select = (
                        ui.select(options=role_options, value=[], multiple=True)
                        .props('outlined dense use-chips clearable')
                    )
                    role_select.bind_value(selected, 'value')

        # Table — toolbar suppressed since we rendered it above
        table_view = UserTableView(
            columns=columns, get_query=get_query, show_toolbar=False,
            row_actions=_ROW_ACTIONS,
            empty_message=(
                'Nobody is a member of this community yet. Add Member brings an '
                'existing account in; granting someone a role makes them a member too.'
            ),
        )
        table_view.table.on(
            'remove_member',
            lambda e: background_tasks.create(remove_member(e.args, context.client)),
        )

        # Same rebind as the tab-switch below: an 'update:model-value' handler
        # is a client event, so a bare background task loses the tenant.
        role_select.on('update:model-value', lambda *_: table_view._bg(table_view.refresh()))

        # Route through the view's _bg so refresh rebinds the tenant captured at
        # build — the selected_tab handler runs detached, and _format_user_row
        # relies on that tenant to keep the roles column scoped.
        def on_tab_selected():
            table_view._bg(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Users' else None)
