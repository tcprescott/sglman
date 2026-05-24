"""Admin Users Management Page"""


from nicegui import background_tasks, ui

from models import User, Permissions
from theme.dialog import AdminUserDialog
from theme.tables.user import UserTableView


def admin_users_page() -> None:
    with ui.column().classes('page-container-narrow'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('User Management').classes('page-title')
        
        ui.separator().classes('separator-spacing')

        # Filter controls
        with ui.row().classes('q-gutter-sm items-center'):
            ui.label('Filter by permission:')
            # Multi-select with chips; empty selection means "All"
            perm_options = [p.name for p in Permissions]
            selected = {'value': []}
            perm_select = (
                ui.select(options=perm_options, value=[], label='Permissions', multiple=True)
                .props('use-chips clearable')
            )
            perm_select.bind_value(selected, 'value')
        
        columns = [
            {'name': 'username', 'label': 'Username', 'field': 'username'},
            {'name': 'preferred_name', 'label': 'Display Name', 'field': 'preferred_name'},
            {'name': 'pronouns', 'label': 'Pronouns', 'field': 'pronouns'},
            {'name': 'permission', 'label': 'Permission', 'field': 'permission'},
        ]

        def get_query():
            # Apply permission filter when one or more selected; empty -> All
            sel_list = selected.get('value') or []
            if isinstance(sel_list, list) and len(sel_list) > 0:
                try:
                    enum_vals = [Permissions[name] for name in sel_list]
                    return User.filter(permission__in=enum_vals)
                except KeyError:
                    return User.all()
            return User.all()

        async def add_user():
            async def after_submit(_):
                await table_view.refresh()
            dialog = AdminUserDialog(on_submit=after_submit)
            await dialog.open()

        table_view = UserTableView(
            columns=columns, get_query=get_query, submit_user_callback=add_user)

        # Refresh table when filter changes
        perm_select.on('update:model-value', lambda *_: background_tasks.create(table_view.refresh()))

        def on_tab_selected():
            background_tasks.create(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Users' else None)
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Users' else None)
