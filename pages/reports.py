import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

from nicegui import ui
from tortoise.functions import Count

from models import Match, Tournament


async def reports_page() -> None:
    """Admin page for viewing reports about match schedules and player activity."""
    with ui.row().style('width: 100%;'):
        ui.label('Tournament Reports').style('font-size: 2em; margin-bottom: 1em;')

    with ui.column().style('width: 100%;'):
        with ui.tabs().props('class="bg-primary text-white"').style('width: 100%') as tabs:
            ui.tab('Active Players Forecast', icon='show_chart')
            
        with ui.tab_panels(tabs, value='Active Players Forecast').style('width: 100%'):
            with ui.tab_panel('Active Players Forecast'):
                await player_activity_report()

async def get_match_date_range() -> Dict:
    """
    Get the earliest and latest dates from scheduled matches.
    [Currently unused - kept for potential future enhancements]
    
    Returns:
        Dict with min_date and max_date
    """
    from tortoise.functions import Min, Max
    
    # Find the earliest and latest scheduled matches
    earliest = await Match.all().annotate(min_date=Min('scheduled_at')).first().values('min_date')
    latest = await Match.all().annotate(max_date=Max('scheduled_at')).first().values('max_date')
    
    # Get the earliest scheduled_at date, or default to today
    min_date = None
    if earliest and earliest.get('min_date'):
        min_date = earliest['min_date'].date()
    
    # Get the latest scheduled_at date, or default to one month from today
    max_date = None
    if latest and latest.get('max_date'):
        max_date = latest['max_date'].date()
        # Add tournament duration to max_date to catch final matches
        max_date += timedelta(days=7)  # Add a week as buffer
    
    # If no matches in database, set reasonable defaults
    today = datetime.now().date()
    if not min_date:
        min_date = today
    if not max_date:
        max_date = today + timedelta(days=30)
        
    return {
        'min_date': min_date.isoformat(),
        'max_date': max_date.isoformat(),
    }

