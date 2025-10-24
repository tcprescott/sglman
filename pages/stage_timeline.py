"""Stage Timeline page - displays a daily calendar view of matches per stream room."""

import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict

from nicegui import app, ui

from models import Match, StreamRoom, Permissions, User


async def stage_timeline_tab():
    """Display a daily calendar view of matches organized by stream room."""
    discord_id = app.storage.user.get('discord_id', None)
    user = await User.get_or_none(discord_id=discord_id) if discord_id else None

    # Use internal state for the current date
    current_date = {'value': date.today()}

    with ui.column().style('width: 100%; padding: 1em;'):
        # Header with date navigation
        with ui.row().style('width: 100%; align-items: center; margin-bottom: 1em;'):
            prev_btn = ui.button(
                icon='chevron_left',
                on_click=lambda: None
            ).props('flat')

            date_label = ui.label(current_date['value'].strftime('%A, %B %d, %Y')).style(
                'font-size: 1.8em; font-weight: bold; margin: 0 1em;'
            )

            next_btn = ui.button(
                icon='chevron_right',
                on_click=lambda: None
            ).props('flat')

            today_btn = ui.button(
                'Today',
                on_click=lambda: None
            ).props('outline')

            ui.space()

            # Date picker
            with ui.input('Select Date', value=current_date['value'].strftime('%Y-%m-%d')) as date_input:
                with ui.menu().props('no-parent-event') as menu:
                    date_picker = ui.date(value=current_date['value'].strftime('%Y-%m-%d')).bind_value(date_input)
                    with ui.row().classes('justify-end'):
                        go_btn = ui.button('Go', on_click=lambda: menu.close())
                with date_input.add_slot('append'):
                    ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')

        # Refresh button
        refresh_btn = ui.button(icon='refresh', on_click=lambda: None).props('flat').style(
            'position: absolute; top: 80px; right: 20px;'
        )

        # Container for the timeline view
        timeline_container = ui.column().style('width: 100%;')

        async def load_timeline():
            """Load and render the timeline for the selected date."""
            timeline_container.clear()

            # Update date label
            date_label.text = current_date['value'].strftime('%A, %B %d, %Y')
            date_input.value = current_date['value'].strftime('%Y-%m-%d')

            # Fetch all active stream rooms
            stream_rooms = await StreamRoom.filter(is_active=True).order_by('name')

            if not stream_rooms:
                with timeline_container:
                    ui.label('No active stream rooms found.').style('color: gray; font-style: italic;')
                return

            # Fetch all matches for the selected date
            start_of_day = datetime.combine(current_date['value'], datetime.min.time())
            end_of_day = datetime.combine(current_date['value'], datetime.max.time())

            matches = await Match.filter(
                scheduled_at__gte=start_of_day,
                scheduled_at__lte=end_of_day
            ).prefetch_related(
                'tournament', 'stream_room', 'players', 'players__user',
                'commentators', 'commentators__user', 'trackers', 'trackers__user'
            ).order_by('scheduled_at')

            # Group matches by stream room
            matches_by_room: Dict[int, List[Match]] = {}
            unassigned_matches = []

            for match in matches:
                if match.stream_room_id:
                    if match.stream_room_id not in matches_by_room:
                        matches_by_room[match.stream_room_id] = []
                    matches_by_room[match.stream_room_id].append(match)
                else:
                    unassigned_matches.append(match)

            with timeline_container:
                # Display each stream room and its matches
                for room in stream_rooms:
                    room_matches = matches_by_room.get(room.id, [])

                    with ui.card().style('width: 100%; margin-bottom: 1em;'):
                        # Stream room header
                        with ui.row().style('width: 100%; align-items: center; background-color: #1976d2; color: white; padding: 0.5em; border-radius: 4px;'):
                            ui.label(room.name).style('font-size: 1.3em; font-weight: bold;')
                            if room.stream_url:
                                ui.link('Watch Stream', room.stream_url, new_tab=True).style(
                                    'margin-left: auto; color: white; text-decoration: underline;'
                                )
                            ui.label(f'{len(room_matches)} match{"es" if len(room_matches) != 1 else ""}').style(
                                'margin-left: 1em; opacity: 0.9;'
                            )

                        # Matches timeline
                        if room_matches:
                            with ui.column().style('width: 100%; padding: 0.5em;'):
                                for match in room_matches:
                                    render_match_card(match, user)
                        else:
                            ui.label('No matches scheduled').style(
                                'color: gray; font-style: italic; padding: 1em;'
                            )

                # Show unassigned matches if any
                if unassigned_matches:
                    with ui.card().style('width: 100%; margin-bottom: 1em;'):
                        with ui.row().style('width: 100%; align-items: center; background-color: #757575; color: white; padding: 0.5em; border-radius: 4px;'):
                            ui.label('Unassigned Matches').style('font-size: 1.3em; font-weight: bold;')
                            ui.label(f'{len(unassigned_matches)} match{"es" if len(unassigned_matches) != 1 else ""}').style(
                                'margin-left: auto; opacity: 0.9;'
                            )

                        with ui.column().style('width: 100%; padding: 0.5em;'):
                            for match in unassigned_matches:
                                render_match_card(match, user)

            if not matches:
                with timeline_container:
                    ui.label('No matches scheduled for this date.').style(
                        'color: gray; font-style: italic; text-align: center; padding: 2em;'
                    )

        def render_match_card(match: Match, user: User = None):
                """Render a single match card in the timeline."""
                # Determine match status
                status_color = '#4CAF50' if match.is_finished else '#2196F3' if match.is_seated else '#9E9E9E'
                status_text = 'Finished' if match.is_finished else 'In Progress' if match.is_seated else 'Scheduled'

                with ui.card().style('width: 100%; margin-bottom: 0.5em; border-left: 4px solid ' + status_color):
                    with ui.row().style('width: 100%; align-items: center;'):
                        # Time
                        time_str = match.scheduled_at.strftime('%H:%M') if match.scheduled_at else 'TBD'
                        ui.label(time_str).style('font-size: 1.2em; font-weight: bold; min-width: 60px;')

                        # Status badge
                        ui.badge(status_text, color=status_color).style('margin-left: 0.5em;')

                        # Tournament name
                        if match.tournament:
                            ui.label(match.tournament.name).style('margin-left: 1em; font-weight: 500;')

                        ui.space()

                        # Match ID (clickable for admins)
                        if user and user.permission >= Permissions.TOURNAMENT_ADMIN:
                            ui.link(f'Match #{match.id}', '/admin?tab=Schedule').style(
                                'color: #1976d2; text-decoration: underline;'
                            )
                        else:
                            ui.label(f'Match #{match.id}').style('color: gray;')

                    # Players
                    with ui.row().style('width: 100%; margin-top: 0.5em;'):
                        ui.icon('sports_esports').style('margin-right: 0.5em;')
                        player_names = [p.user.preferred_name for p in match.players]
                        ui.label(' vs '.join(player_names) if player_names else 'No players assigned').style(
                            'font-weight: 500;'
                        )

                    # Commentators (if any)
                    if match.commentators:
                        approved_commentators = [c for c in match.commentators if c.approved]
                        pending_commentators = [c for c in match.commentators if not c.approved]

                        with ui.row().style('width: 100%; margin-top: 0.3em;'):
                            ui.icon('mic').style('margin-right: 0.5em;')
                            commentator_names = [c.user.preferred_name for c in approved_commentators]
                            if commentator_names:
                                ui.label(', '.join(commentator_names)).style('color: #4CAF50;')
                            if pending_commentators:
                                pending_names = [c.user.preferred_name for c in pending_commentators]
                                ui.label(f' ({", ".join(pending_names)} pending)').style('color: #FF9800; font-style: italic;')

                    # Trackers (if any)
                    if match.trackers:
                        approved_trackers = [t for t in match.trackers if t.approved]
                        pending_trackers = [t for t in match.trackers if not t.approved]

                        with ui.row().style('width: 100%; margin-top: 0.3em;'):
                            ui.icon('track_changes').style('margin-right: 0.5em;')
                            tracker_names = [t.user.preferred_name for t in approved_trackers]
                            if tracker_names:
                                ui.label(', '.join(tracker_names)).style('color: #4CAF50;')
                            if pending_trackers:
                                pending_names = [t.user.preferred_name for t in pending_trackers]
                                ui.label(f' ({", ".join(pending_names)} pending)').style('color: #FF9800; font-style: italic;')

                    # Comment (if any)
                    if match.comment:
                        with ui.row().style('width: 100%; margin-top: 0.3em;'):
                            ui.icon('comment').style('margin-right: 0.5em;')
                            ui.label(match.comment).style('font-style: italic; color: #666;')

        # Define button actions
        async def go_prev_day():
            current_date['value'] = current_date['value'] - timedelta(days=1)
            await load_timeline()

        async def go_next_day():
            current_date['value'] = current_date['value'] + timedelta(days=1)
            await load_timeline()

        async def go_today():
            current_date['value'] = date.today()
            await load_timeline()

        async def go_to_date():
            try:
                new_date = datetime.strptime(date_input.value, '%Y-%m-%d').date()
                current_date['value'] = new_date
                await load_timeline()
            except ValueError:
                ui.notify('Invalid date format', color='warning')

        # Bind button actions
        prev_btn.on('click', lambda: asyncio.create_task(go_prev_day()))
        next_btn.on('click', lambda: asyncio.create_task(go_next_day()))
        today_btn.on('click', lambda: asyncio.create_task(go_today()))
        go_btn.on('click', lambda: asyncio.create_task(go_to_date()))
        refresh_btn.on('click', lambda: asyncio.create_task(load_timeline()))

        # Initial load
        await load_timeline()
