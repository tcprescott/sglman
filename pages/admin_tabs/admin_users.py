"""Admin Users Management Page"""

import asyncio

from nicegui import ui

from models import User
from theme.dialog import UserDialog
from theme.tables.user import UserTableView


def admin_users_page() -> None:
    with ui.row().style('width: 100%;'):
        ui.label('User Management').style('font-size: 2em; margin-bottom: 1em;')
    
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
        dialog = UserDialog(on_submit=after_submit, admin_view=True)
        await dialog.open()

    table_view = UserTableView(
        columns=columns, get_query=get_query, submit_user_callback=add_user)
    
    def on_tab_selected():
        asyncio.create_task(table_view.refresh())
    ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Users' else None)
