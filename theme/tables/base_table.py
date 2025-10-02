from nicegui import ui
import asyncio

class BaseTableView:
    """
    Base class for NiceGUI table views with common UI logic.
    Subclasses should override _build_row and event handlers as needed.
    """
    def __init__(self, columns, get_query, extra_slots=None, submit_callback=None, table_class='', row_key='id', add_label='Add', edit_slot=None, edit_event='edit', pagination=None, admin_controls=False, custom_slots=None, show_upcoming_checkbox=False, auto_refresh_checkbox=False):
        self.columns = columns
        self.get_query = get_query
        self.extra_slots = extra_slots
        self.submit_callback = submit_callback
        self.table_class = table_class
        self.row_key = row_key
        self.add_label = add_label
        self.edit_slot = edit_slot
        self.edit_event = edit_event
        self.table = None
        self.pagination = pagination
        self.admin_controls = admin_controls
        self.custom_slots = custom_slots or {}
        self.show_upcoming_checkbox = show_upcoming_checkbox
        self.auto_refresh_checkbox = auto_refresh_checkbox
        self._auto_refresh_task = None
        self._setup_ui()

    def _setup_ui(self):
        with ui.row().style('width: 100%;'):
            if self.submit_callback:
                ui.button(self.add_label, on_click=self.submit_callback)
            if self.show_upcoming_checkbox:
                self.show_upcoming_checkbox = ui.checkbox('Show only upcoming matches', value=True)
            if self.admin_controls and self.auto_refresh_checkbox:
                self.auto_refresh_checkbox = ui.checkbox('Auto-refresh', value=False)
            ui.button(on_click=self.refresh).props('icon=refresh').style('min-width: 0; margin-left: auto;')
        self._inject_css()
        self.table = ui.table(
            columns=self.columns,
            rows=[],
            row_key=self.row_key,
            pagination=self.pagination if self.pagination else None
        ).classes(f'{self.table_class} w-full')
        if self.edit_slot and self.edit_event:
            self.table.add_slot(self.edit_slot, self._edit_slot_template())
            self.table.on(self.edit_event, self.on_edit)
        # Add custom slots
        for slot_name, slot_template in self.custom_slots.items():
            self.table.add_slot(slot_name, slot_template)
        if self.extra_slots:
            self.extra_slots(self.table)
        self.table.on('update:pagination', self._on_page_change)
        self.refresh()

    def _on_page_change(self, event):
        self.refresh()

    def _inject_css(self):
        # Subclasses can override for custom CSS
        ui.add_head_html(f"""
        <style>
        .{self.table_class} th, .{self.table_class} td {{
            border-right: 1px solid #ccc;
        }}
        .{self.table_class} td {{
            text-align: left;
        }}
        .{self.table_class} th {{
            text-align: center;
        }}
        .{self.table_class} th:last-child, .{self.table_class} td:last-child {{
            border-right: none;
        }}
        .{self.table_class} {{
            border-collapse: collapse;
        }}
        </style>
        """)

    def _edit_slot_template(self):
        # Subclasses can override for custom slot template
        return f'''<q-td :props="props">
            <a href="#" @click="$parent.$emit('{self.edit_event}', props)" style="color: #1976d2; text-decoration: underline;">{{{{ props.value }}}}</a>
        </q-td>'''

    async def on_edit(self, event):
        # Subclasses should override for edit dialog logic
        pass

    def _build_row(self, obj):
        # Subclasses should override to build row dict
        return {}

    def refresh(self):
        """Generic refresh method to reload table data."""
        async def fetch():
            qr = await self.get_query()
            rows = [self._build_row(q) for q in qr]
            self.table.rows = rows
        asyncio.create_task(fetch())
