from nicegui import ui
from tortoise.functions import Count

from application.tenant_context import get_current_tenant_id
from theme.dialog import TournamentDialog
from theme.dialog.tournament_players_dialog import TournamentPlayersDialog
from theme.empty_state import no_data_slot
from theme.tables.admin_crud import capture_render_context, scoped_background
from theme.tables.export import csv_export_button
from theme.tables.mobile_grid import apply_column_visibility
from theme.tables.preferences import (
    customize_table,
    preferences_button,
    row_count_label,
    search_input,
    sticky_header,
)


class TournamentTableView:
    """Encapsulates the tournament table UI and logic for admin/player dashboards."""
    def __init__(self, columns, get_query, extra_slots=None, submit_tournament_callback=None,
                 table_key=None, searchable=False):
        self.columns = columns
        # When set, this view's desktop columns follow the viewer's saved layout.
        self.table_key = table_key
        # A text box over the visible columns. Not persisted: working state.
        self.searchable = searchable
        self._plan = None
        self.get_query = get_query
        self.extra_slots = extra_slots
        self.submit_tournament_callback = submit_tournament_callback
        self.table = None
        # Capture the tenant while the request context is live; background tasks
        # (the initial load, pagination refreshes) run detached from the client
        # slot where the tenant stash lives, so scoped reads would otherwise raise
        # require_tenant_id(). _bg rebinds it — same pattern as MatchTableView.
        self._tenant_id = get_current_tenant_id()
        self._render_context = capture_render_context()
        self._setup_ui()

    def _bg(self, coro) -> None:
        """Schedule ``coro`` with this view's tenant *and* display zone rebound."""
        scoped_background(self._render_context, coro)

    def _setup_ui(self):
        # Toolbar with actions
        with ui.row().classes('full-width'):
            if self.submit_tournament_callback:
                ui.button('Add Tournament', icon='add', on_click=self.submit_tournament_callback).props('color=primary')
            ui.space()
            # Filled after the table exists; the toolbar is drawn first.
            gear_slot = ui.row().classes('items-center')
            ui.button(icon='refresh', on_click=self.refresh).props('flat color=primary').tooltip('Refresh table')

        with ui.column().classes('full-width'):
            self.table = ui.table(
                columns=self.columns,
                rows=[],
                row_key='id',
                # Client-side paging over the rows already loaded — see the note
                # in theme/tables/match.py; there is no pagination handler.
                pagination={'rowsPerPage': 25, 'page': 1},
            ).classes('tournament-table tournament-table-container').props(':grid="Quasar.Screen.lt.md"')
        # This table wires its own :grid prop rather than going through
        # enable_mobile_grid, so it has to honour `hidden` itself.
        apply_column_visibility(self.table, self.columns)
        self.table.add_slot('no-data', no_data_slot('No tournaments yet.'))
        # Add slot for clickable tournament name
        self.table.add_slot('body-cell-name', '''<q-td :props="props">
            <a href="#" @click="$parent.$emit('edit_tournament', props)" class="table-link">{{ props.value }}</a>
        </q-td>''')
        # Add slot for clickable player count
        self.table.add_slot('body-cell-player_count', '''<q-td :props="props">
            <a href="#" @click="$parent.$emit('show_players', props)" class="table-link">{{ props.value }}</a>
        </q-td>''')
        # Truncate long descriptions with tooltip
        self.table.add_slot('body-cell-description', '''<q-td :props="props">
            <span v-if="props.value" class="wrap" :title="props.value">
                {{ props.value.length > 120 ? props.value.substring(0, 117) + '...' : props.value }}
            </span>
            <span v-else>-</span>
        </q-td>''')
        # Render booleans as icons
        self.table.add_slot('body-cell-is_active', '''<q-td :props="props">
            <q-icon :name="props.value ? 'check_circle' : 'cancel'" :color="props.value ? 'positive' : 'negative'" size="sm" />
        </q-td>''')
        self.table.add_slot('body-cell-staff_administered', '''<q-td :props="props">
            <q-icon :name="props.value ? 'badge' : 'person'" :color="props.value ? 'primary' : 'grey'" size="sm" />
        </q-td>''')
        # Mobile grid item slot
        self.table.add_slot('item', '''
        <div class="q-pa-md q-mb-sm tournament-grid-card" style="width: 100%; box-sizing: border-box;">
            <div class="row items-center q-mb-xs">
                <div class="col-4 text-grey-7">Name:</div>
                <div class="col-8">
                    <a href="#" @click="$parent.$emit('edit_tournament', { row: props.row })" class="table-link">{{ props.row.name }}</a>
                </div>
            </div>
            <div class="row items-center q-mb-xs">
                <div class="col-4 text-grey-7">Description:</div>
                <div class="col-8"><span class="wrap" :title="props.row.description">{{ props.row.description && props.row.description.length > 120 ? props.row.description.substring(0,117) + '...' : (props.row.description || '-') }}</span></div>
            </div>
            <div class="row items-center q-mb-xs">
                <div class="col-4 text-grey-7">Seed Generator:</div>
                <div class="col-8">{{ props.row.seed_generator || '-' }}</div>
            </div>
            <div class="row items-center q-mb-xs">
                <div class="col-4 text-grey-7">Active:</div>
                <div class="col-8"><q-icon :name="props.row.is_active ? 'check_circle' : 'cancel'" :color="props.row.is_active ? 'positive' : 'negative'" size="sm" /></div>
            </div>
            <div class="row items-center q-mb-xs">
                <div class="col-4 text-grey-7">Staff Admin:</div>
                <div class="col-8"><q-icon :name="props.row.staff_administered ? 'badge' : 'person'" :color="props.row.staff_administered ? 'primary' : 'grey'" size="sm" /></div>
            </div>
            <div class="row items-center q-mb-xs">
                <div class="col-4 text-grey-7">Players Per Match:</div>
                <div class="col-8">{{ props.row.players_per_match }}</div>
            </div>
            <div class="row items-center q-mb-xs">
                <div class="col-4 text-grey-7">Avg Duration (min):</div>
                <div class="col-8">{{ props.row.average_match_duration }}</div>
            </div>
            <div class="row items-center q-mb-xs">
                <div class="col-4 text-grey-7">Max Duration (min):</div>
                <div class="col-8">{{ props.row.max_match_duration }}</div>
            </div>
            <div class="row items-center q-mb-xs">
                <div class="col-4 text-grey-7">Players:</div>
                <div class="col-8"><a href="#" @click="$parent.$emit('show_players', { row: props.row })" class="table-link">{{ props.row.player_count }}</a></div>
            </div>
        </div>
        ''')
        if self.extra_slots:
            for slot_name, slot_template in self.extra_slots.items():
                self.table.add_slot(slot_name, slot_template)
        if self.table_key:
            # **After** the item slot above, never before: the card is generated
            # from these columns at build time and must not follow a saved
            # layout. Pinned by tests/theme/test_table_preferences.py.
            self._plan = customize_table(self.table, self.columns, key=self.table_key)
            with self.table.parent_slot:
                row_count_label(self.table, 'tournaments')
            sticky_header(self.table)
            with gear_slot:
                if self.searchable:
                    search_input(self.table, placeholder='Search tournaments…')
                csv_export_button(
                    'tournaments',
                    lambda: self._plan.columns if self._plan else self.columns,
                    lambda: self.table.rows,
                )
                preferences_button(self.table)
        # Register edit_tournament event handler immediately after table creation
        self.table.on('edit_tournament', self.handle_edit_tournament)
        self.table.on('show_players', self.handle_show_players)
        # Initial load at build: correctness must not depend on the selected_tab
        # broadcast (which only fires on a *subsequent* tab switch) or on Quasar's
        # incidental pagination event.
        self._bg(self.refresh())

    async def refresh(self, *_, **__):
        # Count enrolled players in SQL rather than hydrating every enrollment
        # row just to len() it.
        tournament_query = self.get_query().annotate(player_count=Count('players'))
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
                'player_count': t.player_count,
                'average_match_duration': t.average_match_duration,
                'max_match_duration': t.max_match_duration,
            }
            rows.append(row)
        self.table.rows = rows
        self.table.update()

    async def update_row_by_id(self, tournament_id):
        """
        Update a single row in the table by its tournament ID, only if the row is currently visible.
        """
        idx = next((i for i, row in enumerate(self.table.rows) if row.get('id') == tournament_id), None)
        if idx is None:
            return  # Row not visible, do nothing
        tournament_query = self.get_query().annotate(player_count=Count('players'))
        t = await tournament_query.filter(id=tournament_id).first()
        if not t:
            return  # Tournament not found
        row = {
            'id': t.id,
            'name': t.name,
            'description': t.description,
            'seed_generator': t.seed_generator,
            'is_active': t.is_active,
            'players_per_match': t.players_per_match,
            'team_size': t.team_size,
            'staff_administered': t.staff_administered,
            'player_count': t.player_count,
            'average_match_duration': t.average_match_duration,
            'max_match_duration': t.max_match_duration,
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
            ui.notify("We couldn't find that tournament — it may have been removed.", color='warning')
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
            ui.notify("We couldn't find that tournament — it may have been removed.", color='warning')
            return
        # The dialog writes now, so the player-count column has to follow it.
        dialog = TournamentPlayersDialog(t, on_change=self.refresh)
        await dialog.open()