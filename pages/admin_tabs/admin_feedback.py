"""Admin Feedback Review Page"""

from nicegui import app, background_tasks, ui
from theme.notify import notify_error
from theme.tables.mobile_grid import enable_mobile_grid

from application.services import FeedbackService, get_user_from_discord_id
from application.utils.timezone import format_eastern_display

_CATEGORY_LABELS = {
    'bug': 'Bug',
    'suggestion': 'Suggestion',
    'praise': 'Praise',
    'other': 'Other',
}

_COLUMNS = [
    {'name': 'created_at', 'label': 'Submitted', 'field': 'created_at', 'align': 'left', 'sortable': True},
    {'name': 'user', 'label': 'User', 'field': 'user', 'align': 'left'},
    {'name': 'category', 'label': 'Category', 'field': 'category', 'align': 'left'},
    {'name': 'message', 'label': 'Message', 'field': 'message', 'align': 'left'},
    {'name': 'page_url', 'label': 'Page', 'field': 'page_url', 'align': 'left'},
    {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'left'},
    {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
]

_STATUS_BADGE = '''
    <q-badge :color="props.row.status === 'reviewed' ? 'positive' : 'warning'">
        {{ props.row.status }}
    </q-badge>
'''

_ROW_ACTIONS = '''
    <q-btn v-if="props.row.status !== 'reviewed'" dense flat color="primary"
           label="Mark reviewed"
           @click="$parent.$emit('mark_reviewed', props.row)" />
'''


async def admin_feedback_page() -> None:
    service = FeedbackService()

    with ui.column().classes('page-container-narrow w-full'):
        with ui.row().classes('header-row items-center full-width no-wrap'):
            ui.label('Feedback').classes('page-title')
            ui.space()
            ui.button(
                icon='refresh',
                on_click=lambda: background_tasks.create(_render_table.refresh()),
            ).props('flat color=primary').tooltip('Refresh')

        ui.separator().classes('separator-spacing')

        ui.label(
            'User-submitted feedback from across the app. Review each item and mark '
            'it reviewed once handled.'
        ).classes('text-caption text-grey')

        @ui.refreshable
        async def _render_table() -> None:
            submissions = await service.list_recent()
            rows = [
                {
                    'id': fb.id,
                    'created_at': format_eastern_display(fb.created_at),
                    'user': fb.user.preferred_name if fb.user else '-',
                    'category': _CATEGORY_LABELS.get(fb.category.value, fb.category.value),
                    'message': fb.message,
                    'page_url': fb.page_url,
                    'status': fb.status.value,
                }
                for fb in submissions
            ]

            table = ui.table(columns=_COLUMNS, rows=rows, row_key='id').classes('w-full sgl-table')
            table.add_slot('body-cell-status', f'<q-td :props="props">{_STATUS_BADGE}</q-td>')
            table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')
            enable_mobile_grid(table, _COLUMNS, actions=_ROW_ACTIONS,
                               field_slots={'status': _STATUS_BADGE})

            async def handle_mark_reviewed(event):
                row = event.args
                actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                try:
                    await service.mark_reviewed(actor, row['id'])
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Marked as reviewed.', color='positive')
                await _render_table.refresh()

            table.on('mark_reviewed', handle_mark_reviewed)

        await _render_table()
