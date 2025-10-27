"""Admin Schedule Management Page"""

import asyncio

from nicegui import ui

from application.services import MatchScheduleService
from models import Match
from theme.dialog import ConfirmationDialog, MatchDialog
from theme.dialog.stream_room_dialog import StreamRoomDialog
from theme.tables.match import MatchTableView


def admin_schedule_page() -> None:
    # Initialize services
    match_schedule_service = MatchScheduleService()
    
    with ui.column().style('width: 100%; max-width: 1600px; margin: 0 auto;') as page_container:
        # Header section
        with ui.row().style('width: 100%; align-items: center; margin-bottom: 1.5em;'):
            ui.label('Schedule Management').style('font-size: 2em; font-weight: bold;')
        
        ui.separator().style('margin-bottom: 1.5em;')
        
        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id'},
            {'name': 'tournament', 'label': 'Tournament',
                'field': 'tournament', 'sortable': True, 'filterable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At',
                'field': 'scheduled_at', 'sortable': True, 'filterable': True},
            {'name': 'seated', 'label': 'Seated', 'field': 'seated',
                'sortable': True, 'filterable': True},
            {'name': 'finished', 'label': 'Finished',
                'field': 'finished', 'filterable': True},
            {'name': 'players', 'label': 'Players',
                'field': 'players', 'filterable': True},
            {'name': 'commentators', 'label': 'Commentators',
                'field': 'commentators', 'filterable': True},
            {'name': 'trackers', 'label': 'Trackers',
                'field': 'trackers', 'filterable': True},
            {'name': 'stream_room', 'label': 'Stage',
                'field': 'stream_room', 'sortable': True, 'filterable': True, 'clickable': True},
            {'name': 'generated_seed', 'label': 'Seed', 'field': 'seed'},
        ]

        def get_query():
            return Match.all()
        
        async def on_edit(match_id: int):
            match = await Match.get(id=match_id)
            async def after_edit(_):
                await table_view.update_row_by_id(match_id)
            with page_container:
                dialog = MatchDialog(match=match, on_submit=after_edit)
                await dialog.open()

        async def on_generate_seed(match_id: int):
            success, message, _ = await match_schedule_service.generate_seed(match_id)
            
            with page_container:
                if success:
                    ui.notify(message, color='positive')
                else:
                    # Check if it's just "already in progress" (not an error per se)
                    if "already in progress" in message.lower():
                        pass  # Skip notification, just refresh
                    else:
                        ui.notify(message, color='warning' if "already been generated" in message else 'negative')
            
            # Always refresh the row to clear spinner
            await table_view.update_row_by_id(match_id)

        async def on_seat(match_id: int):
            match = await Match.get(id=match_id).prefetch_related('players', 'players__user')
            player_names = ', '.join(
                [p.user.username for p in match.players])

            async def handle_confirm(_):
                dialog.dialog.close()
                await confirm_seating(match)
            with page_container:
                dialog = ConfirmationDialog(
                    message=f'Are you sure you want to mark the following players as seated for match ID {match.id}?\n\n{player_names}',
                    on_confirm=handle_confirm
                )
                dialog.open()

        async def confirm_seating(match: Match):
            try:
                await match_schedule_service.seat_match(match)
                await table_view.update_row_by_id(match.id)
            except ValueError as e:
                with page_container:
                    ui.notify(str(e), color='warning')

        async def on_finish(match_id: int):
            match = await Match.get(id=match_id).prefetch_related('players', 'players__user')
            player_names = ', '.join(
                [p.user.username for p in match.players])

            async def handle_confirm(_):
                dialog.dialog.close()
                await confirm_finishing(match)
            with page_container:
                dialog = ConfirmationDialog(
                    message=f'Are you sure you want to mark the following players as finished for match ID {match.id}?\n\n{player_names}',
                    on_confirm=handle_confirm
                )
                dialog.open()

        async def confirm_finishing(match: Match):
            try:
                await match_schedule_service.finish_match(match)
                await table_view.update_row_by_id(match.id)
            except ValueError as e:
                with page_container:
                    ui.notify(str(e), color='warning')

        async def on_edit_stream_room(match_id: int):
            match = await Match.get(id=match_id)
            async def after_edit(_):
                await table_view.update_row_by_id(match_id)
            with page_container:
                dialog = StreamRoomDialog(match=match, on_submit=after_edit)
                await dialog.open()

        async def submit_admin_match():
            async def after_submit(_):
                await table_view.refresh()
            with page_container:
                dialog = MatchDialog(on_submit=after_submit)
                await dialog.open()

        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=True,
            submit_match_callback=submit_admin_match,
            on_edit=on_edit,
            on_generate_seed=on_generate_seed,
            on_seat=on_seat,
            on_finish=on_finish,
            on_edit_stream_room=on_edit_stream_room,
        )

        def on_tab_selected():
            asyncio.create_task(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Schedule' else None)
