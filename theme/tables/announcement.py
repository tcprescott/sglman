import asyncio
from nicegui import ui
from models import Announcement, Tournament
from theme.dialog.announcement_dialog import AnnouncementDialog


class AnnouncementTableView:
    """Encapsulates the announcement table UI and logic for admin dashboards."""
    def __init__(self, columns, get_query, extra_slots=None, submit_announcement_callback=None):
        self.columns = columns
        self.get_query = get_query
        self.extra_slots = extra_slots
        self.submit_announcement_callback = submit_announcement_callback
        self.table = None
        self._setup_ui()

    def _setup_ui(self):
        with ui.row().style('width: 100%;'):
            if self.submit_announcement_callback:
                ui.button('Add Announcement', on_click=self.submit_announcement_callback)
            ui.button(on_click=self.refresh).props('icon=refresh').style('min-width: 0; margin-left: auto;')
        ui.add_head_html("""
        <style>
        .announcement-table th, .announcement-table td {
            border-right: 1px solid #ccc;
        }
        .announcement-table td {
            text-align: left;
        }
        .announcement-table th {
            text-align: center;
        }
        .announcement-table th:last-child, .announcement-table td:last-child {
            border-right: none;
        }
        .announcement-table {
            border-collapse: collapse;
        }
        </style>
        """)
        self.table = ui.table(columns=self.columns, rows=[], row_key='id').classes('announcement-table w-full')
        self.table.add_slot('body-cell-id', '''<q-td :props="props">
            <a href="#" @click="$parent.$emit('edit_announcement', props)" style="color: #1976d2; text-decoration: underline;">{{ props.value }}</a>
        </q-td>''')
        self.table.on('edit_announcement', self.on_edit_announcement)
        if self.extra_slots:
            self.extra_slots(self.table)
        self.refresh()

    async def on_edit_announcement(self, event):
        announcement_id = event.args['row']['id']
        announcement = await Announcement.get(id=announcement_id).prefetch_related('tournament')
        dialog = AnnouncementDialog(announcement)
        await dialog.open()

    def _build_row(self, ann):
        row = {
            'id': ann.id,
            'title': ann.title,
            'content': ann.content,
            'important': 'Yes' if ann.important else '',
            'is_active': 'Yes' if ann.is_active else '',
            'tournament': ann.tournament.name if ann.tournament else '',
            'created_at': ann.created_at.strftime('%Y-%m-%d %H:%M') if ann.created_at else '',
            'updated_at': ann.updated_at.strftime('%Y-%m-%d %H:%M') if ann.updated_at else '',
        }
        return row

    def refresh(self):
        async def fetch():
            from theme.dialog.announcement_dialog import AnnouncementDialog
            announcements = await self.get_query()
            rows = [self._build_row(ann) for ann in announcements]
            self.table.rows = rows
            for i, ann in enumerate(announcements):
                async def make_edit_callback(announcement):
                    dialog = AnnouncementDialog(announcement)
                    await dialog.open()
        asyncio.create_task(fetch())
