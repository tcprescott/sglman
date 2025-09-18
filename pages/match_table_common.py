from theme.match_table import MatchTable
from nicegui import ui
from models import Match
from datetime import datetime
import asyncio

def render_match_table(columns, get_query, admin_controls=False, extra_slots=None, submit_match_callback=None):

    async def refresh():
        match_query = get_query()
        if show_upcoming_checkbox.value:
            match_query = match_query.filter(finished_at__isnull=True)
        all_matches = await match_query.prefetch_related(
            'tournament', 'players', 'players__user', 'stream_room', 'generated_seed'
        ).order_by('scheduled_at')
        rows = []
        for m in all_matches:
            player_names = ', '.join([p.user.username for p in m.players])
            row = {
                'id': m.id,
                'tournament': m.tournament.name if m.tournament else '',
                'scheduled_at': m.scheduled_at.strftime('%Y-%m-%d %H:%M') if m.scheduled_at else '',
                'seated': m.seated_at.strftime('%Y-%m-%d %H:%M') if m.seated_at else '',
                'finished': m.finished_at.strftime('%Y-%m-%d %H:%M') if m.finished_at else '',
                'players': player_names,
                'stream_room': m.stream_room.name if m.stream_room else '',
                'seed': m.generated_seed.seed_url if m.generated_seed else '',
                'generated_seed': m.generated_seed.seed_url if m.generated_seed else ''
            }
            # Admin table may have extra fields
            if admin_controls:
                row['actions'] = ''
            rows.append(row)
        table.rows = rows
        table.update()

    show_upcoming_checkbox = ui.checkbox('Show only upcoming matches', value=True, on_change=refresh)

    with ui.row().style('width: 100%;'):
        if submit_match_callback:
            ui.button('Submit Match', on_click=submit_match_callback)
        ui.button('Refresh', on_click=refresh).props('icon=refresh').style('min-width: 0; margin-left: auto;')

    match_table = MatchTable(columns=columns, admin_controls=admin_controls)
    table = match_table.render()
    if extra_slots:
        for slot_name, slot_template in extra_slots.items():
            match_table.table.add_slot(slot_name, slot_template)
    return table, refresh
