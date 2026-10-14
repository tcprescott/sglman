"""Stage Timeline page - displays a daily calendar view of matches per stage."""

import asyncio
from datetime import datetime, timedelta

from nicegui import app, ui

from application.services import AuthService, MatchService, get_user_from_discord_id
from application.utils.safe_url import http_url_or_empty
from application.utils.timezone import format_local_time, today_local
from application.utils.twitch_embed import twitch_channel
from models import Match, User
from pages.admin_tabs.links import SCHEDULE, admin_url
from theme.empty_state import empty_state
from theme.help import help_icon
from theme.menu import menu_action, more_menu
from theme.realtime import register_view
from theme.twitch_theater import NowPlaying, TwitchTheater


async def stage_timeline_tab():
    """Display a daily calendar view of matches organized by stage."""
    discord_id = app.storage.user.get('discord_id', None)
    user = await get_user_from_discord_id(discord_id) if discord_id else None
    board_scope = await AuthService.schedule_board_scope(user)

    match_service = MatchService()

    # "Today" is the viewer's today, not UTC's — at 21:00 in New York it is
    # already tomorrow in London, and the timeline must open on the day the
    # reader means.
    current_date = {'value': today_local()}

    # `page-container`, like the view switcher above it: `full-width-column`
    # padded this view 16px in from the switcher's left edge.
    with ui.column().classes('page-container'):
        with ui.row().classes('timeline-header'):
            # Keep the chevrons flanking the date as one unit so they never split
            # across lines when the row wraps on a narrow (phone) viewport.
            with ui.row().classes('timeline-nav items-center no-wrap'):
                prev_btn = ui.button(icon='chevron_left').props('outline').classes('timeline-tool') \
                    .tooltip('Previous day')
                with ui.element('div').classes('timeline-date'):
                    date_long = ui.label().classes('gt-xs')
                    date_short = ui.label().classes('xs')
                next_btn = ui.button(icon='chevron_right').props('outline').classes('timeline-tool') \
                    .tooltip('Next day')

            with ui.row().classes('timeline-tools items-center no-wrap'):
                today_btn = ui.button('Today').props('outline no-caps').classes('timeline-tool')
                with ui.button(icon='edit_calendar').props('outline').classes('timeline-tool') \
                        .tooltip('Pick a date'):
                    with ui.menu() as date_menu:
                        date_picker = ui.date()
                ui.space()
                refresh_btn = ui.button(icon='refresh').props('flat round color=primary') \
                    .tooltip('Refresh')
                await help_icon('on-air', 'watch-page', user=user)

        theater = TwitchTheater(on_change=lambda: paint_watch_buttons())
        timeline_container = ui.column().classes('timeline-container')
        watch_buttons: dict[int, ui.button] = {}

        def now_playing(stage, stage_matches, channel: str) -> NowPlaying:
            current = next((m for m in stage_matches if m.is_seated and not m.is_finished), None)
            return NowPlaying(
                stage_id=stage.id,
                stage_name=stage.name,
                channel=channel,
                stream_url=http_url_or_empty(stage.stream_url),
                time=format_local_time(current.scheduled_at) if current and current.scheduled_at else '',
                players=' vs '.join(p.user.preferred_name for p in current.players) if current else '',
                tournament=current.tournament.name if current and current.tournament else '',
            )

        def paint_watch_buttons():
            for stage_id, button in watch_buttons.items():
                on = theater.is_watching(stage_id)
                button.text = 'Watching' if on else 'Watch'
                button.props(f'aria-pressed={"true" if on else "false"}')
                if on:
                    button.props(remove='outline', add='unelevated')
                else:
                    button.props(remove='unelevated', add='outline')

        async def load_timeline():
            """Load and render the timeline for the selected date."""
            timeline_container.clear()
            watch_buttons.clear()

            day = current_date['value']
            date_long.text = day.strftime('%A, %B %d, %Y')
            date_short.text = day.strftime('%a, %b %d, %Y')
            date_picker.value = day.strftime('%Y-%m-%d')

            matches = await match_service.get_matches_for_date(
                target_date=current_date['value'],
                exclude_finished=True,
                require_stage=True
            )

            if not matches:
                with timeline_container:
                    empty_state('No matches scheduled for this date.')
                return

            matches_by_stage = await match_service.group_matches_by_stage(matches)

            sorted_stages = sorted(matches_by_stage.items(), key=lambda x: x[1][0].name)

            watched = None
            with timeline_container:
                for _stage_id, (stage, stage_matches) in sorted_stages:
                    channel = twitch_channel(stage.stream_url)
                    if channel and theater.is_watching(stage.id):
                        watched = now_playing(stage, stage_matches, channel)
                    with ui.card().classes('card-full-width'):
                        with ui.row().classes('stage-header no-wrap'):
                            with ui.column().classes('stage-title'):
                                ui.label(stage.name).classes('stage-name')
                                ui.label(f'{len(stage_matches)} match{"es" if len(stage_matches) != 1 else ""}').classes('stage-match-count')
                            if channel and theater.available:
                                watch_buttons[stage.id] = ui.button(
                                    'Watch', icon='play_arrow',
                                    on_click=lambda s=stage, m=stage_matches, c=channel: theater.watch(now_playing(s, m, c)),
                                ).props('outline no-caps').classes('stage-watch')
                            elif http_url_or_empty(stage.stream_url):
                                with ui.link(target=http_url_or_empty(stage.stream_url), new_tab=True).classes('stage-link'):
                                    ui.label('Open stream')
                                    ui.icon('open_in_new', size='16px')

                        with ui.column().classes('column-spacing'):
                            for match in stage_matches:
                                render_match_card(match, user)
            if watched:
                theater.refresh(watched)
            paint_watch_buttons()

        def render_match_card(match: Match, user: User = None):
            """Render a single match card in the timeline."""
            status_text = 'Finished' if match.is_finished else 'In Progress' if match.is_seated else 'Scheduled'
            chip_class = 'wiz-chip--ok' if match.is_finished else 'wiz-chip--live' if match.is_seated else 'wiz-chip--neutral'
            player_names = [p.user.preferred_name for p in match.players]
            players = ' vs '.join(player_names) if player_names else 'No players assigned'

            with ui.card().classes('match-card'):
                with ui.row().classes('match-card-top items-center no-wrap'):
                    time_str = format_local_time(match.scheduled_at) if match.scheduled_at else 'TBD'
                    ui.label(time_str).classes('match-time')
                    ui.label(status_text).classes(f'wiz-chip {chip_class}')
                    ui.space()
                    # Only where the board can actually show this match: a TA or
                    # CC's board is narrowed to their own tournaments, and an
                    # equipment manager or volunteer coordinator has no board.
                    if board_scope is None or match.tournament_id in board_scope:
                        with more_menu(players):
                            menu_action(
                                'calendar_month', 'Open in Schedule',
                                lambda m=match: ui.navigate.to(admin_url(SCHEDULE, match_id=m.id)),
                            )

                ui.label(players).classes('match-players')
                if match.tournament:
                    ui.label(match.tournament.name).classes('match-tournament')

                approved_commentators = [c for c in (match.commentators or []) if c.approved]
                if approved_commentators:
                    with ui.row().classes('match-crew no-wrap'):
                        ui.icon('mic')
                        ui.label(', '.join(c.user.preferred_name for c in approved_commentators))

                approved_trackers = [t for t in (match.trackers or []) if t.approved]
                if approved_trackers:
                    with ui.row().classes('match-crew no-wrap'):
                        ui.icon('track_changes')
                        ui.label(', '.join(t.user.preferred_name for t in approved_trackers))

        async def go_prev_day():
            current_date['value'] = current_date['value'] - timedelta(days=1)
            await load_timeline()

        async def go_next_day():
            current_date['value'] = current_date['value'] + timedelta(days=1)
            await load_timeline()

        async def go_today():
            current_date['value'] = today_local()
            await load_timeline()

        async def go_to_date(value: str | None):
            if not value:
                return
            try:
                new_date = datetime.strptime(value or '', '%Y-%m-%d').date()
            except ValueError:
                ui.notify('Invalid date format', color='warning')
                return
            date_menu.close()
            # load_timeline writes the picker back, which fires this again.
            if new_date == current_date['value']:
                return
            current_date['value'] = new_date
            await load_timeline()

        # Bind button actions. Return the coroutine so NiceGUI awaits it in the
        # button's slot context — a bare background task has no slot, so
        # go_to_date's ui.notify (outside the container) would raise.
        prev_btn.on('click', lambda: go_prev_day())
        next_btn.on('click', lambda: go_next_day())
        today_btn.on('click', lambda: go_today())
        date_picker.on_value_change(lambda e: go_to_date(e.value))
        refresh_btn.on('click', lambda: load_timeline())

        # Live updates: reload when any match changes, debounced so a multi-step
        # action (e.g. create with players + crew) triggers at most one rebuild.
        reload_token = {'n': 0}

        async def on_remote_change(match_id, change_type):
            reload_token['n'] += 1
            mine = reload_token['n']
            await asyncio.sleep(0.5)
            if mine == reload_token['n']:
                await load_timeline()

        register_view(on_remote_change)

        await load_timeline()
