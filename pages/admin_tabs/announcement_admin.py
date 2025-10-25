
from nicegui import ui, app
from models import Announcement, Permissions
from theme.dialog.announcement_dialog import AnnouncementDialog
from theme.tables.announcement import AnnouncementTableView

async def announcement_admin_page():
    user = app.storage.user
    columns = [
        {'name': 'id', 'label': 'ID', 'field': 'id'},
        {'name': 'title', 'label': 'Title', 'field': 'title'},
        {'name': 'content', 'label': 'Content', 'field': 'content'},
        {'name': 'important', 'label': 'Important', 'field': 'important'},
        {'name': 'is_active', 'label': 'Active', 'field': 'is_active'},
        {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
        {'name': 'created_at', 'label': 'Created At', 'field': 'created_at'},
        {'name': 'updated_at', 'label': 'Updated At', 'field': 'updated_at'},
    ]
    async def get_query():
        return await Announcement.all().prefetch_related('tournament')
    async def submit_announcement_callback():
        async def after_submit(_):
            await announcement_view.refresh()
        dialog = AnnouncementDialog(on_submit=after_submit)
        await dialog.open()

    announcement_view = AnnouncementTableView(columns, get_query, submit_announcement_callback=submit_announcement_callback)
