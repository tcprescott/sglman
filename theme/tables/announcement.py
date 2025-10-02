import asyncio
from nicegui import ui
from models import Announcement, Tournament
from theme.dialog.announcement_dialog import AnnouncementDialog
from theme.tables.base_table import BaseTableView

class AnnouncementTableView(BaseTableView):
    def __init__(self, columns, get_query, extra_slots=None, submit_announcement_callback=None):
        super().__init__(
            columns=columns,
            get_query=get_query,
            extra_slots=extra_slots,
            submit_callback=submit_announcement_callback,
            table_class='announcement-table',
            add_label='Add Announcement',
            edit_slot='body-cell-id',
        )

    async def on_edit(self, event):
        announcement_id = event.args['row']['id']
        announcement = await Announcement.get(id=announcement_id).prefetch_related('tournament')
        dialog = AnnouncementDialog(announcement)
        await dialog.open()

    def _build_row(self, ann):
        return {
            'id': ann.id,
            'title': ann.title,
            'content': ann.content,
            'important': 'Yes' if ann.important else '',
            'is_active': 'Yes' if ann.is_active else '',
            'tournament': ann.tournament.name if ann.tournament else '',
            'created_at': ann.created_at.strftime('%Y-%m-%d %H:%M') if ann.created_at else '',
            'updated_at': ann.updated_at.strftime('%Y-%m-%d %H:%M') if ann.updated_at else '',
        }