async def player_activity_report() -> None:
    """Shows a forecast of the number of active players at 5-minute intervals."""
    
    with ui.row().style('width: 100%'):
        ui.label('Active Players Forecast').classes('text-h5')
        
    with ui.row().style('width: 100%'):
        ui.label('''
            This report shows the predicted number of players who will have active matches at 5-minute intervals.
            An active match is determined by:
            - If seated_at and finished_at are set, the match is active between these times
            - If seated_at is not set, scheduled_at is used as the start time
            - If finished_at is not set, the tournament's average_match_duration is used to calculate the end time
        ''').style('white-space: pre-wrap')

    # Options for the report
    with ui.row():
        with ui.card().style('width: 100%').classes('q-pa-md'):
            with ui.row():
                hours_ahead = ui.number('Hours ahead to forecast', value=24, min=1, max=168).style('width: 200px')
                interval_minutes = ui.select(
                    ['5 minutes', '10 minutes', '15 minutes', '30 minutes', '60 minutes'], 
                    value='5 minutes',
                    label='Interval'
                ).style('width: 200px; margin-left: 20px')
                
            # Row for forecast start time info
            with ui.row():
                ui.label('Report will start from the current time').style('font-style: italic')
                
            with ui.row():
                forecast_button = ui.button('Generate Forecast from Current Time', icon='refresh')
                spinner = ui.spinner('dots').classes('ml-2')
                spinner.visible = False
                spinner.bind_visibility_from(forecast_button, 'loading')
    
    # Container for the chart
    chart_container = ui.card().style('width: 100%; min-height: 500px')

    # Container for peak times
    peaks_container = ui.card().style('width: 100%').classes('q-mb-md')

    # Container for the data table
    table_container = ui.card().style('width: 100%')

    async def generate_forecast():
        # Set button to loading state
        forecast_button.props('loading')
        
        try:
            # Clear previous content
            chart_container.clear()
            peaks_container.clear()
            table_container.clear()
            
            # Get interval in minutes
            interval_map = {
                '5 minutes': 5,
                '10 minutes': 10,
                '15 minutes': 15,
                '30 minutes': 30,
                '60 minutes': 60
            }
            interval_min = interval_map.get(interval_minutes.value, 5)
            
            # Get current time (rounded down to the nearest interval)
            now = datetime.now()
            # Ensure we're using an offset-naive datetime and round to the interval
            now = now.replace(minute=now.minute - now.minute % interval_min, second=0, microsecond=0, tzinfo=None)
            
            # Calculate intervals for the specified hours
            intervals = []
            interval_data = []
            end_time = now + timedelta(hours=hours_ahead.value)
            
            current_time = now
            loading_spinner = ui.spinner('dots')
            try:
                while current_time <= end_time:
                    intervals.append(current_time)
                    interval_data.append(await calculate_active_players_at_time(current_time))
                    current_time += timedelta(minutes=interval_min)
            finally:
                loading_spinner.delete()
            
            # Format for chart display
            time_labels = [t.strftime('%m-%d %H:%M') for t in intervals]
            player_counts = [d['active_players'] for d in interval_data]
            match_counts = [d['active_matches'] for d in interval_data]
            
            # Display chart
            with chart_container:
                ui.label('Active Players and Matches Forecast').classes('text-h6')
                
                # Create EChart configuration
                echart_option = {
                    'title': {
                        'text': 'Activity Forecast'
                    },
                    'tooltip': {
                        'trigger': 'axis',
                        'axisPointer': {
                            'type': 'cross',
                            'label': {
                                'backgroundColor': '#6a7985'
                            }
                        }
                    },
                    'legend': {
                        'data': ['Active Players', 'Active Matches']
                    },
                    'grid': {
                        'left': '3%',
                        'right': '4%',
                        'bottom': '3%',
                        'containLabel': True
                    },
                    'toolbox': {
                        'feature': {
                            'saveAsImage': {},
                            'dataZoom': {},
                            'dataView': {},
                            'restore': {}
                        }
                    },
                    'xAxis': {
                        'type': 'category',
                        'boundaryGap': False,
                        'data': time_labels
                    },
                    'yAxis': [
                        {
                            'type': 'value',
                            'name': 'Players',
                            'position': 'left'
                        },
                        {
                            'type': 'value',
                            'name': 'Matches',
                            'position': 'right'
                        }
                    ],
                    'series': [
                        {
                            'name': 'Active Players',
                            'type': 'line',
                            'yAxisIndex': 0,
                            'data': player_counts,
                            'smooth': True,
                            'lineStyle': {
                                'width': 2,
                                'color': '#1976D2'
                            },
                            'areaStyle': {
                                'color': 'rgba(25, 118, 210, 0.2)'
                            }
                        },
                        {
                            'name': 'Active Matches',
                            'type': 'line',
                            'yAxisIndex': 1,
                            'data': match_counts,
                            'smooth': True,
                            'lineStyle': {
                                'width': 2,
                                'color': '#FF5722'
                            },
                            'areaStyle': {
                                'color': 'rgba(255, 87, 34, 0.2)'
                            }
                        }
                    ]
                }
                
                # Display the chart using ui.echart
                chart = ui.echart(echart_option).style('width: 100%; height: 400px')
            
            # Find peak times
            with peaks_container:
                ui.label('Peak Activity Times').classes('text-h6')
                
                # Find top 5 peaks for players
                player_peaks = sorted(zip(intervals, player_counts), key=lambda x: x[1], reverse=True)[:5]
                match_peaks = sorted(zip(intervals, match_counts), key=lambda x: x[1], reverse=True)[:5]
                
                with ui.row():
                    with ui.column().classes('col-6'):
                        ui.label('Top 5 Player Peak Times:').classes('text-weight-bold')
                        for time, count in player_peaks:
                            ui.label(f"{time.strftime('%Y-%m-%d %H:%M')}: {count} players")
                            
                    with ui.column().classes('col-6'):
                        ui.label('Top 5 Match Peak Times:').classes('text-weight-bold')
                        for time, count in match_peaks:
                            ui.label(f"{time.strftime('%Y-%m-%d %H:%M')}: {count} matches")
            
            # Display table with data
            with table_container:
                ui.label('Forecast Data').classes('text-h6')
                
                columns = [
                    {'name': 'time', 'label': 'Time', 'field': 'time', 'sortable': True},
                    {'name': 'active_matches', 'label': 'Active Matches', 'field': 'active_matches', 'sortable': True},
                    {'name': 'active_players', 'label': 'Active Players', 'field': 'active_players', 'sortable': True},
                ]
                
                rows = [
                    {
                        'time': intervals[i].strftime('%Y-%m-%d %H:%M'),
                        'active_matches': match_counts[i],
                        'active_players': player_counts[i]
                    }
                    for i in range(len(intervals))
                ]
                
                # Create a table with search functionality
                with ui.row().style('width: 100%'):
                    ui.input(label='Search', placeholder='Type to search...').classes('w-full').bind_value_to(
                        table_search_model := {'value': ''}
                    ).on('input', lambda e: filter_table())
                
                table = ui.table(
                    columns=columns,
                    rows=rows,
                    pagination=25,
                    row_key='time'
                ).style('width: 100%')
                
                # Store original rows for filtering
                table_all_rows = rows.copy()
                
                # Function to filter table based on search input
                def filter_table():
                    search_term = table_search_model['value'].lower()
                    if not search_term:
                        table.rows = table_all_rows
                    else:
                        table.rows = [
                            row for row in table_all_rows
                            if search_term in row['time'].lower() or 
                               search_term in str(row['active_matches']).lower() or
                               search_term in str(row['active_players']).lower()
                        ]
                
        finally:
            # Reset button loading state
            forecast_button.props('loading=false')
    
    # Connect the button to the function
    forecast_button.on('click', generate_forecast)

