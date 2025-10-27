"""Admin Reports Page"""

from nicegui import ui

from application.services import ReportsService


async def reports_page() -> None:
    """Admin page for viewing reports about match schedules and player activity."""
    
    # Initialize service
    reports_service = ReportsService()
    
    with ui.column().classes('page-container-wide'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Reports').classes('page-title')
        
        ui.separator().classes('separator-spacing')

        await player_activity_report(reports_service)


async def player_activity_report(reports_service: ReportsService) -> None:
    """Shows a forecast of the number of active players at intervals."""

    with ui.row().classes('full-width'):
        ui.label('Active Players Forecast').classes('text-h5')

    # Options for the report
    with ui.row():
        with ui.card().classes('full-width q-pa-md'):
            with ui.row():
                forecast_period = ui.select(
                    reports_service.FORECAST_PERIODS,
                    value=reports_service.DEFAULT_FORECAST_PERIOD,
                    label='Forecast Period'
                ).classes('control-width')
                
            # Row for forecast period info
            with ui.row():
                ui.label('Select a predefined forecast period').classes('italic-note')
                
            with ui.row():
                forecast_button = ui.button('Generate Forecast', icon='refresh')
                spinner = ui.spinner('dots').classes('ml-2')
                spinner.visible = False
                spinner.bind_visibility_from(forecast_button, 'loading')
    
    # Container for the chart
    chart_container = ui.card().classes('chart-container')

    # Container for peak times
    peaks_container = ui.card().classes('full-width q-mb-md')

    # Container for the data table
    table_container = ui.card().classes('full-width')

    async def generate_forecast():
        # Set button to loading state
        forecast_button.props('loading')
        
        try:
            # Clear previous content
            chart_container.clear()
            peaks_container.clear()
            table_container.clear()
            
            # Generate forecast using service
            forecast_data = await reports_service.generate_player_activity_forecast(forecast_period.value)
            
            # Extract data
            intervals = forecast_data['intervals']
            player_counts = forecast_data['player_counts']
            
            # Format for chart display - include ET timezone indicator
            time_labels = [t.strftime('%m-%d %H:%M ET') for t in intervals]
            max_player_counts = [60] * len(intervals)  # Static value of 60 for max players
            
            # Display chart with period-specific title
            with chart_container:
                ui.label(f'Active Players Forecast - {forecast_period.value}').classes('text-h6')
                

                echart_option = {
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
                ui.echart(echart_option).classes('chart-height')
            
            # Find peak times using service
            with peaks_container:
                ui.label('Peak Activity Times').classes('text-h6')
                
                # Get top 5 peaks from service
                player_peaks = reports_service.get_peak_times(intervals, player_counts, top_n=5)
                
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
                with ui.row().classes('full-width'):
                    ui.input(label='Search', placeholder='Type to search...').classes('w-full').bind_value_to(
                        table_search_model := {'value': ''}
                    ).on('input', lambda e: filter_table())
                
                table = ui.table(
                    columns=columns,
                    rows=rows,
                    pagination=25,
                    row_key='time'
                ).classes('full-width')
                
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
                               search_term in str(row['active_players']).lower()
                        ]
                
        finally:
            # Reset button loading state
            forecast_button.props('loading=false')
    
    # Connect the button to the function
    forecast_button.on('click', generate_forecast)
