from nicegui import ui
import asyncio

# TODO: Implement server-side pagination, sorting, and filtering for large datasets


class MatchTableView:
    """Encapsulates the match table UI and logic for admin/player dashboards."""

    def __init__(self, columns, get_query, admin_controls=False, extra_slots=None, submit_match_callback=None):
        self.columns = columns
        self.get_query = get_query
        self.admin_controls = admin_controls
        self.extra_slots = extra_slots
        self.submit_match_callback = submit_match_callback
        self.table = None
        self.show_upcoming_checkbox = None
        self._setup_ui()

    def _setup_ui(self):
        with ui.row().style('width: 100%;'):
            if self.submit_match_callback:
                ui.button('Add Match', on_click=self.submit_match_callback)
            self.show_upcoming_checkbox = ui.checkbox(
                'Show only upcoming matches', value=True, on_change=self.refresh)
            ui.button('Refresh', on_click=self.refresh).props(
                'icon=refresh').style('min-width: 0; margin-left: auto;')

        ui.add_head_html("""
        <style>
        .match-table th, .match-table td {
            border-right: 1px solid #ccc;
        }
        .match-table td {
            text-align: left;
        }
        .match-table th {
            text-align: center;
        }
        .match-table th:last-child, .match-table td:last-child {
            border-right: none;
        }
        .match-table {
            border-collapse: collapse;
        }
        .match-table tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .match-table tr:nth-child(odd) {
            background-color: #ffffff;
        }
        </style>
        """)
        with ui.column().style('width: 100%;'):
            self.table = ui.table(
                columns=self.columns,
                rows=[],
                row_key='id',
                pagination={'rowsPerPage': 20, 'page': 1}
            ).classes('match-table').style('margin-top: 1em; width: 100%;')
        self.table.on('update:pagination', self._on_page_change)
        # Add slot for clickable match id (or other key field)
        self.table.add_slot('body-cell-id', '''<q-td :props="props">
            <a href="#" @click="$parent.$emit('edit_match', props)" style="color: #1976d2; text-decoration: underline;">{{ props.value }}</a>
        </q-td>''')
        if self.extra_slots:
            for slot_name, slot_template in self.extra_slots.items():
                self.table.add_slot(slot_name, slot_template)
        self.table.on('update:pagination', self._on_page_change)
        # Add slot for clickable player names
        self.table.add_slot('body-cell-players', '''<q-td :props="props">
            <span>
                <template v-for="(name, idx) in props.value.split(', ')">
                    <a href="#" @click="$parent.$emit('edit_player', { row: props.row, idx })" style="color: #1976d2; text-decoration: underline; margin-right: 4px;">{{ name }}</a>
                </template>
            </span>
        </q-td>''')
        if self.extra_slots:
            for slot_name, slot_template in self.extra_slots.items():
                self.table.add_slot(slot_name, slot_template)
        # Handler for editing a player

        async def handle_edit_player(event):
            row = event.args['row']
            idx = event.args['idx']
            match_id = row['id']
            match_query = self.get_query()
            m = await match_query.filter(id=match_id).prefetch_related('players', 'players__user').first()
            if not m or idx >= len(m.players):
                ui.notify('Player not found.', color='warning')
                return
            from pages.dialogues import UserEditDialog
            user = m.players[idx].user
            dialog = UserEditDialog(user)
            await dialog.open()
        self.table.on('edit_player', handle_edit_player)

    async def refresh(self, *args, **kwargs):
        match_query = self.get_query()
        if self.show_upcoming_checkbox.value:
            match_query = match_query.filter(finished_at__isnull=True)
        all_matches = await match_query.prefetch_related(
            'tournament', 'players', 'players__user', 'stream_room', 'generated_seed'
        ).order_by('scheduled_at')
        rows = []
        for m in all_matches:
            player_names = ', '.join(
                [p.user.preferred_name for p in m.players])
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
            if self.admin_controls:
                row['actions'] = ''
            rows.append(row)
        self.table.rows = rows
        self.table.update()

    def _on_page_change(self, event):
        import asyncio
        asyncio.create_task(self.refresh())

    async def update_row_by_id(self, match_id):
        """
        Update a single row in the table by its match ID, only if the row is currently visible.
        Does not respect the upcoming filter, but only updates if the row is present in self.table.rows.
        """
        # Find the index of the row with the given match_id
        idx = next((i for i, row in enumerate(self.table.rows)
                   if row.get('id') == match_id), None)
        if idx is None:
            return  # Row not visible, do nothing
        # Query for the match object
        match_query = self.get_query()
        m = await match_query.filter(id=match_id).prefetch_related(
            'tournament', 'players', 'players__user', 'stream_room', 'generated_seed'
        ).first()
        if not m:
            # Match not found, delete the row from the table
            del self.table.rows[idx]
            self.table.update()
            return
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
        if self.admin_controls:
            row['actions'] = ''
        self.table.rows[idx] = row
        self.table.update()

    async def delete_row_by_id(self, match_id):
        """
        Delete a single row in the table by its match ID, only if the row is currently visible.
        Does not delete from the database, only removes from the table UI.
        """
        idx = next((i for i, row in enumerate(self.table.rows)
                   if row.get('id') == match_id), None)
        if idx is not None:
            del self.table.rows[idx]
            self.table.update()
