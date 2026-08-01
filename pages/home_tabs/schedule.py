

from nicegui import app, ui

from application.services import MatchService
from theme.dialog.match_dialog import UserMatchDialog
from theme.help import help_icon
from theme.tables.match import MatchTableView
from theme.tables.match_slots import SEED_SLOT_READONLY, state_readonly_slot
from theme.tables.preferences import TableKeys


async def schedule():
    discord_id = app.storage.user.get('discord_id', None)
    match_service = MatchService()

    with ui.column().classes('page-container'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Schedule & Crew Signup').classes('page-title')
            # Bare icon = "explain this page"; labelled icons = a named topic.
            # Two bare help_outlines side by side are indistinguishable.
            await help_icon('schedule-columns')
            await help_icon('match-states', label='States')
            ui.space()
            if not discord_id:
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary')

        ui.separator().classes('separator-spacing')

        columns = [
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament', 'sortable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at',
             'sortable': True},
            {'name': 'state', 'label': 'State', 'field': 'state', 'sortable': True},
            # Not sortable: joined rosters sort on whoever is listed first.
            {'name': 'players', 'label': 'Players', 'field': 'players'},
            {'name': 'stream_room', 'label': 'Stage', 'field': 'stream_room', 'sortable': True},
            {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed',
             'sortable': True},
            {'name': 'commentators', 'label': 'Commentators', 'field': 'commentators'},
            {'name': 'trackers', 'label': 'Trackers', 'field': 'trackers'},
        ]
        if discord_id:
            columns.append({'name': 'watch', 'label': 'Watch', 'field': 'watch'})

        async def get_query():
            return await match_service.get_all_matches_for_schedule()

        extra_slots = {
            'body-cell-state': state_readonly_slot(scheduled_detailed=True),
            'body-cell-generated_seed': SEED_SLOT_READONLY,
        }

        async def on_edit(match_id: int):
            if not discord_id:
                return
            match = await match_service.get_by_id(match_id)
            if not match:
                ui.notify('Match not found.', color='warning')
                return
            dialog = UserMatchDialog(
                discord_id=discord_id,
                match=match,
                on_submit=lambda *_: table_view.refresh(),
            )
            await dialog.open()

        # Include crew signup functionality with centralized green/yellow status rendering
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=False,
            table_key=TableKeys.HOME_SCHEDULE,
            extra_slots=extra_slots,
            on_edit=on_edit if discord_id else None,
            grid_breakpoint='lt.lg',
            storage_key='home_schedule',
        )

        # The view loads itself once its filters are restored (MatchTableView
        # ._initial_load) — kicking a refresh here as well raced that restore and
        # doubled the query fan-out.
