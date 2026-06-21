"""Home Triforce Texts tab (inline tournament selection + submission)."""

from nicegui import ui

from application.services import (
    AuthService,
    SeedGenerationService,
    TriforceTextService,
    current_user_from_storage,
)
from models import Tournament


_HELP_TEXT = (
    "Submit up to 3 lines (max 19 characters each) that may be embedded into "
    "the end-game triforce screen of an ALTTP randomizer seed. Allowed "
    "characters: letters, numbers, spaces, basic punctuation, arrows, and "
    "hiragana/katakana. Submissions are reviewed by tournament admins."
)


async def triforce_texts_tab() -> None:
    user = await current_user_from_storage()
    if user is None:
        ui.label('You must be logged in.').classes('text-error')
        return

    service = TriforceTextService()
    state: dict = {'tournament_id': None}

    async def _render_index() -> None:
        tournaments = await service.list_supporting_tournaments()

        with ui.column().classes('page-container-narrow'):
            with ui.row().classes('header-row'):
                ui.label('Triforce Texts').classes('page-title')

            ui.label(
                'Submit custom text for the end-game triforce screen of supported '
                'tournaments. Choose a tournament below.'
            ).classes('text-caption text-grey-7')
            ui.separator().classes('separator-spacing')

            if not tournaments:
                ui.label(
                    'No tournaments are currently accepting triforce text submissions.'
                ).classes('text-grey-7')
                return

            def _open(tid: int) -> None:
                state['tournament_id'] = tid
                content.refresh()

            for tournament in tournaments:
                with ui.card().classes('w-full q-mb-sm'):
                    with ui.row().classes('items-center justify-between w-full'):
                        ui.label(tournament.name).classes('text-subtitle1')
                        ui.button(
                            'Open',
                            icon='arrow_forward',
                            on_click=lambda _, tid=tournament.id: _open(tid),
                        ).props('color=primary dense')

    async def _render_submission(tournament_id: int) -> None:
        def _back() -> None:
            state['tournament_id'] = None
            content.refresh()

        tournament = await Tournament.get_or_none(id=tournament_id)
        if tournament is None:
            with ui.column().classes('page-container-narrow'):
                ui.button('Back', icon='arrow_back', on_click=_back).props('flat color=primary')
                ui.label('Tournament not found.').classes('text-error')
            return

        accepts = tournament.is_active and SeedGenerationService.supports_triforce_texts(
            tournament.seed_generator
        )
        can_submit = await AuthService.can_submit_triforce_text(user, tournament)

        with ui.column().classes('page-container-narrow'):
            with ui.row().classes('header-row items-center'):
                ui.button('Back', icon='arrow_back', on_click=_back).props('flat color=primary')
                ui.label(f'Triforce Texts — {tournament.name}').classes('page-title')

            if not accepts:
                ui.label(
                    'This tournament is not accepting triforce text submissions.'
                ).classes('text-grey-7')
                return

            if not can_submit:
                if tournament.triforce_access_message:
                    # Rendered as plain text (not markdown/HTML): this field is
                    # writable by per-tournament admins and shown to all players,
                    # so HTML passthrough would be a stored-XSS vector.
                    ui.label(tournament.triforce_access_message).style(
                        'white-space: pre-wrap'
                    )
                else:
                    ui.label(
                        'Submitting triforce texts is a paid option for this tournament.'
                    ).classes('text-grey-7')
                return

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
            async def submissions_list() -> None:
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
                    on_click=on_submit,
                ).props('color=primary')

            ui.separator().classes('separator-spacing')
            ui.label('Your Submissions').classes('text-h6')
            await submissions_list()

    @ui.refreshable
    async def content() -> None:
        if state['tournament_id'] is None:
            await _render_index()
        else:
            await _render_submission(state['tournament_id'])

    await content()
