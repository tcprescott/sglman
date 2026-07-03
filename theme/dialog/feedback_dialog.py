from nicegui import ui

from application.services import FeedbackService
from models import FeedbackCategory, User
from theme.dialog._helpers import dialog_actions, dialog_header, mobile_sheet, submit_on_enter

CATEGORY_OPTIONS = {
    FeedbackCategory.BUG.value: 'Bug',
    FeedbackCategory.SUGGESTION.value: 'Suggestion',
    FeedbackCategory.PRAISE.value: 'Praise',
    FeedbackCategory.OTHER.value: 'Other',
}


class FeedbackDialog:
    """Lets a logged-in attendee submit feedback, recording the page they were on."""

    def __init__(self, user: User, initial_category: str | None = None, initial_message: str = ''):
        self.user = user
        self.dialog = None
        self.feedback_service = FeedbackService()
        self.initial_category = initial_category or FeedbackCategory.SUGGESTION.value
        self.initial_message = initial_message

    async def open(self):
        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            mobile_sheet(dialog)
            dialog_header('Send Feedback', dialog)
            with ui.column().classes('q-pa-md gap-2 full-width'):
                category_input = ui.select(
                    options=CATEGORY_OPTIONS,
                    value=self.initial_category,
                    label='Category',
                ).classes('full-width')
                message_input = ui.textarea(
                    label='Message',
                    value=self.initial_message,
                    placeholder='Tell us what works, what doesn\'t, or what you\'d like to see...',
                ).props('required autofocus').classes('full-width')
                ui.label('* required').classes('required-legend')

            async def submit():
                message = (message_input.value or '').strip()
                if not message:
                    with self.dialog:
                        ui.notify('Please enter a message before sending.', color='warning')
                    return
                page_url = await ui.run_javascript(
                    'window.location.pathname + window.location.search'
                )
                with self.dialog:
                    try:
                        await self.feedback_service.submit(
                            actor=self.user,
                            category=category_input.value,
                            message=message,
                            page_url=page_url or '',
                        )
                    except ValueError as e:
                        ui.notify(str(e), color='warning')
                        return
                    ui.notify('Thanks for your feedback!', color='positive')
                    dialog.close()

            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                send_button = ui.button('Send', on_click=submit).props('color=primary')
                send_button.bind_enabled_from(
                    message_input, 'value',
                    backward=lambda v: bool(v and v.strip()),
                )

            submit_on_enter(dialog, submit)
            dialog.open()
