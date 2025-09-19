from nicegui import ui
import asyncio

class UserTableView:
    """Encapsulates the user table UI and logic for admin/player dashboards."""
    def __init__(self, columns, get_query, extra_slots=None, submit_user_callback=None):
        self.columns = columns
        self.get_query = get_query
        self.extra_slots = extra_slots
        self.submit_user_callback = submit_user_callback
        self.table = None
        self._setup_ui()

    def _setup_ui(self):
        with ui.row().style('width: 100%;'):
            if self.submit_user_callback:
                ui.button('Add User', on_click=self.submit_user_callback)
            ui.button('Refresh', on_click=self.refresh).props('icon=refresh').style('min-width: 0; margin-left: auto;')

        ui.add_head_html("""
        <style>
        .user-table th, .user-table td {
            border-right: 1px solid #ccc;
        }
        .user-table td {
            text-align: left;
        }
        .user-table th {
            text-align: center;
        }
        .user-table th:last-child, .user-table td:last-child {
            border-right: none;
        }
        .user-table {
            border-collapse: collapse;
        }
        .user-table tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .user-table tr:nth-child(odd) {
            background-color: #ffffff;
        }
        </style>
        """)
        with ui.column().style('width: 100%;'):
            self.table = ui.table(
                columns=self.columns,
                rows=[],
                row_key='id',
                pagination={'rowsPerPage': 20, 'page': 1}
            ).classes('user-table').style('margin-top: 1em; width: 100%;')
        self.table.on('update:pagination', self._on_page_change)
        # Add slot for clickable username
        self.table.add_slot('body-cell-username', '''<q-td :props="props">
            <a href="#" @click="$parent.$emit('edit_user', props)" style="color: #1976d2; text-decoration: underline;">{{ props.value }}</a>
        </q-td>''')
        if self.extra_slots:
            for slot_name, slot_template in self.extra_slots.items():
                self.table.add_slot(slot_name, slot_template)
        # Handler for editing a user
        async def handle_edit_user(event):
            row = event.args['row'] if 'row' in event.args else event.args
            user_id = row['id']
            user_query = self.get_query()
            u = await user_query.filter(id=user_id).first()
            if not u:
                ui.notify('User not found.', color='warning')
                return
            from pages.dialogues import UserEditDialog
            dialog = UserEditDialog(u)
            await dialog.open()
        self.table.on('edit_user', handle_edit_user)

    async def refresh(self, *args, **kwargs):
        user_query = self.get_query()
        all_users = await user_query.order_by('username')
        rows = []
        for u in all_users:
            row = {
                'id': u.id,
                'username': u.username,
                'display_name': u.display_name or '',
                'discord_id': u.discord_id,
                'is_active': u.is_active,
                'permission': u.permission,
                'created_at': u.created_at.strftime('%Y-%m-%d %H:%M') if u.created_at else '',
                'updated_at': u.updated_at.strftime('%Y-%m-%d %H:%M') if u.updated_at else ''
            }
            rows.append(row)
        self.table.rows = rows
        self.table.update()

    def _on_page_change(self, event):
        asyncio.create_task(self.refresh())

    async def update_row_by_id(self, user_id):
        """
        Update a single row in the table by its user ID, only if the row is currently visible.
        """
        idx = next((i for i, row in enumerate(self.table.rows) if row.get('id') == user_id), None)
        if idx is None:
            return  # Row not visible, do nothing
        user_query = self.get_query()
        u = await user_query.filter(id=user_id).first()
        if not u:
            return  # User not found
        row = {
            'id': u.id,
            'username': u.username,
            'display_name': u.display_name or '',
            'discord_id': u.discord_id,
            'is_active': u.is_active,
            'permission': u.permission,
            'created_at': u.created_at.strftime('%Y-%m-%d %H:%M') if u.created_at else '',
            'updated_at': u.updated_at.strftime('%Y-%m-%d %H:%M') if u.updated_at else ''
        }
        self.table.rows[idx] = row
        self.table.update()