async def calculate_active_players_at_time(check_time: datetime) -> Dict:
    """
    Calculate the number of active players at a specific time.
    
    Args:
        check_time: The time to check for active matches
        
    Returns:
        Dict with active_matches and active_players counts
    """
    # Initialize counters
    active_matches = 0
    active_players = 0
    
    # Get all tournaments for their match durations
    tournaments = {t.id: t for t in await Tournament.all()}
    
    # Ensure check_time is offset-naive (no timezone)
    # This is necessary because database times are usually stored as offset-naive
    if check_time.tzinfo is not None:
        check_time = check_time.replace(tzinfo=None)
    
    # Get all matches that could be active at the given time
    # This includes:
    # 1. Matches with seated_at ≤ check_time and finished_at > check_time
    # 2. Matches with seated_at ≤ check_time and no finished_at
    # 3. Matches with scheduled_at ≤ check_time and no seated_at
    matches = await Match.all().prefetch_related('tournament')
    
    for match in matches:
        # Skip matches with no scheduled time
        if not match.scheduled_at:
            continue
            
        # Determine the start time (seated_at or scheduled_at)
        start_time = match.seated_at if match.seated_at else match.scheduled_at
        
        # Ensure start_time is offset-naive for comparison
        if start_time and start_time.tzinfo is not None:
            start_time = start_time.replace(tzinfo=None)
        
        # Skip matches that haven't started yet
        if start_time and start_time > check_time:
            continue
            
        # Determine the end time (finished_at or calculated from tournament duration)
        if match.finished_at:
            end_time = match.finished_at
            # Ensure end_time is offset-naive for comparison
            if end_time.tzinfo is not None:
                end_time = end_time.replace(tzinfo=None)
        else:
            tournament = tournaments.get(match.tournament_id)
            if tournament and tournament.average_match_duration:
                end_time = start_time + timedelta(minutes=tournament.average_match_duration)
            else:
                # Default to 90 minutes if no duration is specified
                end_time = start_time + timedelta(minutes=90)
        
        # Check if the match is active at the given time
        if start_time <= check_time <= end_time:
            active_matches += 1
            
            # Count players based on tournament's players_per_match
            tournament = tournaments.get(match.tournament_id)
            if tournament:
                active_players += tournament.players_per_match
    
    return {
        'active_matches': active_matches,
        'active_players': active_players
    }