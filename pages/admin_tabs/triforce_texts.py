"""Admin tab for moderating triforce text submissions."""

from nicegui import app, background_tasks, ui

from application.services import AuthService, TriforceTextService, get_user_from_discord_id
from models import Tournament
from theme.dialog.confirmation_dialog import ConfirmationDialog


_STATUS_OPTIONS = {
    'pending': 'Pending',
    'approved': 'Approved',
    'rejected': 'Rejected',
    'all': 'All',
}


def _to_status(option: str):
    return None if option == 'all' else option


async def admin_triforce_texts_page() -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if actor is None:
        ui.label('User not found.').classes('text-error')
        return

    is_staff = await AuthService.is_staff(actor)
    if is_staff:
        tournaments = await Tournament.filter(is_active=True).order_by('name')
    else:
        tournaments = await Tournament.filter(
            is_active=True, admins__id=actor.id
        ).distinct().order_by('name')

    if not tournaments:
        with ui.column().classes('page-container-narrow'):
            ui.label('Triforce Texts').classes('page-title')
            ui.separator()
            ui.label('You are not an admin of any active tournament.').classes('text-grey-7')
        return

    state = {
        'tournament_id': tournaments[0].id,
        'status': 'pending',
    }
    service = TriforceTextService()

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Triforce Texts').classes('page-title')

        ui.separator().classes('separator-spacing')

        with ui.card().classes('match-filters-card'):
            with ui.row().classes('match-filter-row'):
                with ui.column().classes('match-filter-column'):
                    ui.label('Tournament').classes('match-filter-label')
                    tournament_select = ui.select(
                        options={t.id: t.name for t in tournaments},
                        value=state['tournament_id'],
                    ).props('outlined dense').classes('full-width')
                with ui.column().classes('match-filter-column'):
                    ui.label('Status').classes('match-filter-label')
                    status_select = ui.select(
                        options=_STATUS_OPTIONS,
                        value=state['status'],
                    ).props('outlined dense')

        table_container = ui.column().classes('w-full')

        @ui.refreshable
        def submissions_table() -> None:
            async def render():
                table_container.clear()
                rows = await service.list_for_moderation(
                    state['tournament_id'],
                    status=_to_status(state['status']),
                )
                with table_container:
                    if not rows:
                        ui.label('No submissions match the current filter.').classes('text-grey-7')
                        return
                    for entry in rows:
                        with ui.card().classes('w-full q-mb-sm'):
                            with ui.row().classes('items-start justify-between w-full'):
                                with ui.column().classes('q-gutter-xs'):
                                    ui.label(entry.text).style(
                                        'white-space: pre-line; font-family: monospace;'
                                    )
                                    author = entry.author or (
                                        entry.user.preferred_name if entry.user else 'unknown'
                                    )
                                    ui.label(f'by {author}').classes('text-caption text-grey-7')
                                with ui.column().classes('q-gutter-xs items-end'):
                                    status = (
                                        'Pending' if entry.approved is None
                                        else 'Approved' if entry.approved
                                        else 'Rejected'
                                    )
                                    status_color = (
                                        'orange' if entry.approved is None
                                        else 'positive' if entry.approved
                                        else 'negative'
                                    )
                                    ui.badge(status, color=status_color)
                                    with ui.row().classes('q-gutter-xs'):
                                        ui.button(
                                            'Approve',
                                            icon='check',
                                            on_click=lambda _, eid=entry.id: _moderate(eid, True),
                                        ).props('color=positive dense').props(
                                            'disable' if entry.approved is True else ''
                                        )
                                        ui.button(
                                            'Reject',
                                            icon='close',
                                            on_click=lambda _, eid=entry.id: _moderate(eid, False),
                                        ).props('color=negative dense').props(
                                            'disable' if entry.approved is False else ''
                                        )
                                        ui.button(
                                            icon='delete',
                                            on_click=lambda _, eid=entry.id: _confirm_delete(eid),
                                        ).props('flat dense color=grey').tooltip('Delete')
            background_tasks.create(render())

        async def _moderate(text_id: int, approved: bool) -> None:
            try:
                await service.moderate(text_id, approved, actor)
            except ValueError as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify(
                'Approved.' if approved else 'Rejected.',
                color='positive' if approved else 'warning',
            )
            submissions_table.refresh()

        async def _delete(text_id: int) -> None:
            try:
                await service.delete(text_id, actor)
            except ValueError as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Deleted.', color='positive')
            submissions_table.refresh()

        def _confirm_delete(text_id: int) -> None:
            async def on_confirm():
                await _delete(text_id)
            ConfirmationDialog(
                message='Are you sure you want to delete this triforce text submission? This action cannot be undone.',
                on_confirm=on_confirm,
                confirm_text='Delete',
                cancel_text='Cancel',
            ).open()

        def on_tournament_change(e):
            state['tournament_id'] = int(e.value)
            submissions_table.refresh()

        def on_status_change(e):
            state['status'] = e.value
            submissions_table.refresh()

        tournament_select.on_value_change(on_tournament_change)
        status_select.on_value_change(on_status_change)

        submissions_table()
