"""Admin Schedule Management Page"""


from nicegui import background_tasks, ui

from application.services import MatchScheduleService, current_user_from_storage
from models import Match
from theme.dialog import ConfirmationDialog, StationAssignmentDialog, MatchResultDialog
from theme.dialog.match_dialog import AdminMatchDialog
from theme.dialog.stream_room_dialog import StreamRoomDialog
from theme.tables.match import MatchTableView


def admin_schedule_page() -> None:
    # Initialize services
    match_schedule_service = MatchScheduleService()
    
    with ui.column().classes('page-container-wide') as page_container:
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Schedule Management').classes('page-title')
        
        ui.separator().classes('separator-spacing')
        
        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id'},
            {'name': 'tournament', 'label': 'Tournament',
                'field': 'tournament', 'sortable': True, 'filterable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At',
                'field': 'scheduled_at', 'sortable': True, 'filterable': True},
            {'name': 'state', 'label': 'State', 'field': 'state',
                'sortable': True, 'filterable': True},
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
                dialog = AdminMatchDialog(match=match, on_submit=after_edit)
                await dialog.open()

        async def on_generate_seed(match_id: int):
            actor = await current_user_from_storage()
            success, message, _ = await match_schedule_service.generate_seed(match_id, actor=actor)
            
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
                dialog = StationAssignmentDialog(
                    match=match,
                    on_submit=handle_confirm
                )
                await dialog.open()

        async def confirm_seating(match: Match):
            try:
                actor = await current_user_from_storage()
                await match_schedule_service.seat_match(match, actor=actor)
                await table_view.update_row_by_id(match.id)
            except PermissionError as e:
                with page_container:
                    ui.notify(str(e), color='negative')
            except ValueError as e:
                with page_container:
                    ui.notify(str(e), color='warning')

        async def on_start(match_id: int):
            match = await Match.get(id=match_id).prefetch_related('players', 'players__user')
            player_names = ', '.join(
                [p.user.username for p in match.players])

            async def handle_confirm(_):
                dialog.dialog.close()
                await confirm_starting(match)
            with page_container:
                dialog = ConfirmationDialog(
                    message=f'Are you sure you want to start match ID {match.id}?\n\n{player_names}',
                    on_confirm=handle_confirm
                )
                dialog.open()

        async def confirm_starting(match: Match):
            try:
                actor = await current_user_from_storage()
                await match_schedule_service.start_match(match, actor=actor)
                await table_view.update_row_by_id(match.id)
            except PermissionError as e:
                with page_container:
                    ui.notify(str(e), color='negative')
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
                dialog = MatchResultDialog(
                    match=match,
                    on_submit=handle_confirm
                )
                await dialog.open()

        async def confirm_finishing(match: Match):
            try:
                actor = await current_user_from_storage()
                await match_schedule_service.finish_match(match, actor=actor)
                await table_view.update_row_by_id(match.id)
            except PermissionError as e:
                with page_container:
                    ui.notify(str(e), color='negative')
            except ValueError as e:
                with page_container:
                    ui.notify(str(e), color='warning')

        async def on_confirm(match_id: int):
            match = await Match.get(id=match_id).prefetch_related('players', 'players__user')
            player_names = ', '.join(
                [p.user.username for p in match.players])

            async def handle_confirm(_):
                dialog.dialog.close()
                await confirm_confirming(match)
            with page_container:
                dialog = ConfirmationDialog(
                    message=f'Are you sure you want to confirm match ID {match.id}?\n\n{player_names}',
                    on_confirm=handle_confirm
                )
                dialog.open()

        async def confirm_confirming(match: Match):
            try:
                actor = await current_user_from_storage()
                await match_schedule_service.confirm_match(match, actor=actor)
                await table_view.update_row_by_id(match.id)
            except PermissionError as e:
                with page_container:
                    ui.notify(str(e), color='negative')
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

        async def on_assign_stations(match_id: int):
            match = await Match.get(id=match_id).prefetch_related('tournament', 'players', 'players__user')
            async def after_assign(_):
                await table_view.update_row_by_id(match_id)
            with page_container:
                dialog = StationAssignmentDialog(match=match, on_submit=after_assign)
                await dialog.open()

        async def submit_admin_match():
            async def after_submit():
                await table_view.refresh()
            with page_container:
                dialog = AdminMatchDialog(on_submit=after_submit)
                await dialog.open()

        extra_slots = {}

        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=True,
            submit_match_callback=submit_admin_match,
            on_edit=on_edit,
            on_generate_seed=on_generate_seed,
            on_seat=on_seat,
            on_start=on_start,
            on_finish=on_finish,
            on_confirm=on_confirm,
            on_edit_stream_room=on_edit_stream_room,
            on_assign_stations=on_assign_stations,
            extra_slots=extra_slots,
        )

        def on_tab_selected():
            background_tasks.create(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Schedule' else None)
