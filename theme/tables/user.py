import asyncio

from nicegui import ui


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
            ui.button(on_click=self.refresh).props(
                'icon=refresh').style('min-width: 0; margin-left: auto;')

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
                # pagination={'rowsPerPage': 20, 'page': 1}
            ).classes('user-table').style('margin-top: 1em; width: 100%;').props(':grid="Quasar.Screen.lt.md"')
        self.table.on('update:pagination', self._on_page_change)
        # Add slot for clickable username
        self.table.add_slot('body-cell-username', '''<q-td :props="props">
            <a href="#" @click="$parent.$emit('edit_user', props)" style="color: #1976d2; text-decoration: underline;">{{ props.value }}</a>
        </q-td>''')
        self.render_grid_slot()
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
            from theme.dialog import UserDialog
            dialog = UserDialog(u)
            await dialog.open()
        self.table.on('edit_user', handle_edit_user)

    def render_grid_slot(self):
        # Dynamically generate grid slot fields from self.columns
        grid_fields = []
        for col in self.columns:
            field = { 'label': col.get('label', col.get('name', '')), 'key': col.get('name', '') }
            # Add event for username
            if field['key'] == 'username':
                field['event'] = 'edit_user'
            # Add bool for is_active
            if field['key'] == 'is_active':
                field['bool'] = True
            grid_fields.append(field)
        # Build JS array for Vue template
        js_field_array = ',\n    '.join([
            f"{{ label: '{f['label']}', key: '{f['key']}'" +
            (f", event: '{f['event']}'" if 'event' in f else '') +
            (", bool: true" if f.get('bool') else '') + " }" for f in grid_fields
        ])
        self.table.add_slot('item', f'''
        <div class="q-pa-md q-mb-sm" style="width: 100%; box-sizing: border-box; border: 1px solid #eee; border-radius: 8px; background: #fff;">
        <div v-for="field in [
            {js_field_array}
        ]" :key="field.key" class="row items-center q-mb-xs">
            <div class="col-4 text-grey-7">{{{{ field.label }}}}:</div>
            <div class="col-8">
            <template v-if="field.event">
                <a href="#" @click="$parent.$emit(field.event, {{ row: props.row }})" style="color: #1976d2; text-decoration: underline;">{{{{ props.row[field.key] }}}}</a>
            </template>
            <template v-else-if="field.bool">
                {{{{ props.row[field.key] ? 'Yes' : 'No' }}}}
            </template>
            <template v-else>
                {{{{ props.row[field.key] }}}}
            </template>
            </div>
        </div>
        </div>
        ''')

    async def refresh(self, *args, **kwargs):
        user_query = self.get_query()
        all_users = await user_query.order_by('username')
        rows = []
        for u in all_users:
            row = {
                'id': u.id,
                'username': u.username,
                'display_name': u.display_name or '',
                'preferred_name': u.preferred_name or '',
                'pronouns': u.pronouns or '',
                'discord_id': u.discord_id,
                'is_active': u.is_active,
                'permission': u.permission,
                'created_at': u.created_at.strftime('%Y-%m-%d %H:%M') if u.created_at else '',
                'updated_at': u.updated_at.strftime('%Y-%m-%d %H:%M') if u.updated_at else '',
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
        idx = next((i for i, row in enumerate(self.table.rows)
                   if row.get('id') == user_id), None)
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
            'pronouns': u.pronouns or '',
            'discord_id': u.discord_id,
            'is_active': u.is_active,
            'permission': u.permission,
            'created_at': u.created_at.strftime('%Y-%m-%d %H:%M') if u.created_at else '',
            'updated_at': u.updated_at.strftime('%Y-%m-%d %H:%M') if u.updated_at else ''
        }
        self.table.rows[idx] = row
        self.table.update()
