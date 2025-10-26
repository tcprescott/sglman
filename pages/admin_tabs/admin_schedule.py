"""Admin Schedule Management Page"""

import asyncio
from datetime import datetime
from typing import Dict

from nicegui import ui

from application.seedgen import RANDOMIZERS
from discordbot.bot import send_dm
from models import GeneratedSeeds, Match
from theme.dialog import ConfirmationDialog, MatchDialog
from theme.dialog.stream_room_dialog import StreamRoomDialog
from theme.tables.match import MatchTableView

# per-match locks to avoid concurrent seed generation for the same match
_seed_locks: Dict[int, asyncio.Lock] = {}


def admin_schedule_page() -> None:
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
            # ensure only one generator runs per match id at a time
            lock = _seed_locks.get(match_id)
            if lock is None:
                lock = asyncio.Lock()
                _seed_locks[match_id] = lock

            if lock.locked():
                # another generation is in progress for this row; skip and refresh the row to clear client spinner
                await table_view.update_row_by_id(match_id)
                return

            async with lock:
                try:
                    match = await Match.get(id=match_id).prefetch_related('tournament', 'players', 'players__user')
                    # sanity check: if a seed has already been generated for this match, skip
                    if match.generated_seed:
                        ui.notify('A seed has already been generated for this match.', color='warning')
                        table_view.update_row_by_id(match_id)
                        return
                    if match.tournament.seed_generator:
                        seed_generator = RANDOMIZERS.get(match.tournament.seed_generator)
                        if seed_generator:
                            seed_url = await seed_generator()
                            match.generated_seed = await GeneratedSeeds.create(
                                tournament=match.tournament,
                                seed_url=seed_url,
                                seed_info=f"Generated seed for match {match.id}"
                            )
                            await match.save()
                            for player in match.players:
                                if player.user.discord_id:
                                    dm_message = f"Hello {player.user.preferred_name},\n\n"
                                    dm_message += f"A seed has been generated for your upcoming match (ID: {match.id}) in the tournament '{match.tournament.name}'.\n\n"
                                    dm_message += f"{seed_url}\n\n"
                                    dm_message += "Good luck and have fun!"
                                    success, response = await send_dm(player.user.discord_id, dm_message)
                                    if not success:
                                        ui.notify(f"Failed to send DM to {player.user.username}: {response}", color='negative')

                            ui.notify(f'Seed generated successfully for match ID {match.id}.', color='positive')
                        else:
                            ui.notify(f"Seed generator '{match.tournament.seed_generator}' not found.", color='negative')
                finally:
                    # refresh the row so client clears spinner. Keep the lock dict entry for reuse.
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
            match.seated_at = datetime.now()
            await match.save()
            await table_view.update_row_by_id(match.id)

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
            match.finished_at = datetime.now()
            await match.save()
            await table_view.update_row_by_id(match.id)

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
