"""Triforce text submission, opened from a tournament's signup card.

This was its own Home tab with its own tournament index, which meant picking a
tournament twice: once on Tournaments to sign up, again here to submit text for
the thing you just signed up for. The index is gone and the submission form is a
dialog hanging off the card for the tournament it belongs to.
"""

from typing import Set

from nicegui import ui

from application.services import (
    AuthService,
    SeedGenerationService,
    TriforceTextService,
)
from models import Tournament, User

_HELP_TEXT = (
    "Submit up to 3 lines (max 19 characters each) that may be embedded into "
    "the end-game triforce screen of an ALTTP randomizer seed. Allowed "
    "characters: letters, numbers, spaces, basic punctuation, arrows, and "
    "hiragana/katakana. Submissions are reviewed by tournament admins."
)


async def supporting_tournament_ids() -> Set[int]:
    """Tournaments whose seed generator can carry triforce text.

    Only says the tournament *supports* submissions. Whether this particular
    viewer may submit is :meth:`AuthService.can_submit_triforce_text`, resolved
    when the dialog opens, because it can turn on a paid option per user.
    """
    return {t.id for t in await TriforceTextService().list_supporting_tournaments()}


async def open_triforce_dialog(tournament: Tournament, user: User) -> None:
    service = TriforceTextService()
    accepts = tournament.is_active and SeedGenerationService.supports_triforce_texts(
        tournament.seed_generator
    )
    can_submit = await AuthService.can_submit_triforce_text(user, tournament)

    with ui.dialog() as dialog, ui.card().classes('w-full'):
        with ui.row().classes('items-center justify-between full-width no-wrap'):
            ui.label(f'Triforce Texts — {tournament.name}').classes('text-h6')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense')

        if not accepts:
            ui.label(
                'This tournament is not accepting triforce text submissions.'
            ).classes('text-grey-7')
            dialog.open()
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
            dialog.open()
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
            rows = await service.list_user_submissions(tournament.id, user)
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
                await service.submit(tournament.id, lines, user)
            except ValueError as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Submitted! A moderator will review.', color='positive')
            for inp in line_inputs:
                inp.set_value('')
            submissions_list.refresh()

        with ui.row().classes('q-mt-md'):
            ui.button('Submit', icon='send', on_click=on_submit).props('color=primary')

        ui.separator().classes('separator-spacing')
        ui.label('Your Submissions').classes('text-h6')
        await submissions_list()

    dialog.open()
