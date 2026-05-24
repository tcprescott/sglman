"""Triforce Text submission page (public, Discord OAuth required)."""

from nicegui import background_tasks, ui

from application.services import TriforceTextService, current_user_from_storage
from middleware.auth import protected_page
from models import Tournament
from theme.base import BaseLayout


_HELP_TEXT = (
    "Submit up to 3 lines (max 19 characters each) that may be embedded into "
    "the end-game triforce screen of an ALTTP randomizer seed. Allowed "
    "characters: letters, numbers, spaces, basic punctuation, arrows, and "
    "hiragana/katakana. Submissions are reviewed by tournament admins."
)


def create() -> None:
    @protected_page('/triforcetexts/{tournament_id}')
    async def triforce_texts_page(tournament_id: int):
        ui.page_title('Triforce Text Submission')

        user = await current_user_from_storage()
        if user is None:
            await BaseLayout(page_name='triforce_texts').render()
            ui.label('User not found in the database.').classes('text-error')
            return

        tournament = await Tournament.get_or_none(id=tournament_id)
        if tournament is None:
            await BaseLayout(page_name='triforce_texts', user=user).render()
            ui.label('Tournament not found.').classes('text-error')
            return

        await BaseLayout(page_name='triforce_texts', user=user).render()

        service = TriforceTextService()

        with ui.column().classes('page-container-narrow'):
            with ui.row().classes('header-row'):
                ui.label(f'Triforce Texts — {tournament.name}').classes('page-title')

            ui.label(_HELP_TEXT).classes('text-caption text-grey-7')
            ui.separator().classes('separator-spacing')

            line_inputs: list[ui.input] = []
            with ui.column().classes('w-full q-gutter-sm'):
                for i in range(1, 4):
                    line_inputs.append(
                        ui.input(label=f'Line {i}')
                        .props('maxlength=19 outlined dense')
                        .classes('w-full')
                    )

            @ui.refreshable
            def submissions_list() -> None:
                async def render():
                    rows = await service.list_user_submissions(tournament_id, user)
                    if not rows:
                        ui.label('You have no submissions yet.').classes('text-caption text-grey-7')
                        return
                    for entry in rows:
                        status = (
                            'Pending' if entry.approved is None
                            else 'Approved' if entry.approved
                            else 'Rejected'
                        )
                        color = (
                            'orange' if entry.approved is None
                            else 'positive' if entry.approved
                            else 'negative'
                        )
                        with ui.card().classes('w-full q-mb-sm'):
                            with ui.row().classes('items-center justify-between w-full'):
                                ui.label(entry.text).classes(
                                    'q-py-xs'
                                ).style('white-space: pre-line; font-family: monospace;')
                                ui.badge(status, color=color)
                background_tasks.create(render())

            async def on_submit():
                lines = [inp.value or '' for inp in line_inputs]
                try:
                    await service.submit(tournament_id, lines, user)
                except ValueError as e:
                    ui.notify(str(e), color='warning')
                    return
                ui.notify('Submitted! A moderator will review.', color='positive')
                for inp in line_inputs:
                    inp.set_value('')
                submissions_list.refresh()

            with ui.row().classes('q-mt-md'):
                ui.button(
                    'Submit',
                    icon='send',
                    on_click=lambda: background_tasks.create(on_submit()),
                ).props('color=primary')

            ui.separator().classes('separator-spacing')
            ui.label('Your Submissions').classes('text-h6')
            submissions_list()
