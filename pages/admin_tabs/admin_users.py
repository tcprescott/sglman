"""Admin Users Management Page"""


from nicegui import background_tasks, ui

from models import Role, User
from theme.dialog import AdminUserDialog
from theme.tables.user import UserTableView


_TA_FILTER = '_tournament_admin'
_CC_FILTER = '_crew_coordinator'


def admin_users_page() -> None:
    with ui.column().classes('page-container-narrow w-full'):
        with ui.row().classes('header-row'):
            ui.label('User Management').classes('page-title')

        ui.separator().classes('separator-spacing')

        # Filter controls: global roles plus synthetic Tournament Admin / Crew Coordinator entries
        with ui.row().classes('q-gutter-sm items-center'):
            ui.label('Filter by role:')
            role_options = {r.value: r.name.replace('_', ' ').title() for r in Role}
            role_options[_TA_FILTER] = 'Tournament Admin'
            role_options[_CC_FILTER] = 'Crew Coordinator'
            selected = {'value': []}
            role_select = (
                ui.select(options=role_options, value=[], label='Roles', multiple=True)
                .props('use-chips clearable')
            )
            role_select.bind_value(selected, 'value')

        columns = [
            {'name': 'username', 'label': 'Username', 'field': 'username'},
            {'name': 'preferred_name', 'label': 'Display Name', 'field': 'preferred_name'},
            {'name': 'pronouns', 'label': 'Pronouns', 'field': 'pronouns'},
            {'name': 'roles', 'label': 'Roles', 'field': 'roles'},
        ]

        def get_query():
            sel_list = selected.get('value') or []
            if not sel_list:
                return User.all()
            global_roles = [v for v in sel_list if v in {r.value for r in Role}]
            qs = User.all()
            if global_roles:
                qs = qs.filter(roles__role__in=global_roles)
            if _TA_FILTER in sel_list:
                qs = qs.filter(admin_tournaments__isnull=False)
            if _CC_FILTER in sel_list:
                qs = qs.filter(crew_coordinated_tournaments__isnull=False)
            return qs.distinct()

        async def add_user():
            async def after_submit(_):
                await table_view.refresh()
            dialog = AdminUserDialog(on_submit=after_submit)
            await dialog.open()

        table_view = UserTableView(
            columns=columns, get_query=get_query, submit_user_callback=add_user)

        role_select.on('update:model-value', lambda *_: background_tasks.create(table_view.refresh()))

        def on_tab_selected():
            background_tasks.create(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Users' else None)
