from nicegui import ui, events, app
from models import Match, User, Tournament, MatchPlayers
import asyncio
from datetime import datetime

def create() -> None:
    @ui.page('/player')
    def player_page() -> None:
        ui.label('Player Page').style('font-size: 2em; margin-bottom: 1em;')
        ui.label('This is the player dashboard where players can view their upcoming or in-progress matches, submit match results, and confirm matches assigned to them.')

        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            ui.label('You must be logged in to view this page.').style('color: red; font-weight: bold;')
            return

        # get matches for the logged-in player
        async def refresh():
            matches = await Match.filter(players__user__discord_id=discord_id).prefetch_related('tournament', 'players', 'players__user', 'stream_room', 'generated_seed').order_by('scheduled_at')
            rows = []
            for m in matches:
                player_names = ', '.join([p.user.username for p in m.players])
                rows.append({
                    'id': m.id,
                    'tournament': m.tournament.name if m.tournament else '',
                    'scheduled_at': m.scheduled_at.strftime('%Y-%m-%d %H:%M') if m.scheduled_at else '',
                    'players': player_names,
                    'stream_room': m.stream_room.name if m.stream_room else '',
                    'generated_seed': m.generated_seed.seed_url if m.generated_seed else ''
                })
            table.rows = rows
            table.update()

        async def submit_match():
            # Fetch users and tournaments for dropdowns
            users = await User.all().order_by('username')
            tournaments = await Tournament.all().order_by('name')

            now = datetime.now()
            default_date = now.strftime('%Y-%m-%d')
            default_time = now.strftime('%H:%M')

            with ui.dialog() as dialog, ui.card():
                # tournament selection
                selected_tournament = ui.select(label='Tournament', options={t.id: t.name for t in tournaments}, with_input=True)
                selected_opponent = ui.select(label='Opponent', options={u.id: u.username for u in users}, with_input=True)

                with ui.row().classes('justify-between items-center').style('margin-bottom: 1em;'):
                    with ui.input('Date', value=default_date) as date:
                        with ui.menu().props('no-parent-event') as menu:
                            with ui.date(value=default_date).bind_value(date):
                                with ui.row().classes('justify-end'):
                                    ui.button('Close', on_click=menu.close).props('flat')
                        with date.add_slot('append'):
                            ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')

                    with ui.input('Time', value=default_time) as time:
                        with ui.menu().props('no-parent-event') as menu:
                            with ui.time(value=default_time).bind_value(time):
                                with ui.row().classes('justify-end'):
                                    ui.button('Close', on_click=menu.close).props('flat')
                        with time.add_slot('append'):
                            ui.icon('access_time').on('click', menu.open).classes('cursor-pointer')

                async def submit():
                    opponent_id = selected_opponent.value
                    tournament_id = selected_tournament.value
                    date_value = date.value
                    time_value = time.value
                    # Validate all fields are filled
                    if not (opponent_id and tournament_id and date_value and time_value):
                        ui.notify('All fields are required.', color='warning')
                        return
                    # Convert YYYY-MM-DD and HH:SS to datetime
                    match_time = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
                    match = await Match.create(
                        tournament_id=tournament_id,
                        scheduled_at=match_time
                    )
                    await MatchPlayers.create(match=match, user=await User.get(discord_id=discord_id))
                    await MatchPlayers.create(match=match, user=await User.get(id=opponent_id))
                    ui.notify(f'Match submitted: Opponent={opponent_id}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
                    dialog.close()

                ui.button('Submit', on_click=submit)
                ui.button('Cancel', on_click=dialog.close)

            dialog.open()

        with ui.row():
            ui.button('Refresh', on_click=refresh)
            ui.button('Submit Match', on_click=submit_match)
        table = ui.table(
            columns=[
                {'name': 'id', 'label': 'ID', 'field': 'id'},
                {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
                {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
                {'name': 'players', 'label': 'Players', 'field': 'players'},
                {'name': 'stream_room', 'label': 'Stream Room', 'field': 'stream_room'},
                {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
            ],
            rows=[],
            row_key='id'
        ).style('margin-top: 1em;')

        # Refresh table on page load
        asyncio.create_task(refresh())
