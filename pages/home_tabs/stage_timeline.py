"""Stage Timeline page - displays a daily calendar view of matches per stream room."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nicegui import app, background_tasks, ui

from application.services import MatchService
from application.utils.timezone import format_eastern_time
from models import Match, Permissions, User


async def stage_timeline_tab():
    """Display a daily calendar view of matches organized by stream room."""
    discord_id = app.storage.user.get('discord_id', None)
    user = await User.get_or_none(discord_id=discord_id) if discord_id else None
    
    # Initialize service
    match_service = MatchService()

    # Use internal state for the current date (based on US/Eastern timezone)
    eastern = ZoneInfo('US/Eastern')
    today_eastern = datetime.now(eastern).date()
    current_date = {'value': today_eastern}

    with ui.column().classes('full-width-column'):
        # Header with date navigation
        with ui.row().classes('timeline-header'):
            prev_btn = ui.button(
                icon='chevron_left',
                on_click=lambda: None
            ).props('flat')

            date_label = ui.label(current_date['value'].strftime('%A, %B %d, %Y')).classes('large-title')

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
        refresh_btn = ui.button(icon='refresh', on_click=lambda: None).props('flat').classes('refresh-button')

        # Container for the timeline view
        timeline_container = ui.column().classes('timeline-container')

        async def load_timeline():
            """Load and render the timeline for the selected date."""
            timeline_container.clear()

            # Update date label
            date_label.text = current_date['value'].strftime('%A, %B %d, %Y')
            date_input.value = current_date['value'].strftime('%Y-%m-%d')

            # Fetch matches for the selected date using service
            matches = await match_service.get_matches_for_date(
                target_date=current_date['value'],
                exclude_finished=True,
                require_stream_room=True
            )

            if not matches:
                with timeline_container:
                    ui.label('No matches scheduled for this date.').classes('empty-state')
                return

            # Group matches by stream room using service
            matches_by_room = await match_service.group_matches_by_stream_room(matches)

            # Sort rooms by name
            sorted_rooms = sorted(matches_by_room.items(), key=lambda x: x[1][0].name)

            with timeline_container:
                # Display each stream room and its matches
                for room_id, (room, room_matches) in sorted_rooms:
                    with ui.card().classes('card-full-width'):
                        # Stream room header
                        with ui.row().classes('room-header'):
                            ui.label(room.name).classes('room-name')
                            if room.stream_url:
                                ui.link('Watch Stream', room.stream_url, new_tab=True).classes('room-link')
                            ui.label(f'{len(room_matches)} match{"es" if len(room_matches) != 1 else ""}').classes('room-match-count')

                        # Matches timeline
                        with ui.column().classes('column-spacing'):
                            for match in room_matches:
                                render_match_card(match, user)

        def render_match_card(match: Match, user: User = None):
            """Render a single match card in the timeline."""
            # Determine match status
            status_color = '#4CAF50' if match.is_finished else '#2196F3' if match.is_seated else '#9E9E9E'
            status_text = 'Finished' if match.is_finished else 'In Progress' if match.is_seated else 'Scheduled'
            
            # Determine border class
            border_class = 'border-left-green' if match.is_finished else 'border-left-blue' if match.is_seated else 'border-left-gray'

            with ui.card().classes(f'match-card {border_class}'):
                with ui.row().classes('full-width'):
                    # Time (displayed in Eastern timezone)
                    time_str = format_eastern_time(match.scheduled_at) if match.scheduled_at else 'TBD'
                    ui.label(time_str).classes('match-time')

                    # Status badge
                    ui.badge(status_text, color=status_color).classes('match-badge')

                    # Tournament name
                    if match.tournament:
                        ui.label(match.tournament.name).classes('match-tournament')

                    ui.space()

                    # Match ID (clickable for admins)
                    if user and user.permission >= Permissions.TOURNAMENT_ADMIN:
                        ui.link(f'Match #{match.id}', '/admin?tab=Schedule').classes('text-link')
                    else:
                        ui.label(f'Match #{match.id}').classes('text-gray')

                # Players
                with ui.row().classes('match-details'):
                    ui.icon('sports_esports').classes('icon-spacing')
                    player_names = [p.user.preferred_name for p in match.players]
                    ui.label(' vs '.join(player_names) if player_names else 'No players assigned').classes('match-players')

                # Commentators (if any)
                    if match.commentators:
                        approved_commentators = [c for c in match.commentators if c.approved]
                        if approved_commentators:
                            with ui.row().classes('match-details-nested'):
                                ui.icon('mic').classes('icon-spacing')
                                commentator_names = [c.user.preferred_name for c in approved_commentators]
                                ui.label(', '.join(commentator_names)).classes('text-success')

                # Trackers (if any)
                    if match.trackers:
                        approved_trackers = [t for t in match.trackers if t.approved]
                        if approved_trackers:
                            with ui.row().classes('match-details-nested'):
                                ui.icon('track_changes').classes('icon-spacing')
                                tracker_names = [t.user.preferred_name for t in approved_trackers]
                                ui.label(', '.join(tracker_names)).classes('text-success')

                    # # Comment (if any)
                    # if match.comment:
                    #     with ui.row().classes('match-details-nested'):
                    #         ui.icon('comment').classes('icon-spacing')
                    #         ui.label(match.comment).classes('text-italic')

        # Define button actions
        async def go_prev_day():
            current_date['value'] = current_date['value'] - timedelta(days=1)
            await load_timeline()

        async def go_next_day():
            current_date['value'] = current_date['value'] + timedelta(days=1)
            await load_timeline()

        async def go_today():
            current_date['value'] = datetime.now(eastern).date()
            await load_timeline()

        async def go_to_date():
            try:
                new_date = datetime.strptime(date_input.value, '%Y-%m-%d').date()
                current_date['value'] = new_date
                await load_timeline()
            except ValueError:
                ui.notify('Invalid date format', color='warning')

        # Bind button actions
        prev_btn.on('click', lambda: background_tasks.create(go_prev_day()))
        next_btn.on('click', lambda: background_tasks.create(go_next_day()))
        today_btn.on('click', lambda: background_tasks.create(go_today()))
        go_btn.on('click', lambda: background_tasks.create(go_to_date()))
        refresh_btn.on('click', lambda: background_tasks.create(load_timeline()))

        # Initial load
        await load_timeline()
