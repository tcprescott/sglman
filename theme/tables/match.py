import asyncio
from nicegui import app, ui
from models import Commentator, Match, Tracker, User
from theme.dialog import ConfirmationDialog, UserDialog
from theme.tables.base_table import BaseTableView

class MatchTableView(BaseTableView):
    def __init__(self, columns, get_query, admin_controls=False, extra_slots=None, submit_match_callback=None):
        # Custom slots for clickable cells
        custom_slots = {
            'body-cell-id': '''<q-td :props="props">
                <a href="#" @click="$parent.$emit('edit_match', props)" style="color: #1976d2; text-decoration: underline;">{{ props.value }}</a>
            </q-td>''',
            'body-cell-players': '''<q-td :props="props">
                <span>
                    <template v-for="(name, idx) in props.value">
                        <a v-if="props.row.actions !== undefined" href="#" @click="$parent.$emit('edit_player', { row: props.row, idx })" style="color: #1976d2; text-decoration: underline; margin-right: 4px;">{{ name }}</a>
                        <span v-else style="margin-right: 4px; text-decoration: underline;">{{ name }}</span>
                    </template>
                </span>
            </q-td>''',
            'body-cell-commentators': '''<q-td :props="props">
                <span>
                    <template v-for="(item, idx) in props.value">
                        <a href="#" @click="$parent.$emit('edit_commentator', { row: props.row, idx })"
                           :style="'color: ' + (item[1] ? '#1976d2' : 'red') + '; text-decoration: underline; margin-right: 4px; font-weight:' + (item[1] ? 'bold' : 'normal')">
                            {{ item[0] }}
                        </a>
                    </template>
                </span>
            </q-td>''',
            'body-cell-trackers': '''<q-td :props="props">
                <span>
                    <template v-for="(item, idx) in props.value">
                        <a href="#" @click="$parent.$emit('edit_tracker', { row: props.row, idx })"
                           :style="'color: ' + (item[1] ? '#1976d2' : 'red') + '; text-decoration: underline; margin-right: 4px; font-weight:' + (item[1] ? 'bold' : 'normal')">
                            {{ item[0] }}
                        </a>
                    </template>
                </span>
            </q-td>''',
        }
        super().__init__(
            columns=columns,
            get_query=get_query,
            extra_slots=extra_slots,
            submit_callback=submit_match_callback,
            table_class='match-table',
            row_key='id',
            add_label='Create Match' if admin_controls else 'Request Match',
            edit_slot='body-cell-id',
            edit_event='edit_match',
            pagination={'rowsPerPage': 20, 'page': 1},
            admin_controls=admin_controls,
            custom_slots=custom_slots,
            show_upcoming_checkbox=True,
            auto_refresh_checkbox=admin_controls
        )
        self._auto_refresh_task = None
        self._setup_role_events()

    def _build_row(self, m):
        player_names = [p.user.preferred_name for p in m.players]
        commentator_names = [(c.user.preferred_name, c.approved, c.user.discord_id) for c in m.commentators]
        tracker_names = [(t.user.preferred_name, t.approved, t.user.discord_id) for t in m.trackers]
        row = {
            'id': m.id,
            'tournament': m.tournament.name if m.tournament else '',
            'scheduled_at': m.scheduled_at.strftime('%Y-%m-%d %H:%M') if m.scheduled_at else '',
            'seated': m.seated_at.strftime('%Y-%m-%d %H:%M') if m.seated_at else '',
            'finished': m.finished_at.strftime('%Y-%m-%d %H:%M') if m.finished_at else '',
            'players': player_names,
            'stream_room': m.stream_room.name if m.stream_room else '',
            'seed': m.generated_seed.seed_url if m.generated_seed else '',
            'generated_seed': m.generated_seed.seed_url if m.generated_seed else '',
            'tournament_seed_generator': m.tournament.seed_generator if m.tournament else None,
            'commentators': commentator_names,
            'trackers': tracker_names,
        }
        if self.admin_controls:
            row['actions'] = ''
        return row

    def _setup_role_events(self):
        # Handler for editing a player
        async def handle_edit_role(role, event):
            row = event.args['row']
            idx = event.args['idx']
            match_id = row['id']
            match_query = self.get_query()
            prefetch_map = {
                'player': ('players', 'players__user'),
                'commentator': ('commentators', 'commentators__user'),
                'tracker': ('trackers', 'trackers__user'),
            }
            attr_map = {
                'player': 'players',
                'commentator': 'commentators',
                'tracker': 'trackers',
            }
            if role not in prefetch_map:
                ui.notify(f'Unknown role: {role}', color='warning')
                return
            m = await match_query.filter(id=match_id).prefetch_related(*prefetch_map[role]).first()
            items = getattr(m, attr_map[role], []) if m else []
            if not m or idx >= len(items):
                ui.notify(f'{role.capitalize()} not found.', color='warning')
                return
            user = items[idx].user
            dialog = UserDialog(user)
            await dialog.open()

        async def handle_approve_role(role, event):
            row = event.args['row']
            idx = event.args['idx']
            match_id = row['id']
            match_query = self.get_query()
            prefetch_map = {
                'player': ('players', 'players__user'),
                'commentator': ('commentators', 'commentators__user'),
                'tracker': ('trackers', 'trackers__user'),
            }
            attr_map = {
                'player': 'players',
                'commentator': 'commentators',
                'tracker': 'trackers',
            }
            if role not in prefetch_map:
                ui.notify(f'Unknown role: {role}', color='warning')
                return
            m = await match_query.filter(id=match_id).prefetch_related(*prefetch_map[role]).first()
            items = getattr(m, attr_map[role], []) if m else []
            if not m or idx >= len(items):
                ui.notify(f'{role.capitalize()} not found.', color='warning')
                return
            from theme.dialog import ApproveCrewDialog
            crew_member = items[idx]
            dialog = ApproveCrewDialog(crew_member, role, on_approve=lambda: self.update_row_by_id(match_id))
            await dialog.open()

        for role in ['player']:
            self.table.on(f'edit_{role}', lambda event, r=role: handle_edit_role(r, event))
        for role in ['commentator', 'tracker']:
            self.table.on(f"edit_{role}", lambda event, r=role: handle_approve_role(r, event))

        async def handle_signup_or_undo_role(action, role, row):
            discord_id = app.storage.user.get('discord_id', None)
            if not discord_id:
                ui.notify(f'You must be logged in to {action}.', color='warning')
                return
            user = await User.get(discord_id=discord_id)
            match_query = self.get_query()
            match = await match_query.filter(id=row['id']).first().prefetch_related('tournament', role + 's', role + 's__user')
            if not match:
                ui.notify('Match not found.', color='warning')
                return
            attr_map = {
                'commentator': 'commentators',
                'tracker': 'trackers',
            }
            if role not in attr_map:
                ui.notify(f'Unknown role: {role}', color='warning')
                return
            crew_list = getattr(match, attr_map[role], [])
            if action == 'undo':
                crew_member = next((c for c in crew_list if c.user_id == user.id), None)
                if not crew_member:
                    ui.notify(f'You are not signed up as a {role} for this match.', color='info')
                    return
                await crew_member.delete()
                ui.notify(f'You have been removed as a {role} for match ID {match.id}.', color='positive')
                await self.update_row_by_id(match.id)
            elif action == 'signup':
                async def update_role_signup():
                    if any(c.user_id == user.id for c in crew_list):
                        ui.notify(f'You are already signed up as a {role} for this match.', color='info')
                        return
                    model_map = {
                        'commentator': Commentator,
                        'tracker': Tracker,
                    }
                    new_crew = model_map.get(role)(match=match, user=user, approved=False)
                    await new_crew.save()
                    ui.notify(f'Successfully signed up as a {role} for match ID {match.id}. Awaiting approval.', color='positive')
                    await self.update_row_by_id(match.id)
                    dialog.dialog.close()
                dialog = ConfirmationDialog(f'Do you want to sign up as a {role} for match ID {match.id}?', confirm_text='Yes', cancel_text='No', on_confirm=update_role_signup)
                dialog.open()
        self.table.on('signup_commentator', lambda event: handle_signup_or_undo_role('signup', 'commentator', event.args))
        self.table.on('signup_tracker', lambda event: handle_signup_or_undo_role('signup', 'tracker', event.args))
        self.table.on('undo_commentator', lambda event: handle_signup_or_undo_role('undo', 'commentator', event.args))
        self.table.on('undo_tracker', lambda event: handle_signup_or_undo_role('undo', 'tracker', event.args))

    async def update_row_by_id(self, match_id):
        idx = next((i for i, row in enumerate(self.table.rows)
                   if row.get('id') == match_id), None)
        if idx is None:
            return
        match_query = self.get_query()
        m = await match_query.filter(id=match_id).prefetch_related(
            'tournament', 'players', 'players__user', 'stream_room', 'generated_seed', 'commentators', 'commentators__user', 'trackers', 'trackers__user'
        ).first()
        if not m:
            del self.table.rows[idx]
            self.table.update()
            return
        row = self._build_row(m)
        self.table.rows[idx] = row
        self.table.update()

    async def delete_row_by_id(self, match_id):
        idx = next((i for i, row in enumerate(self.table.rows)
                   if row.get('id') == match_id), None)
        if idx is not None:
            del self.table.rows[idx]
            self.table.update()
