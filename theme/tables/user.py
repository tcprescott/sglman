from nicegui import background_tasks, ui
from models import Permissions


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
        # Toolbar with actions
        with ui.row().classes('full-width'):
            if self.submit_user_callback:
                ui.button('Add User', icon='add', on_click=self.submit_user_callback).props('color=primary')
            ui.space()
            ui.button(icon='refresh', on_click=self.refresh).props('flat color=primary').tooltip('Refresh table')

        with ui.column().classes('full-width'):
            self.table = ui.table(
                columns=self.columns,
                rows=[],
                row_key='id',
                # pagination={'rowsPerPage': 20, 'page': 1}
            ).classes('user-table user-table-container').props(':grid="Quasar.Screen.lt.md"')
        self.table.on('update:pagination', self._on_page_change)
        # Add slot for clickable username
        self.table.add_slot('body-cell-username', '''<q-td :props="props">
            <a href="#" @click="$parent.$emit('edit_user', props)" class="table-link">{{ props.value }}</a>
        </q-td>''')
        # Render is_active as icon
        self.table.add_slot('body-cell-is_active', '''<q-td :props="props">
            <q-icon :name="props.value ? 'check_circle' : 'cancel'" :color="props.value ? 'positive' : 'negative'" size="sm" />
        </q-td>''')
        # Truncate long discord ids if present (leave plain text)
        self.table.add_slot('body-cell-discord_id', '''<q-td :props="props">
            <span v-if="props.value" class="wrap" :title="props.value">{{ props.value.toString().length > 24 ? props.value.toString().substring(0, 21) + '...' : props.value }}</span>
            <span v-else>-</span>
        </q-td>''')
        # Display permission as a chip
        self.table.add_slot('body-cell-permission', '''<q-td :props="props">
            <q-chip :color="'primary'" text-color="white" dense>{{ props.value }}</q-chip>
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
            from theme.dialog import AdminUserDialog
            dialog = AdminUserDialog(u)
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
        <div class="q-pa-md q-mb-sm user-grid-card" style="width: 100%; box-sizing: border-box; border: 1px solid #eee; border-radius: 8px; background: #fff;">
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

    async def refresh(self, *_, **__):
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
                'permission': (Permissions(u.permission).name if isinstance(u.permission, int) else str(u.permission)),
                'created_at': u.created_at.strftime('%Y-%m-%d %H:%M') if u.created_at else '',
                'updated_at': u.updated_at.strftime('%Y-%m-%d %H:%M') if u.updated_at else '',
            }
            rows.append(row)
        self.table.rows = rows
        self.table.update()

    def _on_page_change(self, _event):
        background_tasks.create(self.refresh())

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
            'permission': (Permissions(u.permission).name if isinstance(u.permission, int) else str(u.permission)),
            'created_at': u.created_at.strftime('%Y-%m-%d %H:%M') if u.created_at else '',
            'updated_at': u.updated_at.strftime('%Y-%m-%d %H:%M') if u.updated_at else ''
        }
        self.table.rows[idx] = row
        self.table.update()
