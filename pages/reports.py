import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

import pytz
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

    # Options for the report
    with ui.row():
        with ui.card().style('width: 100%').classes('q-pa-md'):
            with ui.row():
                forecast_period = ui.select(
                    [
                        'Whole Event (Thursday - Sunday)',
                        'Thursday',
                        'Friday',
                        'Saturday',
                        'Sunday',
                    ],
                    value='Thursday',
                    label='Forecast Period'
                ).style('width: 400px')
                
            # Row for forecast period info
            with ui.row():
                ui.label('Select a predefined forecast period').style('font-style: italic')
                
            with ui.row():
                forecast_button = ui.button('Generate Forecast', icon='refresh')
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
            
            # Setup timezone
            eastern_tz = pytz.timezone('US/Eastern')
            
            # Determine date range and interval based on selected forecast period
            if forecast_period.value == 'Whole Event (Thursday - Sunday)':
                # Fixed date range for the whole event with 60-minute intervals
                now = eastern_tz.localize(datetime(2025, 10, 24, 8, 0, 0))  # Oct 24, 2025 at 8AM ET
                end_time = eastern_tz.localize(datetime(2025, 10, 27, 22, 0, 0))  # Oct 27, 2025 at 10PM ET
                interval_min = 60  # 60-minute intervals for the whole event
            else:
                datemap = {
                    'Thursday': (datetime(2025, 10, 24, 8, 0, 0, tzinfo=eastern_tz), datetime(2025, 10, 25, 0, 0, 0, tzinfo=eastern_tz)),
                    'Friday': (datetime(2025, 10, 25, 8, 0, 0, tzinfo=eastern_tz), datetime(2025, 10, 26, 0, 0, 0, tzinfo=eastern_tz)),
                    'Saturday': (datetime(2025, 10, 26, 8, 0, 0, tzinfo=eastern_tz), datetime(2025, 10, 27, 0, 0, 0, tzinfo=eastern_tz)),
                    'Sunday': (datetime(2025, 10, 27, 8, 0, 0, tzinfo=eastern_tz), datetime(2025, 10, 28, 0, 0, 0, tzinfo=eastern_tz)),
                }
                now = datemap.get(forecast_period.value, (datetime.now(), datetime.now() + timedelta(hours=24)))[0]
                # Round to nearest 15 minutes and localize to Eastern timezone
                now = datetime(year=now.year, month=now.month, day=now.day)
                now = eastern_tz.localize(now)
                end_time = now + timedelta(hours=24)
                interval_min = 15  # 15-minute intervals for next 24 hours
            
            # Calculate intervals for the specified period
            intervals = []
            interval_data = []
            
            current_time = now
            loading_spinner = ui.spinner('dots')
            try:
                while current_time <= end_time:
                    intervals.append(current_time)
                    interval_data.append(await calculate_active_players_at_time(current_time))
                    current_time += timedelta(minutes=interval_min)
            finally:
                loading_spinner.delete()
            
            # Format for chart display - include ET timezone indicator
            time_labels = [t.strftime('%m-%d %H:%M ET') for t in intervals]
            player_counts = [d['active_players'] for d in interval_data]
            max_player_counts = [60] * len(intervals)  # Static value of 60 for max players
            
            # Display chart with period-specific title
            with chart_container:
                if forecast_period.value == 'Whole Event (Thursday - Sunday)':
                    ui.label('Active Players and Matches Forecast - Whole Event').classes('text-h6')
                else:
                    ui.label('Active Players and Matches Forecast - Next 24 Hours').classes('text-h6')
                
                # Create EChart configuration
                # Set chart title based on forecast period
                title_text = 'Activity Forecast - ' + ('Whole Event' if forecast_period.value.startswith('Whole Event') else 'Next 24 Hours')
                
                echart_option = {
                    'title': {
                        'text': title_text
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
                        'data': ['Active Players', 'Max Players']
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
                            'name': 'Max Players',
                            'type': 'line',
                            'yAxisIndex': 0,
                            'data': max_player_counts,
                            'smooth': False,
                            'lineStyle': {
                                'width': 2,
                                'color': '#FF0000',
                                'type': 'dashed'
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
                
                with ui.row():
                    with ui.column().classes('col-12'):
                        ui.label('Top 5 Player Peak Times:').classes('text-weight-bold')
                        for time, count in player_peaks:
                            ui.label(f"{time.strftime('%Y-%m-%d %H:%M ET')}: {count} players")
            
            # Display table with data
            with table_container:
                ui.label('Forecast Data').classes('text-h6')
                
                columns = [
                    {'name': 'time', 'label': 'Time', 'field': 'time', 'sortable': True},
                    {'name': 'active_players', 'label': 'Active Players', 'field': 'active_players', 'sortable': True},
                ]
                
                rows = [
                    {
                        'time': intervals[i].strftime('%Y-%m-%d %H:%M ET'),
                        'active_players': player_counts[i],
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
                               search_term in str(row['active_players']).lower() or
                               search_term in str(row['max_players']).lower()
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
    active_players = 0
    
    # Note: We assume that match.scheduled_at values are already in US/Eastern timezone
    
    # Set up timezone
    eastern_tz = pytz.timezone('US/Eastern')
    
    # Convert check_time to US/Eastern timezone
    # If check_time has no timezone (is naive), assume it's in US/Eastern
    if check_time.tzinfo is None:
        check_time = eastern_tz.localize(check_time)
    else:
        check_time = check_time.astimezone(eastern_tz)
    
    # Get all matches that could be active at the given time
    # This includes:
    # 1. Matches with seated_at ≤ check_time and finished_at > check_time
    # 2. Matches with seated_at ≤ check_time and no finished_at
    # 3. Matches with scheduled_at ≤ check_time and no seated_at
    # Exclude matches with a stream_room set
    matches = await Match.filter(stream_room=None).prefetch_related('tournament', 'players')
    
    for match in matches:
        # Skip matches with no scheduled time
        if not match.scheduled_at:
            continue
            
        # Determine the start time (seated_at or scheduled_at)
        if match.seated_at:
            # Convert seated_at to US/Eastern timezone
            if match.seated_at.tzinfo is None:
                start_time = eastern_tz.localize(match.seated_at)
            else:
                start_time = match.seated_at.astimezone(eastern_tz)
        else:
            # Use scheduled_at if seated_at is not available
            # Assume scheduled_at is already in US/Eastern timezone
            if match.scheduled_at.tzinfo is None:
                # If naive datetime, just use it directly as it's already Eastern time
                start_time = eastern_tz.localize(match.scheduled_at)
            else:
                # If it has a timezone, assume it's correct but standardize to US/Eastern
                # start_time = match.scheduled_at.astimezone(eastern_tz)
                start_time = match.scheduled_at.replace(tzinfo=eastern_tz)

        # Skip matches that haven't started yet
        if start_time > check_time:
            continue
            
        # Determine the end time (finished_at or calculated from tournament duration)
        if match.finished_at:
            # Convert finished_at to US/Eastern timezone
            if match.finished_at.tzinfo is None:
                end_time = eastern_tz.localize(match.finished_at)
            else:
                end_time = match.finished_at.astimezone(eastern_tz)
        else:
            # Use the prefetched tournament relation directly
            if match.tournament and match.tournament.average_match_duration:
                end_time = start_time + timedelta(minutes=match.tournament.average_match_duration)
            else:
                # Default to 90 minutes if no duration is specified
                end_time = start_time + timedelta(minutes=90)
        
        # Check if the match is active at the given time
        if start_time <= check_time <= end_time:
            active_players += len(match.players)
    
    return {
        'active_players': active_players
    }