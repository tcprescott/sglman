import asyncio
from nicegui import ui
from models import Announcement, Tournament

class AnnouncementDialog:
    def __init__(self, announcement=None, on_submit=None):
        self.announcement = announcement
        self.on_submit = on_submit
        self.dialog = None

    async def open(self):
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            title_input = ui.input('Title', value=self.announcement.title if self.announcement else '')
            content_input = ui.editor(placeholder='Content', value=self.announcement.content if self.announcement else '')
            important_checkbox = ui.checkbox('Important', value=self.announcement.important if self.announcement else False)
            is_active_checkbox = ui.checkbox('Active', value=self.announcement.is_active if self.announcement else True)
            tournaments = ['None'] + [t.name async for t in Tournament.all()]
            tournament_select = ui.select(tournaments, label='Tournament', value=self.announcement.tournament.name if self.announcement and self.announcement.tournament else 'None')
            status_label = ui.label('').classes('q-mt-md')

            async def submit():
                title = title_input.value.strip()
                content = content_input.value.strip()
                important = important_checkbox.value
                is_active = is_active_checkbox.value
                tournament_name = tournament_select.value
                tournament = None
                if tournament_name and tournament_name != 'None':
                    tournament = await Tournament.get_or_none(name=tournament_name)
                if not title or not content:
                    status_label.text = 'Title and content are required.'
                    status_label.classes('text-warning')
                    return
                if self.announcement:
                    self.announcement.title = title
                    self.announcement.content = content
                    self.announcement.important = important
                    self.announcement.is_active = is_active
                    self.announcement.tournament = tournament
                    await self.announcement.save()
                    status_label.text = 'Announcement updated.'
                    status_label.classes('text-positive')
                    dialog.close()
                    if self.on_submit:
                        await self.on_submit(self.announcement)
                else:
                    announcement = await Announcement.create(
                        title=title,
                        content=content,
                        important=important,
                        is_active=is_active,
                        tournament=tournament
                    )
                    status_label.text = 'Announcement created.'
                    status_label.classes('text-positive')
                    dialog.close()
                    if self.on_submit:
                        await self.on_submit(announcement)
            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                ui.button('Save' if self.announcement else 'Create', color='green', on_click=lambda: asyncio.create_task(submit()))
                ui.button('Cancel', color='gray', on_click=dialog.close)
            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    asyncio.create_task(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()
