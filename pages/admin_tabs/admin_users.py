"""Admin Users Management Page"""

import asyncio

from nicegui import ui

from models import User
from theme.dialog import AdminUserDialog
from theme.tables.user import UserTableView


def admin_users_page() -> None:
    with ui.column().classes('page-container-narrow'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('User Management').classes('page-title')
        
        ui.separator().classes('separator-spacing')
        
        columns = [
            {'name': 'username', 'label': 'Username', 'field': 'username'},
            {'name': 'preferred_name', 'label': 'Display Name', 'field': 'preferred_name'},
            {'name': 'pronouns', 'label': 'Pronouns', 'field': 'pronouns'},
            {'name': 'permission', 'label': 'Permission', 'field': 'permission'},
        ]

        def get_query():
            return User.all()

        async def add_user():
            async def after_submit(_):
                await table_view.refresh()
            dialog = AdminUserDialog(on_submit=after_submit)
            await dialog.open()

        table_view = UserTableView(
            columns=columns, get_query=get_query, submit_user_callback=add_user)
        
        def on_tab_selected():
            asyncio.create_task(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Users' else None)
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Users' else None)
