import asyncio

from nicegui import ui

from theme.dialog import TournamentDialog
from theme.dialog.tournament_players_dialog import TournamentPlayersDialog


class TournamentTableView:
    """Encapsulates the tournament table UI and logic for admin/player dashboards."""
    def __init__(self, columns, get_query, extra_slots=None, submit_tournament_callback=None):
        self.columns = columns
        self.get_query = get_query
        self.extra_slots = extra_slots
        self.submit_tournament_callback = submit_tournament_callback
        self.table = None
        self._setup_ui()

    def _setup_ui(self):
        with ui.row().style('width: 100%;'):
            if self.submit_tournament_callback:
                ui.button('Add Tournament', on_click=self.submit_tournament_callback)
            ui.button(on_click=self.refresh).props('icon=refresh').style('min-width: 0; margin-left: auto;')

        ui.add_head_html("""
        <style>
        .tournament-table th, .tournament-table td {
            border-right: 1px solid #ccc;
        }
        .tournament-table td {
            text-align: left;
        }
        .tournament-table th {
            text-align: center;
        }
        .tournament-table th:last-child, .tournament-table td:last-child {
            border-right: none;
        }
        .tournament-table {
            border-collapse: collapse;
        }
        .tournament-table tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .tournament-table tr:nth-child(odd) {
            background-color: #ffffff;
        }
        </style>
        """)
        with ui.column().style('width: 100%;'):
            self.table = ui.table(
                columns=self.columns,
                rows=[],
                row_key='id',
                # pagination={'rowsPerPage': 20, 'page': 1}
            ).classes('tournament-table').style('margin-top: 1em; width: 100%;').props(':grid="Quasar.Screen.lt.md"')
        self.table.on('update:pagination', self._on_page_change)
        # Add slot for clickable tournament name
        self.table.add_slot('body-cell-name', '''<q-td :props="props">
            <a href="#" @click="$parent.$emit('edit_tournament', props)" style="color: #1976d2; text-decoration: underline;">{{ props.value }}</a>
        </q-td>''')
        # Add slot for clickable player count
        self.table.add_slot('body-cell-player_count', '''<q-td :props="props">
            <a href="#" @click="$parent.$emit('show_players', props)" style="color: #1976d2; text-decoration: underline;">{{ props.value }}</a>
        </q-td>''')
        if self.extra_slots:
            for slot_name, slot_template in self.extra_slots.items():
                self.table.add_slot(slot_name, slot_template)
        # Register edit_tournament event handler immediately after table creation
        self.table.on('edit_tournament', self.handle_edit_tournament)
        self.table.on('show_players', self.handle_show_players)

    async def refresh(self, *args, **kwargs):
        tournament_query = self.get_query().prefetch_related('players')
        all_tournaments = await tournament_query.order_by('name')
        rows = []
        for t in all_tournaments:
            row = {
                'id': t.id,
                'name': t.name,
                'description': t.description,
                'seed_generator': t.seed_generator,
                'is_active': t.is_active,
                'players_per_match': t.players_per_match,
                'team_size': t.team_size,
                'staff_administered': t.staff_administered,
                'player_count': len(t.players),  # Changed to use prefetch_related data
                'average_match_duration': t.average_match_duration,
                'max_match_duration': t.max_match_duration,
            }
            rows.append(row)
        self.table.rows = rows
        self.table.update()

    def _on_page_change(self, event):
        asyncio.create_task(self.refresh())

    async def update_row_by_id(self, tournament_id):
        """
        Update a single row in the table by its tournament ID, only if the row is currently visible.
        """
        idx = next((i for i, row in enumerate(self.table.rows) if row.get('id') == tournament_id), None)
        if idx is None:
            return  # Row not visible, do nothing
        tournament_query = self.get_query()
        t = await tournament_query.filter(id=tournament_id).first()
        if not t:
            return  # Tournament not found
        row = {
            'id': t.id,
            'name': t.name,
        }
        self.table.rows[idx] = row
        self.table.update()

    # Handler for editing a tournament
    async def handle_edit_tournament(self, event):
        row = event.args['row'] if hasattr(event, 'args') and 'row' in event.args else event.args if hasattr(event, 'args') else event
        tournament_id = row['id']
        tournament_query = self.get_query()
        t = await tournament_query.filter(id=tournament_id).first()
        if not t:
            ui.notify('Tournament not found.', color='warning')
            return
        dialog = TournamentDialog(t)
        await dialog.open()
        # You may want to call self.refresh() or self.update_row_by_id(t.id) after editing

    async def handle_show_players(self, event):
        row = event.args['row'] if hasattr(event, 'args') and 'row' in event.args else event.args if hasattr(event, 'args') else event
        tournament_id = row['id']
        tournament_query = self.get_query()
        t = await tournament_query.filter(id=tournament_id).first()
        if not t:
            ui.notify('Tournament not found.', color='warning')
            return
        dialog = TournamentPlayersDialog(t)
        await dialog.open()